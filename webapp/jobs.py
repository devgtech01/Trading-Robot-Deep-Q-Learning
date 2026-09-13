"""
jobs.py - Execução em segundo plano do treinamento e do backtest dos modelos.

Cada job roda em uma thread própria e publica log e progresso incrementais,
que o painel consome por polling (GET /api/jobs). O laço de treino é o mesmo
de main.py / main_crypto.py, só que sem tqdm e com callback de progresso.
"""

import os
import threading
import time
import traceback
import uuid

import matplotlib

matplotlib.use("Agg")  # gráficos gerados fora da thread principal, sem GUI

from src.b3_data import load_b3_data, split_train_test
from src.crypto_data import load_crypto_data, split_crypto_train_test
from src.crypto_env import CryptoTradingEnv
from src.crypto_evaluator import calculate_crypto_metrics, plot_crypto_backtest_report
from src.dqn_agent import DQNAgent
from src.environment import B3TradingEnv
from src.evaluator import calculate_metrics, plot_backtest_report
from webapp import config, signals, sizing, store

_JOBS: dict = {}
_LOCK = threading.RLock()
MAX_LOG_LINES = 400
MAX_JOBS_KEPT = 40


# --------------------------------------------------------------------------- #
# Registro de jobs
# --------------------------------------------------------------------------- #
def _new_job(job_type: str, ticker: str, params: dict) -> dict:
    job = {
        "id": uuid.uuid4().hex[:12],
        "type": job_type,
        "ticker": ticker,
        "params": params,
        "status": "running",
        "progress": 0.0,
        "stage": "Preparando...",
        "log": [],
        "result": None,
        "error": None,
        "cancel_requested": False,
        "started_at": store.now_iso(),
        "finished_at": None,
    }
    with _LOCK:
        _JOBS[job["id"]] = job
        if len(_JOBS) > MAX_JOBS_KEPT:
            finished = [j for j in _JOBS.values() if j["status"] in ("done", "error", "cancelled")]
            finished.sort(key=lambda j: j["started_at"])
            for old in finished[: len(_JOBS) - MAX_JOBS_KEPT]:
                _JOBS.pop(old["id"], None)
    return job


def _log(job: dict, message: str):
    with _LOCK:
        job["log"].append(f"[{time.strftime('%H:%M:%S')}] {message}")
        if len(job["log"]) > MAX_LOG_LINES:
            del job["log"][: len(job["log"]) - MAX_LOG_LINES]


