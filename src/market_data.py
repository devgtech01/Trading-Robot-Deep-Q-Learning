"""
market_data.py - Download de candles diários (OHLCV), seguro para uso em threads.

Por que este módulo existe
--------------------------
`yfinance.download()` guarda o resultado de cada chamada em dicionários globais
do módulo (`yfinance.shared._DFS` / `_ERRORS`). Quando o painel pede o sinal de
vários ativos ao mesmo tempo (o servidor usa um ThreadPoolExecutor), as chamadas
concorrentes sobrescrevem umas às outras e cada thread recebe o histórico de
OUTRO ativo — o painel passa a mostrar o preço do BTC na linha da PETR4, o sinal
da rede é calculado sobre a série errada e a carteira simulada registra a compra
pelo preço errado.

`yfinance.Ticker(...).history()` não usa esse estado global e é seguro em
paralelo. Um lock adicional serializa as requisições, o que também evita o
rate-limit do Yahoo quando são 8+ ativos de uma vez.
"""

import threading
import time

import pandas as pd
import yfinance as yf

_DOWNLOAD_LOCK = threading.RLock()
OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def download_ohlcv(ticker: str, start_date: str, end_date: str = None,
                   interval: str = "1d", retries: int = 2) -> pd.DataFrame:
    """
    Baixa o histórico diário do ativo e devolve um DataFrame com as colunas
    Open/High/Low/Close/Volume e índice de datas sem fuso horário.

    Levanta ValueError se o Yahoo não devolver nenhuma barra para o ticker.
    """
    last_error = None
    for attempt in range(retries + 1):
        try:
            with _DOWNLOAD_LOCK:
                df = yf.Ticker(ticker).history(
                    start=start_date, end=end_date, interval=interval,
                    auto_adjust=True, actions=False, raise_errors=False,
                )
            if df is not None and not df.empty:
                break
        except Exception as exc:  # rede instável, rate-limit momentâneo etc.
            last_error = exc
            df = None
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))

    if df is None or df.empty:
        extra = f" ({last_error})" if last_error else ""
        raise ValueError(
            f"Não foram encontrados dados para o ticker {ticker}{extra}. "
            f"Confira o código (ações da B3 terminam em .SA, cripto usa o formato BTC-USD) "
            f"e a conexão com a internet."
        )

    # O Yahoo devolve MultiIndex em algumas versões e sempre um índice com fuso
    # horário (America/Sao_Paulo para B3, UTC para cripto). O restante do projeto
    # compara datas sem fuso (split_date, gráficos), então normalizamos aqui.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df.index = df.index.normalize()
    df.index.name = "Date"

    missing = [c for c in OHLCV if c not in df.columns]
    if missing:
        raise ValueError(f"Retorno incompleto do Yahoo para {ticker}: faltam {missing}.")

    return df[OHLCV].copy()
