"""
store.py - Persistência em JSON do catálogo de ativos, das configurações e do log de atividades.

Todas as escritas são atômicas (arquivo temporário + replace) e protegidas por lock,
já que o agendador roda em threads paralelas ao servidor web.
"""

import json
import os
import threading
import uuid
from datetime import datetime

from webapp import config

_LOCK = threading.RLock()
MAX_ACTIVITY_ENTRIES = 500


# --------------------------------------------------------------------------- #
# Utilidades de arquivo
# --------------------------------------------------------------------------- #
def _read_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: str, payload):
    config.ensure_dirs()
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)
    os.replace(tmp, path)


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- #
# Ativos
# --------------------------------------------------------------------------- #
def _default_automation() -> dict:
    return {
        "enabled": False,
        "mode": config.MODE_SIGNAL,
        "interval_minutes": 60,
        "last_run": None,
        "next_run": None,
        "last_result": None,
    }


def _normalize_asset(raw: dict) -> dict:
    ticker = str(raw.get("ticker", "")).strip().upper()
    asset_class = raw.get("asset_class") or config.guess_class(ticker)
    default_qty = 100 if asset_class == config.CLASS_STOCK else 100.0
    default_start = "2018-01-01" if asset_class == config.CLASS_STOCK else "2019-01-01"
    default_split = "2023-01-01" if asset_class == config.CLASS_STOCK else "2024-01-01"

    automation = {**_default_automation(), **(raw.get("automation") or {})}
    if automation["mode"] not in config.MODES_BY_CLASS[asset_class]:
        automation["mode"] = config.MODE_SIGNAL

    return {
        "ticker": ticker,
        "name": raw.get("name") or ticker,
        "asset_class": asset_class,
        "broker_symbol": raw.get("broker_symbol") or config.clean_ticker(ticker),
        "quantity": float(raw.get("quantity", default_qty)),
        "start_date": raw.get("start_date") or default_start,
        "split_date": raw.get("split_date") or default_split,
        "automation": automation,
    }


def load_assets() -> list[dict]:
    with _LOCK:
        raw = _read_json(config.ASSETS_FILE, None)
        if raw is None:
            assets = [_normalize_asset(a) for a in config.DEFAULT_ASSETS]
            _write_json(config.ASSETS_FILE, assets)
            return assets
        return [_normalize_asset(a) for a in raw]


def save_assets(assets: list[dict]):
    with _LOCK:
        _write_json(config.ASSETS_FILE, [_normalize_asset(a) for a in assets])


def get_asset(ticker: str) -> dict | None:
    ticker = ticker.strip().upper()
    for asset in load_assets():
        if asset["ticker"] == ticker:
            return asset
    return None


def upsert_asset(payload: dict) -> dict:
    """Cria ou atualiza um ativo do catálogo, preservando a configuração de automação."""
    with _LOCK:
        assets = load_assets()
        ticker = str(payload.get("ticker", "")).strip().upper()
        if not ticker:
            raise ValueError("Ticker obrigatório.")

        for idx, existing in enumerate(assets):
            if existing["ticker"] == ticker:
                merged = {**existing, **payload, "ticker": ticker}
                merged["automation"] = {**existing["automation"], **(payload.get("automation") or {})}
                assets[idx] = _normalize_asset(merged)
                save_assets(assets)
                return assets[idx]

        new_asset = _normalize_asset(payload)
        assets.append(new_asset)
        save_assets(assets)
        return new_asset


def delete_asset(ticker: str) -> bool:
    with _LOCK:
        assets = load_assets()
        remaining = [a for a in assets if a["ticker"] != ticker.strip().upper()]
        if len(remaining) == len(assets):
            return False
        save_assets(remaining)
        return True


def update_automation(ticker: str, patch: dict) -> dict:
    """Atualiza apenas o bloco de automação de um ativo."""
    with _LOCK:
        assets = load_assets()
        for idx, asset in enumerate(assets):
            if asset["ticker"] == ticker.strip().upper():
                asset["automation"] = {**asset["automation"], **patch}
                assets[idx] = _normalize_asset(asset)
                save_assets(assets)
                return assets[idx]
    raise ValueError(f"Ativo {ticker} não encontrado.")


# --------------------------------------------------------------------------- #
# Configurações globais
# --------------------------------------------------------------------------- #
def load_settings() -> dict:
    with _LOCK:
        stored = _read_json(config.SETTINGS_FILE, {})
        return {**config.DEFAULT_SETTINGS, **stored}


def save_settings(patch: dict) -> dict:
    with _LOCK:
        settings = {**load_settings(), **patch}
        _write_json(config.SETTINGS_FILE, settings)
        return settings


def public_settings() -> dict:
    """Versão das configurações segura para enviar ao navegador (chaves mascaradas)."""
    settings = load_settings()
    key = settings.get("binance_api_key", "")
    secret = settings.get("binance_secret_key", "")
    return {
        "automation_master_enabled": settings["automation_master_enabled"],
        "allow_real_money": settings["allow_real_money"],
        "quote_cache_minutes": settings["quote_cache_minutes"],
        "binance_api_key_masked": (key[:4] + "•" * 8 + key[-4:]) if len(key) > 8 else ("" if not key else "••••"),
        "binance_configured": bool(key and secret),
    }


# --------------------------------------------------------------------------- #
# Log de atividades
# --------------------------------------------------------------------------- #
def load_activity(limit: int = 100, ticker: str | None = None) -> list[dict]:
    with _LOCK:
        entries = _read_json(config.ACTIVITY_FILE, [])
    if ticker:
        entries = [e for e in entries if e.get("ticker") == ticker.upper()]
    return entries[:limit]


def log_activity(level: str, message: str, ticker: str | None = None, extra: dict | None = None) -> dict:
    """Registra um evento (mais recente primeiro) e devolve a entrada criada."""
    entry = {
        "id": uuid.uuid4().hex[:12],
        "timestamp": now_iso(),
        "level": level,           # info | success | warning | error | trade
        "message": message,
        "ticker": ticker.upper() if ticker else None,
        "extra": extra or {},
    }
    with _LOCK:
        entries = _read_json(config.ACTIVITY_FILE, [])
        entries.insert(0, entry)
        _write_json(config.ACTIVITY_FILE, entries[:MAX_ACTIVITY_ENTRIES])
    return entry
