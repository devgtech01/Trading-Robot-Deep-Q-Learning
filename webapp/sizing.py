"""
sizing.py - Evidência de backtest por ativo e cálculo do tamanho sugerido de ordem.

Duas responsabilidades:

1. Guardar e recuperar as métricas do teste cego (out-of-sample) de cada modelo,
   em data/backtests.json. Modelos treinados antes deste recurso não têm métricas
   salvas; nesse caso o backtest é reexecutado sob demanda a partir do .pt.

2. Converter essas métricas em um tamanho de ordem sugerido, por uma regra
   explícita e auditável — o painel mostra cada passo da conta.

A regra NÃO tenta prever preço. Ela é de risco: parte de quanto você aceita
perder por operação e divide pela perda média que o próprio modelo teve no
teste cego, depois corta o resultado conforme a qualidade daquela evidência.
"""

import json
import math
import os
import threading

import matplotlib

matplotlib.use("Agg")

from src.b3_data import load_b3_data, split_train_test
from src.crypto_data import load_crypto_data, split_crypto_train_test
from src.crypto_env import CryptoTradingEnv
from src.crypto_evaluator import calculate_crypto_metrics, plot_crypto_backtest_report
from src.dqn_agent import DQNAgent
from src.environment import B3TradingEnv
from src.evaluator import calculate_metrics, plot_backtest_report
from webapp import config, store

_LOCK = threading.RLock()
BACKTESTS_FILE = os.path.join(config.DATA_DIR, "backtests.json")

# --------------------------------------------------------------------------- #
# Parâmetros da regra de tamanho (todos aparecem na tela, nada é implícito)
# --------------------------------------------------------------------------- #
RISK_PER_TRADE = 0.02      # 2% do patrimônio da conta arriscados por operação
MAX_WEIGHT = 0.25          # nenhum ativo passa de 25% do patrimônio da conta
MIN_TRADES = 10            # abaixo disso a amostra do backtest é pequena demais
SEVERE_DRAWDOWN = 40.0     # queda de patrimônio a partir da qual o corte é dobrado
FALLBACK_LOSS_PCT = 8.0    # perda por trade assumida quando não há evidência


# --------------------------------------------------------------------------- #
# Persistência das métricas
# --------------------------------------------------------------------------- #
def _finite(value):
    """JSON não aceita inf/NaN — o fator de lucro vira inf quando não houve perdas."""
    if isinstance(value, (int, float)):
        if math.isinf(value) or math.isnan(value):
            return None
        return float(value)
    return value


