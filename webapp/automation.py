"""
automation.py - Agendador que executa os robôs de cada ativo em intervalos regulares.

Uma única thread varre o catálogo a cada 10 segundos; para cada ativo com automação
ligada e prazo vencido, calcula o sinal e o aplica no destino configurado
(apenas sinal, carteira simulada, MetaTrader 5 ou Binance).

A chave-geral (`automation_master_enabled`) desliga tudo de uma vez.
"""

import threading
import time
from datetime import datetime, timedelta

from webapp import brokers, config, portfolio, signals, store

_thread: threading.Thread | None = None
_stop_event = threading.Event()
_LOCK = threading.RLock()
TICK_SECONDS = 10


# --------------------------------------------------------------------------- #
# Ciclo de um ativo
# --------------------------------------------------------------------------- #
def run_cycle(asset: dict, mode: str = None, manual: bool = False,
              quantity: float = None, force_action: int = None) -> dict:
    """
    Executa um ciclo completo para um ativo: sinal -> decisão -> execução.
    Usado tanto pelo agendador quanto pelo botão "Executar agora" do painel.

    `force_action` ignora a decisão da rede e aplica a ação informada. Serve para
    o encerramento manual de posição: o sinal continua sendo calculado e
    registrado, mas quem manda na execução é o usuário. Só a venda pode ser
    forçada — forçar compra passaria por cima do modelo na direção que aumenta
    exposição, e isso o painel não faz.
    """
    ticker = asset["ticker"]
    mode = mode or asset["automation"]["mode"]
    origin = "manual" if manual else "automação"

    try:
        is_holding, buy_price = _current_position(asset, mode)
        signal = signals.compute_signal(asset, is_holding=is_holding, buy_price=buy_price, force_refresh=True)
    except Exception as exc:
        result = {"ok": False, "executed": False, "message": f"Falha ao ler o sinal: {exc}", "mode": mode}
        store.log_activity("error", f"[{origin}] {ticker}: {result['message']}", ticker)
        _record_run(asset, result)
        return result

    action = signal["action"] if force_action is None else int(force_action)
    price = signal["price"]
    forced = force_action is not None

    if mode == config.MODE_SIGNAL:
        execution = {"executed": False, "type": "none",
                     "message": f"Sinal registrado: {signal['action_label']} (modo somente sinal)."}
    elif mode == config.MODE_PAPER:
        execution = portfolio.execute(asset, action, price, quantity=quantity)
    else:
        execution = brokers.execute_live(asset, action, price, mode, quantity=quantity)

    level = "trade" if execution.get("executed") else "info"
    descricao = (f"encerramento manual (o sinal era {signal['action_label']})" if forced
                 else f"sinal {signal['action_label']}")
    store.log_activity(
        level,
        f"[{origin}] {ticker} — {descricao} @ {price:,.2f} → {execution['message']}",
        ticker,
        {"mode": mode, "action": action, "q_values": signal["q_values"],
         "forced": forced, "executed": bool(execution.get("executed"))},
    )

    result = {
        "ok": True,
        "mode": mode,
        "forced": forced,
        "signal": signal,
        "executed": bool(execution.get("executed")),
        "trade_type": execution.get("type", "none"),
        "message": execution["message"],
        "ran_at": store.now_iso(),
    }
    _record_run(asset, result)
    return result


def _current_position(asset: dict, mode: str) -> tuple:
    """Descobre a posição atual no destino escolhido, para montar o estado da rede."""
    if mode == config.MODE_PAPER:
        return portfolio.holding_info(asset)

    if mode == config.MODE_MT5:
        try:
            from src.mt5_executor import get_mt5_positions
            import MetaTrader5 as mt5
            if mt5.initialize():
                try:
                    positions = get_mt5_positions(asset.get("broker_symbol") or config.clean_ticker(asset["ticker"]))
                    if positions:
                        return True, float(positions[0].price_open)
                finally:
                    mt5.shutdown()
        except Exception:
            pass
        return False, 0.0

    if mode in (config.MODE_BINANCE_TEST, config.MODE_BINANCE_REAL):
        status = brokers.binance_status(testnet=(mode == config.MODE_BINANCE_TEST))
        if status.get("connected"):
            symbol = asset.get("broker_symbol") or ""
            base = symbol.replace("USDT", "")
            balance = status.get("balances", {}).get(base, 0.0)
            if balance > 0:
                return True, 0.0  # preço médio não é exposto pela API de saldos
        return False, 0.0

    # Modo somente-sinal: usa a carteira simulada como referência de posição
    return portfolio.holding_info(asset)


def _record_run(asset: dict, result: dict):
    """Grava horário da última execução e agenda a próxima no catálogo."""
    interval = int(asset["automation"].get("interval_minutes") or 60)
    next_run = (datetime.now() + timedelta(minutes=interval)).strftime("%Y-%m-%d %H:%M:%S")
    summary = result.get("message", "")
    if result.get("ok") and result.get("signal"):
        summary = f"{result['signal']['action_label']} — {summary}"

    try:
        store.update_automation(asset["ticker"], {
            "last_run": store.now_iso(),
            "next_run": next_run if asset["automation"].get("enabled") else None,
            "last_result": summary[:300],
        })
    except ValueError:
        pass  # ativo removido do catálogo durante o ciclo


# --------------------------------------------------------------------------- #
# Laço do agendador
# --------------------------------------------------------------------------- #
def _due(asset: dict) -> bool:
    automation = asset["automation"]
    if not automation.get("enabled"):
        return False
    last_run = automation.get("last_run")
    if not last_run:
        return True
    try:
        last = datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return True
    return datetime.now() >= last + timedelta(minutes=int(automation.get("interval_minutes") or 60))


def _loop():
    store.log_activity("info", "Agendador de automação iniciado.")
    while not _stop_event.is_set():
        try:
            if store.load_settings().get("automation_master_enabled"):
                for asset in store.load_assets():
                    if _stop_event.is_set():
                        break
                    if _due(asset):
                        run_cycle(asset)
        except Exception as exc:  # o agendador nunca deve morrer por um erro pontual
            store.log_activity("error", f"Erro no agendador: {exc}")
        _stop_event.wait(TICK_SECONDS)
    store.log_activity("info", "Agendador de automação encerrado.")


def start():
    """Sobe a thread do agendador (idempotente)."""
    global _thread
    with _LOCK:
        if _thread and _thread.is_alive():
            return
        _stop_event.clear()
        _thread = threading.Thread(target=_loop, name="dqn-scheduler", daemon=True)
        _thread.start()


def stop():
    with _LOCK:
        _stop_event.set()


def status() -> dict:
    settings = store.load_settings()
    assets = store.load_assets()
    active = [a for a in assets if a["automation"].get("enabled")]
    live = [a for a in active if a["automation"]["mode"] in config.LIVE_MODES]
    return {
        "scheduler_running": bool(_thread and _thread.is_alive()),
        "master_enabled": bool(settings.get("automation_master_enabled")),
        "allow_real_money": bool(settings.get("allow_real_money")),
        "active_count": len(active),
        "live_count": len(live),
        "active_tickers": [a["ticker"] for a in active],
        "tick_seconds": TICK_SECONDS,
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