def _public(job: dict, log_from: int = 0) -> dict:
    return {
        "id": job["id"],
        "type": job["type"],
        "ticker": job["ticker"],
        "status": job["status"],
        "progress": round(job["progress"], 1),
        "stage": job["stage"],
        "log": job["log"][log_from:],
        "log_total": len(job["log"]),
        "result": job["result"],
        "error": job["error"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
    }


def list_jobs(active_only: bool = False) -> list:
    with _LOCK:
        jobs = list(_JOBS.values())
    jobs.sort(key=lambda j: j["started_at"], reverse=True)
    if active_only:
        jobs = [j for j in jobs if j["status"] == "running"]
    return [_public(j, log_from=max(0, len(j["log"]) - 3)) for j in jobs]


def get_job(job_id: str, log_from: int = 0) -> dict | None:
    with _LOCK:
        job = _JOBS.get(job_id)
    return _public(job, log_from) if job else None


def cancel_job(job_id: str) -> bool:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job["status"] != "running":
            return False
        job["cancel_requested"] = True
        job["stage"] = "Cancelamento solicitado..."
        return True


def running_job_for(ticker: str) -> dict | None:
    with _LOCK:
        for job in _JOBS.values():
            if job["ticker"] == ticker and job["status"] == "running":
                return _public(job)
    return None


# --------------------------------------------------------------------------- #
# Treinamento + backtest
# --------------------------------------------------------------------------- #
def _run_training(job: dict, asset: dict, episodes: int, batch_size: int, capital: float):
    ticker = asset["ticker"]
    is_crypto = asset["asset_class"] == config.CLASS_CRYPTO
    currency = "$" if is_crypto else "R$"

    job["stage"] = "Baixando histórico de mercado..."
    _log(job, f"Baixando histórico de {ticker} desde {asset['start_date']}...")

    if is_crypto:
        raw_df = load_crypto_data(ticker, start_date=asset["start_date"])
        train_df, test_df = split_crypto_train_test(raw_df, split_date=asset["split_date"])
        train_env = CryptoTradingEnv(train_df, initial_balance=capital)
        test_env = CryptoTradingEnv(test_df, initial_balance=capital)
    else:
        raw_df = load_b3_data(ticker, start_date=asset["start_date"])
        train_df, test_df = split_train_test(raw_df, split_date=asset["split_date"])
        train_env = B3TradingEnv(train_df, initial_balance=capital)
        test_env = B3TradingEnv(test_df, initial_balance=capital)

    _log(job, f"Treino: {len(train_df)} barras | Teste cego: {len(test_df)} barras "
              f"(corte em {asset['split_date']}).")

    agent = DQNAgent(state_size=train_env.state_size, action_space=train_env.action_space)
    _log(job, f"Agente DQN criado (estado={train_env.state_size}, dispositivo={agent.device}).")

    # ---------------- Loop de treino ----------------
    equity_curve_by_episode = []
    for episode in range(1, episodes + 1):
        if job["cancel_requested"]:
            job["status"] = "cancelled"
            job["stage"] = "Cancelado pelo usuário"
            _log(job, "Treinamento cancelado.")
            return

        job["stage"] = f"Treinando episódio {episode}/{episodes}"
        state = train_env.reset()
        done = False
        total_loss, loss_steps = 0.0, 0

        while not done:
            action = agent.act(state, evaluate=False)
            next_state, reward, done, _ = train_env.step(action)
            agent.remember(state, action, reward, next_state, done)
            state = next_state
            if len(agent.memory) > batch_size:
                total_loss += agent.replay(batch_size)
                loss_steps += 1

        if episode % 3 == 0:
            agent.update_target_network()

        final_portfolio = train_env.portfolio_history[-1]
        pnl_pct = (final_portfolio - train_env.initial_balance) / train_env.initial_balance * 100.0
        avg_loss = total_loss / max(1, loss_steps)
        equity_curve_by_episode.append(round(pnl_pct, 2))

        job["progress"] = episode / episodes * 90.0
        _log(job, f"Ep {episode:02d}/{episodes:02d} | Saldo {currency} {final_portfolio:,.2f} "
                  f"({pnl_pct:+.2f}%) | Trades: {len(train_env.trade_log)} | "
                  f"Epsilon {agent.epsilon:.3f} | Loss {avg_loss:.5f}")

    # ---------------- Salvar modelo ----------------
    config.ensure_dirs()
    path = config.model_path(ticker)
    agent.save(path)
    signals.invalidate_agent_cache(ticker)
    _log(job, f"Modelo salvo em {os.path.relpath(path, config.BASE_DIR)}.")

    # ---------------- Teste cego ----------------
    job["stage"] = "Executando teste cego (out-of-sample)..."
    job["progress"] = 92.0
    state = test_env.reset()
    done = False
    while not done:
        action = agent.act(state, evaluate=True)
        state, _, done, _ = test_env.step(action)

    first_price = float(test_env.df.iloc[test_env.window_size]["Close"])
    last_price = float(test_env.df.iloc[-1]["Close"])
    benchmark_return = (last_price - first_price) / first_price * 100.0

    if is_crypto:
        metrics = calculate_crypto_metrics(test_env.portfolio_history, test_env.trade_log, benchmark_return)
        report = plot_crypto_backtest_report(
            dates=test_env.dates_history, portfolio_history=test_env.portfolio_history,
            df_prices=test_env.df, trade_log=test_env.trade_log, metrics=metrics,
            ticker=ticker, output_dir=config.REPORTS_DIR)
    else:
        metrics = calculate_metrics(test_env.portfolio_history, test_env.trade_log, benchmark_return)
        report = plot_backtest_report(
            dates=test_env.dates_history, portfolio_history=test_env.portfolio_history,
            df_prices=test_env.df, trade_log=test_env.trade_log, metrics=metrics,
            ticker=ticker, output_dir=config.REPORTS_DIR)

    # Guarda a evidência do teste cego: é o que embasa o tamanho de ordem sugerido.
    sizing.save_metrics(ticker, metrics, episodes=episodes)

    job["progress"] = 100.0
    job["stage"] = "Concluído"
    job["result"] = {
        "metrics": {k: (None if v is None else (float(v) if isinstance(v, (int, float)) else v))
                    for k, v in metrics.items()},
        "report": os.path.relpath(report, config.BASE_DIR).replace("\\", "/"),
        "model": os.path.relpath(path, config.BASE_DIR).replace("\\", "/"),
        "episodes_pnl_pct": equity_curve_by_episode,
    }

    _log(job, f"Teste cego: retorno {metrics['total_return_pct']:+.2f}% "
              f"vs Buy & Hold {metrics['benchmark_return_pct']:+.2f}% | "
              f"Drawdown {metrics['max_drawdown_pct']:.2f}% | "
              f"Trades {metrics['total_trades']} | Acerto {metrics['win_rate_pct']:.1f}%")
    _log(job, "Relatório gráfico gerado com sucesso.")


def _worker(job: dict, asset: dict, episodes: int, batch_size: int, capital: float):
    try:
        _run_training(job, asset, episodes, batch_size, capital)
        if job["status"] == "running":
            job["status"] = "done"
            store.log_activity("success", f"Treinamento concluído para {asset['ticker']}.", asset["ticker"],
                               {"job_id": job["id"]})
        else:
            store.log_activity("warning", f"Treinamento de {asset['ticker']} cancelado.", asset["ticker"])
    except Exception as exc:
        job["status"] = "error"
        job["stage"] = "Erro"
        job["error"] = str(exc)
        _log(job, f"ERRO: {exc}")
        _log(job, traceback.format_exc().strip().splitlines()[-1])
        store.log_activity("error", f"Falha no treinamento de {asset['ticker']}: {exc}", asset["ticker"])
    finally:
        job["finished_at"] = store.now_iso()


def start_training(asset: dict, episodes: int = 20, batch_size: int = 32, capital: float = None) -> dict:
    """Dispara o treinamento em segundo plano e devolve o job criado."""
    existing = running_job_for(asset["ticker"])
    if existing:
        raise RuntimeError(f"Já existe um treinamento em andamento para {asset['ticker']}.")

    if capital is None:
        capital = 1000.0 if asset["asset_class"] == config.CLASS_CRYPTO else 10000.0

    params = {"episodes": episodes, "batch_size": batch_size, "capital": capital}
    job = _new_job("train", asset["ticker"], params)
    _log(job, f"Iniciando treinamento de {asset['ticker']} ({episodes} episódios, "
              f"capital {capital:,.2f}).")
    store.log_activity("info", f"Treinamento iniciado para {asset['ticker']} ({episodes} episódios).",
                       asset["ticker"], {"job_id": job["id"]})

    thread = threading.Thread(
        target=_worker, args=(job, asset, episodes, batch_size, capital),
        name=f"train-{asset['ticker']}", daemon=True,
    )
    thread.start()
    return _public(job)