def _read_all() -> dict:
    if not os.path.exists(BACKTESTS_FILE):
        return {}
    try:
        with open(BACKTESTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_metrics(ticker: str, metrics: dict, episodes: int = None) -> dict:
    """Grava as métricas do teste cego de um ativo."""
    entry = {
        "ticker": ticker.upper(),
        "metrics": {k: _finite(v) for k, v in metrics.items()},
        "episodes": episodes,
        "evaluated_at": store.now_iso(),
    }
    with _LOCK:
        data = _read_all()
        data[ticker.upper()] = entry
        config.ensure_dirs()
        tmp = f"{BACKTESTS_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, BACKTESTS_FILE)
    return entry


def load_metrics(ticker: str) -> dict | None:
    return _read_all().get(ticker.upper())


# --------------------------------------------------------------------------- #
# Backtest fora da amostra
# --------------------------------------------------------------------------- #
def run_oos_backtest(asset: dict, agent: DQNAgent, capital: float = None,
                     write_report: bool = True) -> dict:
    """
    Roda o agente de forma determinística no período de teste cego do ativo e
    devolve as métricas. Compartilhado pelo treinamento e pela avaliação avulsa.
    """
    is_crypto = asset["asset_class"] == config.CLASS_CRYPTO
    if capital is None:
        capital = 1000.0 if is_crypto else 10000.0

    if is_crypto:
        raw = load_crypto_data(asset["ticker"], start_date=asset["start_date"])
        _, test_df = split_crypto_train_test(raw, split_date=asset["split_date"])
        env = CryptoTradingEnv(test_df, initial_balance=capital)
    else:
        raw = load_b3_data(asset["ticker"], start_date=asset["start_date"])
        _, test_df = split_train_test(raw, split_date=asset["split_date"])
        env = B3TradingEnv(test_df, initial_balance=capital)

    state = env.reset()
    done = False
    while not done:
        state, _, done, _ = env.step(agent.act(state, evaluate=True))

    first_price = float(env.df.iloc[env.window_size]["Close"])
    last_price = float(env.df.iloc[-1]["Close"])
    benchmark = (last_price - first_price) / first_price * 100.0

    if is_crypto:
        metrics = calculate_crypto_metrics(env.portfolio_history, env.trade_log, benchmark)
    else:
        metrics = calculate_metrics(env.portfolio_history, env.trade_log, benchmark)

    if write_report:
        plot = plot_crypto_backtest_report if is_crypto else plot_backtest_report
        plot(dates=env.dates_history, portfolio_history=env.portfolio_history,
             df_prices=env.df, trade_log=env.trade_log, metrics=metrics,
             ticker=asset["ticker"], output_dir=config.REPORTS_DIR)

    return metrics


def evaluate_model(asset: dict) -> dict | None:
    """Reavalia um modelo já treinado para obter métricas que não foram salvas."""
    path = config.model_path(asset["ticker"])
    if not os.path.exists(path):
        return None

    from webapp import signals  # import tardio: signals importa store, não sizing

    agent = DQNAgent(state_size=signals.state_size_for(asset["asset_class"]), action_space=3)
    agent.load(path)
    metrics = run_oos_backtest(asset, agent)
    return save_metrics(asset["ticker"], metrics)


def metrics_for(asset: dict, compute_if_missing: bool = True) -> dict | None:
    """Métricas do ativo, reavaliando o modelo salvo se ainda não houver registro."""
    entry = load_metrics(asset["ticker"])
    if entry or not compute_if_missing:
        return entry
    try:
        return evaluate_model(asset)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Regra de tamanho
# --------------------------------------------------------------------------- #
def suggest(asset: dict, price: float, equity: float, cash: float,
            entry: dict | None) -> dict:
    """
    Calcula o tamanho sugerido de ordem e devolve TODOS os passos da conta,
    para que o painel possa mostrar o embasamento em vez de um número solto.
    """
    is_crypto = asset["asset_class"] == config.CLASS_CRYPTO
    metrics = (entry or {}).get("metrics") or {}
    steps, warnings = [], []

    # -- 1. Orçamento de risco -------------------------------------------------
    risk_budget = equity * RISK_PER_TRADE

    # -- 2. Perda esperada por operação, tirada do teste cego -------------------
    avg_loss = abs(float(metrics.get("avg_loss_pct") or 0.0))
    drawdown = abs(float(metrics.get("max_drawdown_pct") or 0.0))

    if avg_loss >= 0.5:
        loss_pct, loss_origin = avg_loss, "perda média por trade no teste cego"
    elif drawdown >= 0.5:
        loss_pct, loss_origin = drawdown, "maior queda de patrimônio no teste cego"
    else:
        loss_pct, loss_origin = FALLBACK_LOSS_PCT, "valor assumido (sem evidência de perdas)"
        warnings.append("O backtest não registrou perdas suficientes para medir o risco; "
                        f"a conta usa {FALLBACK_LOSS_PCT:.0f}% como perda hipotética.")

    base_amount = risk_budget / (loss_pct / 100.0)
    steps.append(f"{RISK_PER_TRADE * 100:.0f}% do patrimônio ({equity:,.2f}) = {risk_budget:,.2f} "
                 f"÷ {loss_pct:.2f}% ({loss_origin}) = {base_amount:,.2f}")

    # -- 3. Fator de qualidade da evidência ------------------------------------
    factor, reasons = 1.0, []

    if not entry:
        factor *= 0.25
        reasons.append("nenhum backtest registrado para este modelo")
    else:
        trades = int(metrics.get("total_trades") or 0)
        profit_factor = metrics.get("profit_factor")
        robot = float(metrics.get("total_return_pct") or 0.0)
        bench = float(metrics.get("benchmark_return_pct") or 0.0)
        episodes = entry.get("episodes")

        if trades < MIN_TRADES:
            factor *= 0.5
            reasons.append(f"amostra pequena: só {trades} operações no teste cego")
        if profit_factor is not None and profit_factor < 1.0:
            factor *= 0.25
            reasons.append(f"as perdas superaram os ganhos (fator de lucro {profit_factor:.2f})")
        # O fator de lucro pode ficar acima de 1 e o resultado final ainda ser
        # negativo, por juros compostos e taxas — então o retorno é testado à parte.
        if robot < 0:
            factor *= 0.5
            reasons.append(f"terminou o teste cego no prejuízo ({robot:+.1f}%)")
            warnings.append("Este modelo perdeu dinheiro no próprio teste cego. "
                            "Vale retreiná-lo antes de operar com ele.")
        if robot < bench:
            factor *= 0.75
            reasons.append(f"ficou abaixo do Buy & Hold ({robot:+.1f}% contra {bench:+.1f}%)")
        # A perda média por trade não enxerga sequências ruins: um modelo que
        # derreteu o patrimônio no caminho merece corte mesmo com trades pequenos.
        if drawdown >= SEVERE_DRAWDOWN:
            factor *= 0.5
            reasons.append(f"chegou a perder {drawdown:.1f}% do patrimônio no teste cego")
        if episodes is not None and episodes < 10:
            factor *= 0.5
            reasons.append(f"treinado com apenas {episodes} episódio(s)")

    factor = max(0.25, round(factor, 3))
    amount = base_amount * factor
    if reasons:
        steps.append(f"ajuste de qualidade ×{factor:.2f} → {amount:,.2f}")

    # -- 4. Tetos --------------------------------------------------------------
    capped_by = None
    weight_cap = equity * MAX_WEIGHT
    if amount > weight_cap:
        amount, capped_by = weight_cap, f"teto de {MAX_WEIGHT * 100:.0f}% do patrimônio"
        steps.append(f"limitado ao teto de {MAX_WEIGHT * 100:.0f}% do patrimônio = {amount:,.2f}")
    if amount > cash:
        amount, capped_by = cash, "caixa livre"
        steps.append(f"limitado ao caixa livre = {amount:,.2f}")

    # -- 5. Converte para a unidade que o ativo usa ----------------------------
    if is_crypto:
        units = round(max(0.0, amount), 2)          # ordem em USDT
        notional = units
    else:
        units = float(int(max(0.0, amount) // price)) if price > 0 else 0.0
        notional = units * price
        if 0 < units < 100:
            warnings.append(f"{units:.0f} ações fica abaixo do lote padrão de 100 da B3 — "
                            f"no MetaTrader 5 use o mercado fracionário "
                            f"({asset.get('broker_symbol', '')}F).")

    if units <= 0:
        warnings.append("O caixa disponível não cobre nem uma unidade deste ativo.")

    return {
        "suggested_units": units,
        "suggested_notional": notional,
        "unit_label": "USDT" if is_crypto else "ações",
        "price": price,
        "equity": equity,
        "cash": cash,
        "risk_pct": RISK_PER_TRADE * 100,
        "risk_budget": risk_budget,
        "loss_pct": loss_pct,
        "loss_origin": loss_origin,
        "base_amount": base_amount,
        "quality_factor": factor,
        "quality_reasons": reasons,
        "capped_by": capped_by,
        "steps": steps,
        "warnings": warnings,
        "has_evidence": bool(entry),
        "evaluated_at": (entry or {}).get("evaluated_at"),
        "episodes": (entry or {}).get("episodes"),
        "metrics": {k: _finite(v) for k, v in metrics.items()} if metrics else None,
    }
