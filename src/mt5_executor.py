"""
mt5_executor.py - Módulo para execução de ordens automatizadas no MetaTrader 5 (B3).
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np


def connect_mt5(path: str = None) -> bool:
    """Inicializa a conexão com o MetaTrader 5 instalado."""
    if path:
        initialized = mt5.initialize(path=path)
    else:
        initialized = mt5.initialize()

    if not initialized:
        print(f"[-] Falha ao inicializar o MetaTrader 5. Código de erro: {mt5.last_error()}")
        return False

    account_info = mt5.account_info()
    if account_info is None:
        print("[-] Nenhuma conta conectada no MetaTrader 5.")
        return False

    print("\n" + "=" * 55)
    print("       METATRADER 5 CONECTADO COM SUCESSO!")
    print("=" * 55)
    print(f"  Conta/Login:       {account_info.login}")
    print(f"  Servidor:          {account_info.server}")
    print(f"  Modo da Conta:     {'DEMO / SIMULADOR' if account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else 'PRODUÇÃO / REAL'}")
    print(f"  Saldo em Conta:    R$ {account_info.balance:,.2f}")
    print(f"  Patrimônio Líq.:   R$ {account_info.equity:,.2f}")
    print("=" * 55 + "\n")
    return True


def get_mt5_positions(symbol: str) -> list:
    """Retorna as posições abertas para um determinado ativo."""
    # Trata símbolo com ou sem sufixo fracionário
    positions = mt5.positions_get(symbol=symbol)
    if positions is None or len(positions) == 0:
        # Tenta versão fracionária (ex: PETR4F)
        if not symbol.endswith("F"):
            positions = mt5.positions_get(symbol=symbol + "F")
    return list(positions) if positions else []


def send_buy_order(symbol: str, volume: float = 100.0, slippage: int = 10) -> bool:
    """Envia uma ordem de compra a mercado no MetaTrader 5."""
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        # Tenta com sufixo fracionário se volume < 100
        if volume < 100 and not symbol.endswith("F"):
            symbol = symbol + "F"
            symbol_info = mt5.symbol_info(symbol)

    if symbol_info is None or not symbol_info.visible:
        if not mt5.symbol_select(symbol, True):
            print(f"[-] Símbolo {symbol} não encontrado no MT5.")
            return False

    price = mt5.symbol_info_tick(symbol).ask
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "deviation": slippage,
        "magic": 123456,
        "comment": "DQN Trading Robot Buy",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }

    print(f"[*] Enviando ordem de COMPRA: {volume} un. de {symbol} a R$ {price:.2f}...")
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[-] Falha na ordem de compra. Retcode: {result.retcode} - {result.comment}")
        return False

    print(f"[+] COMPRA EXECUTADA COM SUCESSO! Ticket #{result.order} - Preço: R$ {result.price:.2f}")
    return True


def send_close_position(position) -> bool:
    """Encerra uma posição existente no MetaTrader 5."""
    symbol = position.symbol
    price = mt5.symbol_info_tick(symbol).bid
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(position.volume),
        "type": mt5.ORDER_TYPE_SELL,
        "position": position.ticket,
        "price": price,
        "deviation": 10,
        "magic": 123456,
        "comment": "DQN Trading Robot Close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }

    print(f"[*] Enviando ordem de VENDA para fechar Ticket #{position.ticket} ({position.volume} un. de {symbol})...")
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[-] Falha ao fechar posição. Retcode: {result.retcode} - {result.comment}")
        return False

    profit = position.profit
    print(f"[+] POSIÇÃO ENCERRADA! Lucro/Prejuízo: R$ {profit:+,.2f}")
    return True
