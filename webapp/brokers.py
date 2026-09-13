"""
brokers.py - Adaptadores de corretora usados pelos modos de execução ao vivo.

- MetaTrader 5 (ações da B3): reaproveita src/mt5_executor.py.
- Binance Spot (cripto, Testnet ou conta real): usa python-binance.

As bibliotecas são importadas sob demanda: o painel continua funcionando
normalmente em uma máquina sem MetaTrader 5 instalado ou sem chaves da Binance.
"""

import threading
import time

from webapp import config, store

_MT5_LOCK = threading.RLock()
_BINANCE_LOCK = threading.RLock()
_binance_clients: dict = {}
_binance_synced_at: dict = {}

# Ressincroniza o relógio a cada 5 min: um robô em loop roda por horas e o
# relógio da máquina volta a derivar.
BINANCE_SYNC_INTERVAL = 300
# Margem para ficar atrás do servidor, dentro da janela tolerada.
BINANCE_SAFETY_MS = 500


# --------------------------------------------------------------------------- #
# MetaTrader 5 (Ações B3)
# --------------------------------------------------------------------------- #
def mt5_status() -> dict:
    """Estado da conexão com o terminal MetaTrader 5 (nunca levanta exceção)."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {"available": False, "connected": False,
                "message": "Biblioteca MetaTrader5 não instalada (pip install MetaTrader5)."}

    with _MT5_LOCK:
        try:
            if not mt5.initialize():
                return {"available": True, "connected": False,
                        "message": f"MetaTrader 5 não respondeu: {mt5.last_error()}. Abra o terminal e faça login."}
            info = mt5.account_info()
            if info is None:
                return {"available": True, "connected": False,
                        "message": "Terminal aberto, mas nenhuma conta logada."}
            return {
                "available": True,
                "connected": True,
                "login": info.login,
                "server": info.server,
                "demo": info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO,
                "balance": float(info.balance),
                "equity": float(info.equity),
                "message": "Conectado ao MetaTrader 5.",
            }
        except Exception as exc:  # pragma: no cover - depende do terminal local
            return {"available": True, "connected": False, "message": f"Erro no MetaTrader 5: {exc}"}
        finally:
            try:
                mt5.shutdown()
            except Exception:
                pass


def mt5_execute(asset: dict, action: int, quantity: float = None) -> dict:
    """Envia a ordem correspondente à ação da IA para o MetaTrader 5."""
    try:
        import MetaTrader5 as mt5
        from src.mt5_executor import connect_mt5, get_mt5_positions, send_buy_order, send_close_position
    except ImportError as exc:
        return {"executed": False, "type": "none", "message": f"MetaTrader5 indisponível: {exc}"}

    symbol = asset.get("broker_symbol") or config.clean_ticker(asset["ticker"])
    volume = float(quantity) if quantity is not None else float(asset["quantity"])

    with _MT5_LOCK:
        try:
            if not connect_mt5():
                return {"executed": False, "type": "none",
                        "message": "Não foi possível conectar ao MetaTrader 5 (terminal aberto? AlgoTrading ligado?)."}

            positions = get_mt5_positions(symbol)
            is_holding = len(positions) > 0

            if action == 1 and not is_holding:
                ok = send_buy_order(symbol=symbol, volume=volume)
                return {"executed": ok, "type": "buy" if ok else "none",
                        "message": f"Ordem de COMPRA de {volume:g} {symbol} enviada ao MT5."
                                   if ok else f"Falha ao enviar compra de {symbol} no MT5."}

            if action == 2 and is_holding:
                closed = [send_close_position(p) for p in positions]
                ok = any(closed)
                return {"executed": ok, "type": "sell" if ok else "none",
                        "message": f"{sum(1 for c in closed if c)} posição(ões) de {symbol} encerrada(s) no MT5."
                                   if ok else f"Falha ao encerrar posições de {symbol} no MT5."}

            estado = "comprado" if is_holding else "em caixa"
            return {"executed": False, "type": "none",
                    "message": f"Nenhuma ordem necessária em {symbol} (posição atual: {estado})."}
        except Exception as exc:  # pragma: no cover - depende do terminal local
            return {"executed": False, "type": "none", "message": f"Erro no MT5: {exc}"}
        finally:
            try:
                mt5.shutdown()
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Binance (Cripto)
# --------------------------------------------------------------------------- #
def _binance_client(testnet: bool):
    from binance.client import Client

    settings = store.load_settings()
    api_key = settings.get("binance_api_key", "")
    secret_key = settings.get("binance_secret_key", "")
    if not api_key or not secret_key:
        raise ValueError("Chaves da Binance não configuradas (aba Configurações).")

    cache_key = (api_key, testnet)
    with _BINANCE_LOCK:
        client = _binance_clients.get(cache_key)
        if client is None:
            client = Client(api_key, secret_key, testnet=testnet)
            if testnet:
                client.API_URL = "https://testnet.binance.vision/api"
            _binance_clients[cache_key] = client
        sync_binance_time(client)
        return client


def sync_binance_time(client, force: bool = False):
    """
    Alinha o relógio usado nas requisições assinadas com o da Binance.

    A Binance rejeita qualquer requisição assinada cujo timestamp esteja mais de
    1000 ms ADIANTADO em relação ao servidor dela (erro -1021), e `recvWindow`
    não cobre esse caso — ele só tolera atraso. Como o python-binance usa o
    relógio local puro (`timestamp_offset` nasce zerado e ele nunca sincroniza),
    qualquer desvio do relógio do Windows derruba todas as ordens.

    Aqui medimos o desvio e deixamos o cliente propositalmente alguns
    milissegundos ATRÁS do servidor, que é o lado seguro da janela.
    """
    key = id(client)
    if not force and (time.time() - _binance_synced_at.get(key, 0)) < BINANCE_SYNC_INTERVAL:
        return

    before = time.time() * 1000
    server_time = client.get_server_time()["serverTime"]
    after = time.time() * 1000

    # Ponto médio da chamada: desconta metade da latência da ida e volta.
    local_time = (before + after) / 2
    client.timestamp_offset = int(server_time - local_time) - BINANCE_SAFETY_MS
    _binance_synced_at[key] = time.time()


def _with_time_retry(client, call):
    """
    Executa a chamada e, se a Binance recusar por timestamp (-1021), ressincroniza
    e tenta uma única vez.

    Repetir é seguro justamente nesse código: a Binance valida o timestamp e a
    assinatura antes de encaminhar qualquer coisa ao livro de ofertas, então uma
    requisição recusada com -1021 não chegou a virar ordem.
    """
    from binance.exceptions import BinanceAPIError

    try:
        return call()
    except BinanceAPIError as exc:
        if getattr(exc, "code", None) != -1021:
            raise
        sync_binance_time(client, force=True)
        return call()


def invalidate_binance_clients():
    with _BINANCE_LOCK:
        _binance_clients.clear()
        _binance_synced_at.clear()


def binance_status(testnet: bool = True) -> dict:
    """Estado da conexão com a Binance e saldos relevantes (nunca levanta exceção)."""
    try:
        import binance  # noqa: F401
    except ImportError:
        return {"available": False, "connected": False,
                "message": "Biblioteca python-binance não instalada."}

    try:
        client = _binance_client(testnet)
        account = _with_time_retry(client, client.get_account)
        balances = {
            b["asset"]: float(b["free"])
            for b in account["balances"]
            if float(b["free"]) > 0
        }
        return {
            "available": True,
            "connected": True,
            "testnet": testnet,
            "balances": dict(sorted(balances.items(), key=lambda kv: -kv[1])[:10]),
            "usdt": balances.get("USDT", 0.0),
            "message": f"Conectado à Binance {'Testnet' if testnet else 'REAL'}.",
        }
    except Exception as exc:
        return {"available": True, "connected": False, "testnet": testnet, "message": f"Binance: {exc}"}


def binance_execute(asset: dict, action: int, price: float, testnet: bool = True,
                    quantity: float = None) -> dict:
    """Envia ordem a mercado na Binance conforme a ação da IA."""
    from binance.client import Client

    symbol = asset.get("broker_symbol") or (config.clean_ticker(asset["ticker"]).replace("_USD", "USDT"))
    base_asset = symbol.replace("USDT", "")
    # valor da ordem em USDT
    trade_amount = float(quantity) if quantity is not None else float(asset["quantity"])

    try:
        client = _binance_client(testnet)
        usdt_balance = float(_with_time_retry(
            client, lambda: client.get_asset_balance(asset="USDT"))["free"])
        crypto_balance = float(_with_time_retry(
            client, lambda: client.get_asset_balance(asset=base_asset))["free"])
        is_holding = (crypto_balance * price) > 10.0

        if action == 1:
            if is_holding:
                return {"executed": False, "type": "none",
                        "message": f"Já posicionado em {base_asset} na Binance."}
            if usdt_balance < trade_amount:
                return {"executed": False, "type": "none",
                        "message": f"Saldo USDT insuficiente na Binance ($ {usdt_balance:,.2f} < $ {trade_amount:,.2f})."}
            order = _with_time_retry(client, lambda: client.create_order(
                symbol=symbol,
                side=Client.SIDE_BUY,
                type=Client.ORDER_TYPE_MARKET,
                quoteOrderQty=trade_amount,
            ))
            return {"executed": True, "type": "buy", "order_id": order.get("orderId"),
                    "message": f"COMPRA de $ {trade_amount:,.2f} em {symbol} executada na Binance "
                               f"({'Testnet' if testnet else 'REAL'}). Order #{order.get('orderId')}."}

        if action == 2:
            if not is_holding or crypto_balance <= 0.0001:
                return {"executed": False, "type": "none",
                        "message": f"Nenhum saldo relevante de {base_asset} para vender."}
            qty = round(crypto_balance, 5)
            order = _with_time_retry(client, lambda: client.create_order(
                symbol=symbol,
                side=Client.SIDE_SELL,
                type=Client.ORDER_TYPE_MARKET,
                quantity=qty,
            ))
            return {"executed": True, "type": "sell", "order_id": order.get("orderId"),
                    "message": f"VENDA de {qty} {base_asset} executada na Binance "
                               f"({'Testnet' if testnet else 'REAL'}). Order #{order.get('orderId')}."}

        estado = f"comprado em {base_asset}" if is_holding else "líquido em USDT"
        return {"executed": False, "type": "none",
                "message": f"Nenhuma ordem necessária em {symbol} (posição atual: {estado})."}

    except Exception as exc:
        return {"executed": False, "type": "none", "message": f"Erro na Binance: {exc}"}


# --------------------------------------------------------------------------- #
# Roteamento por modo
# --------------------------------------------------------------------------- #
def execute_live(asset: dict, action: int, price: float, mode: str,
                 quantity: float = None) -> dict:
    """Executa a ação no destino escolhido, respeitando a trava de dinheiro real."""
    if mode in config.REAL_MONEY_MODES and not store.load_settings().get("allow_real_money", False):
        return {"executed": False, "type": "none",
                "message": "Modo de dinheiro real bloqueado. Libere a trava em Configurações antes de operar ao vivo."}

    if mode == config.MODE_MT5:
        return mt5_execute(asset, action, quantity=quantity)
    if mode == config.MODE_BINANCE_TEST:
        return binance_execute(asset, action, price, testnet=True, quantity=quantity)
    if mode == config.MODE_BINANCE_REAL:
        return binance_execute(asset, action, price, testnet=False, quantity=quantity)
    raise ValueError(f"Modo de execução desconhecido: {mode}")
