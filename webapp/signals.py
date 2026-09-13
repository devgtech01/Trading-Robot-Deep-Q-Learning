"""
signals.py - Cotações, indicadores e leitura do sinal da rede neural DQN.

Reaproveita exatamente os mesmos módulos usados pelos scripts de linha de comando
(src/b3_data.py, src/crypto_data.py, src/dqn_agent.py), de modo que o painel e o
CLI produzem sempre o mesmo sinal para o mesmo ativo.
"""

import os
import threading
import time

import numpy as np
import pandas as pd
import torch

from src.b3_data import load_b3_data
from src.crypto_data import load_crypto_data
from src.dqn_agent import DQNAgent
from webapp import config, store

# Cache de cotações em memória: ticker -> (timestamp, DataFrame)
_QUOTE_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_CACHE_LOCK = threading.RLock()

# Cache de agentes carregados: caminho do modelo -> (mtime, DQNAgent)
_AGENT_CACHE: dict[str, tuple[float, DQNAgent]] = {}
_AGENT_LOCK = threading.RLock()


def features_for(asset_class: str) -> list[str]:
    return config.FEATURES_CRYPTO if asset_class == config.CLASS_CRYPTO else config.FEATURES_STOCK


def state_size_for(asset_class: str) -> int:
    return config.WINDOW_SIZE * len(features_for(asset_class)) + 2


# --------------------------------------------------------------------------- #
# Dados de mercado
# --------------------------------------------------------------------------- #
def market_data(asset: dict, force_refresh: bool = False, ttl_minutes: int | None = None) -> pd.DataFrame:
    """Baixa (com cache) o histórico do ativo já com os indicadores técnicos calculados."""
    ticker = asset["ticker"]
    if ttl_minutes is None:
        ttl_minutes = store.load_settings().get("quote_cache_minutes", 15)
    ttl = int(ttl_minutes) * 60

    with _CACHE_LOCK:
        cached = _QUOTE_CACHE.get(ticker)
        if cached and not force_refresh and (time.time() - cached[0]) < ttl:
            return cached[1]

    # Janela curta: o sinal só precisa das últimas barras, mas as médias de 21/20
    # períodos exigem folga, então pegamos ~2 anos.
    if asset["asset_class"] == config.CLASS_CRYPTO:
        df = load_crypto_data(ticker=ticker, start_date="2024-01-01")
    else:
        df = load_b3_data(ticker=ticker, start_date="2023-01-01")

    with _CACHE_LOCK:
        _QUOTE_CACHE[ticker] = (time.time(), df)
    return df


def invalidate_quote_cache(ticker: str | None = None):
    with _CACHE_LOCK:
        if ticker:
            _QUOTE_CACHE.pop(ticker, None)
        else:
            _QUOTE_CACHE.clear()


def price_series(asset: dict, points: int = 90) -> dict:
    """Série de fechamento recente para o mini-gráfico do card do ativo."""
    df = market_data(asset)
    tail = df.tail(points)
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in tail.index],
        "closes": [float(v) for v in tail["Close"].values],
    }


# --------------------------------------------------------------------------- #
# Modelo treinado
# --------------------------------------------------------------------------- #
def model_status(asset: dict) -> dict:
    path = config.model_path(asset["ticker"])
    exists = os.path.exists(path)
    return {
        "trained": exists,
        "path": os.path.relpath(path, config.BASE_DIR) if exists else None,
        "trained_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path))) if exists else None,
        "size_kb": round(os.path.getsize(path) / 1024, 1) if exists else 0,
    }


def _load_agent(asset: dict) -> DQNAgent:
    """Carrega o agente do disco com cache invalidado pela data de modificação do arquivo."""
    path = config.model_path(asset["ticker"])
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Modelo não treinado para {asset['ticker']}. Treine o ativo pelo painel antes de pedir o sinal."
        )

    mtime = os.path.getmtime(path)
    with _AGENT_LOCK:
        cached = _AGENT_CACHE.get(path)
        if cached and cached[0] == mtime:
            return cached[1]

        agent = DQNAgent(state_size=state_size_for(asset["asset_class"]), action_space=3)
        agent.load(path)
        _AGENT_CACHE[path] = (mtime, agent)
        return agent


def invalidate_agent_cache(ticker: str | None = None):
    with _AGENT_LOCK:
        if ticker:
            _AGENT_CACHE.pop(config.model_path(ticker), None)
        else:
            _AGENT_CACHE.clear()


# --------------------------------------------------------------------------- #
# Sinal
# --------------------------------------------------------------------------- #
def compute_signal(
    asset: dict,
    is_holding: bool = False,
    buy_price: float = 0.0,
    force_refresh: bool = False,
) -> dict:
    """
    Devolve o sinal da IA para o ativo no fechamento mais recente.

    A ação bruta da rede é filtrada pela posição informada: comprar estando comprado
    ou vender estando líquido viram AGUARDAR — mesma regra de predict_today.py.
    """
    asset_class = asset["asset_class"]
    df = market_data(asset, force_refresh=force_refresh)
    cols = features_for(asset_class)

    if len(df) < config.WINDOW_SIZE + 1:
        raise ValueError(f"Histórico insuficiente para {asset['ticker']} (barras: {len(df)}).")

    last = df.iloc[-1]
    current_price = float(last["Close"])
    prev_close = float(df.iloc[-2]["Close"]) if len(df) > 1 else current_price

    unrealized_pnl = ((current_price - buy_price) / buy_price) if (is_holding and buy_price > 0) else 0.0
    window = df.iloc[-config.WINDOW_SIZE:][cols].values.flatten()
    state = np.concatenate([window, [1.0 if is_holding else 0.0, unrealized_pnl]]).astype(np.float32)

    agent = _load_agent(asset)
    with torch.no_grad():
        q_values = agent.policy_net(
            torch.FloatTensor(state).unsqueeze(0).to(agent.device)
        ).cpu().numpy()[0]

    raw_action = int(np.argmax(q_values))
    action = raw_action
    if raw_action == 1 and is_holding:
        action = 0
    elif raw_action == 2 and not is_holding:
        action = 0

    indicators = {
        "rsi": float(last["RSI_14"]) * 100.0,
        "dist_sma21": float(last["Dist_SMA21"]) * 100.0,
        "return_1d": float(last["Return_1d"]) * 100.0,
        "return_5d": float(last["Return_5d"]) * 100.0,
    }
    if asset_class == config.CLASS_CRYPTO:
        indicators["bollinger_pct_b"] = float(last["Bollinger_PctB"]) * 100.0
        indicators["volatility"] = float(last["Volatility_14"]) * 100.0
    else:
        indicators["volatility"] = float(last["Volatility_10"]) * 100.0

    return {
        "ticker": asset["ticker"],
        "asset_class": asset_class,
        "price": current_price,
        "price_change_pct": ((current_price - prev_close) / prev_close * 100.0) if prev_close else 0.0,
        "quote_date": df.index[-1].strftime("%d/%m/%Y"),
        "action": action,
        "action_label": config.ACTION_LABELS[action],
        "raw_action": raw_action,
        "raw_action_label": config.ACTION_LABELS[raw_action],
        "filtered": action != raw_action,
        "q_values": {"hold": float(q_values[0]), "buy": float(q_values[1]), "sell": float(q_values[2])},
        "confidence": float(np.max(q_values) - np.mean(q_values)),
        "indicators": indicators,
        "is_holding": is_holding,
        "buy_price": buy_price,
        "unrealized_pnl_pct": unrealized_pnl * 100.0,
        "computed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
