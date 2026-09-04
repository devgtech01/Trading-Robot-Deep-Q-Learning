"""
crypto_data.py - Módulo para download e preparação de séries temporais de Criptomoedas (24/7).
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calcula o RSI (Índice de Força Relativa)."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def load_crypto_data(
    ticker: str = "BTC-USD",
    start_date: str = "2019-01-01",
    end_date: str = None
) -> pd.DataFrame:
    """
    Baixa os dados históricos de uma Criptomoeda e calcula indicadores técnicos adaptados à alta volatilidade.
    """
    if end_date is None:
        end_date = datetime.today().strftime("%Y-%m-%d")

    print(f"[*] Baixando dados para {ticker} de {start_date} até {end_date} (Mercado Cripto 24/7)...")
    df = yf.download(ticker, start=start_date, end=end_date, progress=False)

    if df.empty:
        raise ValueError(f"Não foram encontrados dados para o par {ticker}.")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.dropna(inplace=True)

    # Indicadores técnicos para Cripto
    df["Return_1d"] = df["Close"].pct_change().fillna(0)
    df["Return_5d"] = df["Close"].pct_change(5).fillna(0)
    df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["SMA_21"] = df["Close"].rolling(window=21).mean().bfill()
    df["Dist_SMA21"] = (df["Close"] - df["SMA_21"]) / (df["SMA_21"] + 1e-9)
    df["RSI_14"] = compute_rsi(df["Close"], period=14) / 100.0  # Normalizado 0 a 1

    # Bandas de Bollinger (20 períodos, 2 desvios padrão)
    sma_20 = df["Close"].rolling(20).mean()
    std_20 = df["Close"].rolling(20).std()
    upper_band = sma_20 + (2 * std_20)
    lower_band = sma_20 - (2 * std_20)
    # Posição percentual dentro das bandas (%B)
    df["Bollinger_PctB"] = ((df["Close"] - lower_band) / (upper_band - lower_band + 1e-9)).fillna(0.5)

    # Volatilidade de 14 períodos
    df["Volatility_14"] = df["Return_1d"].rolling(14).std().fillna(0)

    df.dropna(inplace=True)
    return df


def split_crypto_train_test(
    df: pd.DataFrame,
    split_date: str = "2024-01-01"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Divide a série histórica de Cripto em Treino e Teste Cego (Out-of-Sample).
    """
    split_dt = pd.to_datetime(split_date)
    train_df = df[df.index < split_dt].copy()
    test_df = df[df.index >= split_dt].copy()

    print(f"[+] Divisão Cripto concluída:")
    print(f"    - Treino: {train_df.index[0].strftime('%Y-%m-%d')} até {train_df.index[-1].strftime('%Y-%m-%d')} ({len(train_df)} dias/barras)")
    print(f"    - Teste Cego: {test_df.index[0].strftime('%Y-%m-%d')} até {test_df.index[-1].strftime('%Y-%m-%d')} ({len(test_df)} dias/barras)")

    return train_df, test_df
