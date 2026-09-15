"""
server.py - API REST + servidor do painel web do Robô de Trading DQN.

Sobe com `python dashboard.py`. Todos os endpoints ficam sob /api e devolvem JSON;
a página única é servida em /.
"""

import math
import os
from concurrent.futures import ThreadPoolExecutor
from threading import RLock

from flask import Flask, jsonify, render_template, request, send_from_directory

from webapp import auth, automation, brokers, config, jobs, portfolio, signals, sizing, store

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["JSON_SORT_KEYS"] = False

# Cache do último sinal calculado por ativo (evita rebaixar o yfinance a cada refresh da tela)
_SIGNAL_CACHE: dict = {}
_SIGNAL_LOCK = RLock()
_POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="signal")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def clean(obj):
    """Substitui inf/NaN por None para que o JSON seja sempre válido no navegador."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, float) and (math.isinf(obj) or math.isnan(obj)):
        return None
    return obj


def ok(payload=None, **extra):
    body = {"ok": True}
    if isinstance(payload, dict):
        body.update(payload)
    elif payload is not None:
        body["data"] = payload
    body.update(extra)
    return jsonify(clean(body))


def fail(message: str, status: int = 400):
    return jsonify({"ok": False, "error": str(message)}), status


def require_asset(ticker: str) -> dict:
    asset = store.get_asset(ticker)
    if not asset:
        raise LookupError(f"Ativo {ticker} não está no catálogo.")
    return asset


def asset_signal(asset: dict, force: bool = False) -> dict:
    """Sinal do ativo com cache em memória; devolve o erro embutido em vez de estourar."""
    ticker = asset["ticker"]
    if not force:
        with _SIGNAL_LOCK:
            cached = _SIGNAL_CACHE.get(ticker)
        if cached:
            return cached

    status = signals.model_status(asset)
    if not status["trained"]:
        result = {"available": False, "reason": "untrained",
                  "message": "Modelo ainda não treinado para este ativo."}
        with _SIGNAL_LOCK:
            _SIGNAL_CACHE[ticker] = result
        return result

    try:
        is_holding, buy_price = portfolio.holding_info(asset)
        signal = signals.compute_signal(asset, is_holding=is_holding, buy_price=buy_price, force_refresh=force)
        result = {"available": True, **signal}
    except Exception as exc:
        result = {"available": False, "reason": "error", "message": str(exc)}

    with _SIGNAL_LOCK:
        _SIGNAL_CACHE[ticker] = result
    return result


def asset_view(asset: dict, force: bool = False) -> dict:
    """Objeto completo de um ativo para a interface."""
    return {
        **asset,
        "currency": config.CURRENCY[asset["asset_class"]],
        "currency_symbol": config.CURRENCY_SYMBOL[config.CURRENCY[asset["asset_class"]]],
        "model": signals.model_status(asset),
        "signal": asset_signal(asset, force=force),
        "position": portfolio.get_position(asset),
        "has_report": os.path.exists(config.report_path(asset["ticker"])),
        "available_modes": config.MODES_BY_CLASS[asset["asset_class"]],
        "running_job": jobs.running_job_for(asset["ticker"]),
    }


def last_prices(views: list) -> dict:
    prices = {}
    for view in views:
        signal = view.get("signal") or {}
        if signal.get("available"):
            prices[view["ticker"]] = signal["price"]
    return prices


# --------------------------------------------------------------------------- #
# Páginas e arquivos estáticos
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    return send_from_directory(os.path.join(os.path.dirname(__file__), "templates"), "index.html")


@app.route("/api/session", methods=["DELETE"])
def api_session_logout():
    """Encerra a sessao a partir do proprio painel."""
    from flask import session
    session.clear()
    return ok()


@app.route("/reports/<path:filename>")
def report_file(filename):
    return send_from_directory(config.REPORTS_DIR, filename)


# --------------------------------------------------------------------------- #
# Visão geral
# --------------------------------------------------------------------------- #
@app.route("/api/overview")
def api_overview():
    force = request.args.get("refresh") == "1"
    assets = store.load_assets()

    views = list(_POOL.map(lambda a: asset_view(a, force=force), assets)) if assets else []
    prices = last_prices(views)

    return ok({
        "stocks": [v for v in views if v["asset_class"] == config.CLASS_STOCK],
        "crypto": [v for v in views if v["asset_class"] == config.CLASS_CRYPTO],
        "portfolio": portfolio.summary(prices),
        "automation": automation.status(),
        "settings": store.public_settings(),
        "jobs": jobs.list_jobs(active_only=True),
        "activity": store.load_activity(limit=25),
    })


@app.route("/api/connections")
def api_connections():
    testnet = request.args.get("binance", "testnet") != "real"
    return ok({
        "mt5": brokers.mt5_status(),
        "binance": brokers.binance_status(testnet=testnet),
    })


# --------------------------------------------------------------------------- #
# Ativos
# --------------------------------------------------------------------------- #
@app.route("/api/assets", methods=["GET"])
def api_assets():
    return ok({"assets": [asset_view(a) for a in store.load_assets()]})


@app.route("/api/assets", methods=["POST"])
def api_asset_create():
    payload = request.get_json(force=True, silent=True) or {}
    ticker = str(payload.get("ticker", "")).strip().upper()
    if not ticker:
        return fail("Informe o ticker do ativo (ex.: PETR4.SA ou BTC-USD).")
    try:
        asset = store.upsert_asset(payload)
        store.log_activity("info", f"Ativo {asset['ticker']} salvo no catálogo.", asset["ticker"])
        signals.invalidate_quote_cache(asset["ticker"])
        with _SIGNAL_LOCK:
            _SIGNAL_CACHE.pop(asset["ticker"], None)
        return ok({"asset": asset_view(asset)})
    except Exception as exc:
        return fail(exc)


@app.route("/api/assets/<ticker>", methods=["DELETE"])
def api_asset_delete(ticker):
    if not store.delete_asset(ticker):
        return fail(f"Ativo {ticker} não encontrado.", 404)
    with _SIGNAL_LOCK:
        _SIGNAL_CACHE.pop(ticker.upper(), None)
    store.log_activity("warning", f"Ativo {ticker.upper()} removido do catálogo.", ticker)
    return ok()


@app.route("/api/assets/<ticker>/signal")
def api_asset_signal(ticker):
    try:
        asset = require_asset(ticker)
    except LookupError as exc:
        return fail(exc, 404)
    return ok({"asset": asset_view(asset, force=request.args.get("refresh") == "1")})


@app.route("/api/assets/<ticker>/series")
def api_asset_series(ticker):
    try:
        asset = require_asset(ticker)
        points = int(request.args.get("points", 90))
        return ok({"series": signals.price_series(asset, points=points)})
    except LookupError as exc:
        return fail(exc, 404)
    except Exception as exc:
        return fail(exc)


@app.route("/api/assets/<ticker>/train", methods=["POST"])
def api_asset_train(ticker):
    payload = request.get_json(force=True, silent=True) or {}
    try:
        asset = require_asset(ticker)
        job = jobs.start_training(
            asset,
            episodes=int(payload.get("episodes", 20)),
            batch_size=int(payload.get("batch_size", 32)),
            capital=float(payload["capital"]) if payload.get("capital") else None,
        )
        return ok({"job": job})
    except LookupError as exc:
        return fail(exc, 404)
    except RuntimeError as exc:
        return fail(exc, 409)
    except Exception as exc:
        return fail(exc)


@app.route("/api/assets/<ticker>/run", methods=["POST"])
def api_asset_run(ticker):
    payload = request.get_json(force=True, silent=True) or {}
    try:
        asset = require_asset(ticker)
        mode = payload.get("mode") or asset["automation"]["mode"]
        if mode not in config.MODES_BY_CLASS[asset["asset_class"]]:
            return fail(f"Modo '{mode}' não é válido para {asset['asset_class']}.")

        quantity = payload.get("quantity")
        if quantity is not None:
            quantity = float(quantity)
            if quantity <= 0:
                return fail("O tamanho da ordem precisa ser maior que zero.")

        force_action = payload.get("force_action")
        if force_action is not None:
            force_action = int(force_action)
            # Só venda: o encerramento manual existe para reduzir exposição.
            if force_action != 2:
                return fail("Só o encerramento de posição pode ser forçado manualmente.")

        result = automation.run_cycle(asset, mode=mode, manual=True,
                                      quantity=quantity, force_action=force_action)
        with _SIGNAL_LOCK:
            _SIGNAL_CACHE.pop(asset["ticker"], None)
        return ok({"result": result, "asset": asset_view(store.get_asset(ticker))})
    except LookupError as exc:
        return fail(exc, 404)
    except Exception as exc:
        return fail(exc)


@app.route("/api/assets/<ticker>/sizing")
def api_asset_sizing(ticker):
    """
    Tamanho de ordem sugerido para o ativo, com todo o embasamento que o gerou.

    A evidência vem do teste cego do próprio modelo. Se ele foi treinado antes
    de o painel passar a guardar métricas, o backtest é reexecutado uma vez a
    partir do .pt salvo (`compute=1`, que é o padrão) e o resultado fica gravado.
    """
    try:
        asset = require_asset(ticker)
    except LookupError as exc:
        return fail(exc, 404)

    signal = asset_signal(asset)
    if not signal.get("available"):
        return fail(signal.get("message", "Sinal indisponível para este ativo."), 409)

    price = float(signal["price"])
    currency = config.CURRENCY[asset["asset_class"]]
    account = portfolio.summary({asset["ticker"]: price})[currency]

    entry = sizing.metrics_for(asset, compute_if_missing=request.args.get("compute", "1") == "1")
    result = sizing.suggest(asset, price=price, equity=account["equity"],
                            cash=account["cash"], entry=entry)

    return ok({
        "sizing": result,
        "configured_quantity": asset["quantity"],
        "currency": currency,
        "currency_symbol": config.CURRENCY_SYMBOL[currency],
    })


@app.route("/api/assets/<ticker>/automation", methods=["PUT"])
def api_asset_automation(ticker):
    payload = request.get_json(force=True, silent=True) or {}
    patch = {}
    if "enabled" in payload:
        patch["enabled"] = bool(payload["enabled"])
    if "mode" in payload:
        patch["mode"] = payload["mode"]
    if "interval_minutes" in payload:
        patch["interval_minutes"] = max(1, int(payload["interval_minutes"]))

    try:
        asset = require_asset(ticker)
        if patch.get("mode") and patch["mode"] not in config.MODES_BY_CLASS[asset["asset_class"]]:
            return fail(f"Modo '{patch['mode']}' não é válido para este tipo de ativo.")

        mode = patch.get("mode", asset["automation"]["mode"])
        if patch.get("enabled"):
            # Conta demo do MT5 não é dinheiro real e não precisa da trava.
            required, motivo = brokers.needs_real_money_unlock(mode)
            if required and not store.load_settings().get("allow_real_money"):
                return fail(f"Automação bloqueada: {motivo}. Libere a trava de dinheiro real "
                            f"em Configurações, ou use conta demo/Testnet.", 403)

        updated = store.update_automation(ticker, patch)
        if "enabled" in patch:
            estado = "ligada" if patch["enabled"] else "desligada"
            store.log_activity("info", f"Automação {estado} para {updated['ticker']} (modo {mode}).", ticker)
        return ok({"asset": asset_view(updated)})
    except LookupError as exc:
        return fail(exc, 404)
    except Exception as exc:
        return fail(exc)


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
@app.route("/api/jobs")
def api_jobs():
    return ok({"jobs": jobs.list_jobs(active_only=request.args.get("active") == "1")})


@app.route("/api/jobs/<job_id>")
def api_job(job_id):
    job = jobs.get_job(job_id, log_from=int(request.args.get("log_from", 0)))
    if not job:
        return fail("Job não encontrado.", 404)
    return ok({"job": job})


@app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
def api_job_cancel(job_id):
    if not jobs.cancel_job(job_id):
        return fail("Job não está em execução.", 409)
    return ok()


# --------------------------------------------------------------------------- #
# Carteira e histórico
# --------------------------------------------------------------------------- #
@app.route("/api/portfolio")
def api_portfolio():
    views = [asset_view(a) for a in store.load_assets()]
    return ok({"portfolio": portfolio.summary(last_prices(views))})


@app.route("/api/portfolio/<currency>/reset", methods=["POST"])
def api_portfolio_reset(currency):
    payload = request.get_json(force=True, silent=True) or {}
    default = 1000.0 if currency.upper() == "USDT" else 10000.0
    try:
        account = portfolio.reset_account(currency.upper(), float(payload.get("initial_cash", default)))
        store.log_activity("warning", f"Carteira simulada {currency.upper()} reiniciada "
                                      f"com {account['initial_cash']:,.2f}.")
        return ok({"account": account})
    except Exception as exc:
        return fail(exc)


@app.route("/api/portfolio/<currency>/deposit", methods=["POST"])
def api_portfolio_deposit(currency):
    payload = request.get_json(force=True, silent=True) or {}
    try:
        amount = float(payload.get("amount", 0))
        if amount <= 0:
            return fail("Informe um valor positivo.")
        account = portfolio.deposit(currency.upper(), amount)
        store.log_activity("info", f"Aporte de {amount:,.2f} na carteira simulada {currency.upper()}.")
        return ok({"account": account})
    except Exception as exc:
        return fail(exc)


@app.route("/api/history")
def api_history():
    currency = request.args.get("currency")
    return ok({"history": portfolio.history(currency=currency, limit=int(request.args.get("limit", 100)))})


@app.route("/api/activity")
def api_activity():
    return ok({"activity": store.load_activity(
        limit=int(request.args.get("limit", 100)),
        ticker=request.args.get("ticker"),
    )})


# --------------------------------------------------------------------------- #
# Configurações e automação global
# --------------------------------------------------------------------------- #
@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    return ok({"settings": store.public_settings()})


@app.route("/api/settings", methods=["POST"])
def api_settings_post():
    payload = request.get_json(force=True, silent=True) or {}
    patch = {}
    for key in ("binance_api_key", "binance_secret_key"):
        if payload.get(key):  # string vazia não apaga a chave já salva
            patch[key] = str(payload[key]).strip()
    if "allow_real_money" in payload:
        patch["allow_real_money"] = bool(payload["allow_real_money"])
    if "quote_cache_minutes" in payload:
        patch["quote_cache_minutes"] = max(1, int(payload["quote_cache_minutes"]))
    if payload.get("clear_binance_keys"):
        patch["binance_api_key"] = ""
        patch["binance_secret_key"] = ""

    store.save_settings(patch)
    brokers.invalidate_binance_clients()
    if "allow_real_money" in patch:
        estado = "LIBERADA" if patch["allow_real_money"] else "bloqueada"
        store.log_activity("warning", f"Trava de dinheiro real {estado}.")
    return ok({"settings": store.public_settings()})


@app.route("/api/automation/master", methods=["POST"])
def api_automation_master():
    payload = request.get_json(force=True, silent=True) or {}
    enabled = bool(payload.get("enabled"))
    store.save_settings({"automation_master_enabled": enabled})
    store.log_activity("warning" if enabled else "info",
                       f"Chave-geral da automação {'LIGADA' if enabled else 'DESLIGADA'}.")
    return ok({"automation": automation.status()})


@app.route("/api/automation/panic", methods=["POST"])
def api_automation_panic():
    """Botão de pânico: desliga a chave-geral e a automação de todos os ativos."""
    store.save_settings({"automation_master_enabled": False})
    for asset in store.load_assets():
        if asset["automation"].get("enabled"):
            store.update_automation(asset["ticker"], {"enabled": False, "next_run": None})
    store.log_activity("warning", "PARADA DE EMERGÊNCIA: toda a automação foi desligada.")
    return ok({"automation": automation.status()})


# --------------------------------------------------------------------------- #
# Bootstrap
# --------------------------------------------------------------------------- #
def create_app() -> Flask:
    config.ensure_dirs()
    store.load_assets()      # cria data/assets.json na primeira execução
    auth.registrar(app)      # exige login em tudo, inclusive /api
    automation.start()
    return app
