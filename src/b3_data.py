"""
b3_data.py - Módulo para download e preparação de séries temporais da B3.
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calcula o RSI (Índice de Força Relativa) clássico de Wilder."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def load_b3_data(
    ticker: str = "PETR4.SA",
    start_date: str = "2018-01-01",
    end_date: str = None
) -> pd.DataFrame:
    """
    Baixa os dados históricos de uma ação da B3 e calcula indicadores técnicos.
    """
    if end_date is None:
        end_date = datetime.today().strftime("%Y-%m-%d")

    print(f"[*] Baixando dados para {ticker} de {start_date} até {end_date}...")
    df = yf.download(ticker, start=start_date, end=end_date, progress=False)

    if df.empty:
        raise ValueError(f"Não foram encontrados dados para o ticker {ticker}.")

    # Formatação das colunas para lidar com MultiIndex do yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.dropna(inplace=True)

    # Indicadores técnicos para auxiliar a tomada de decisão em Swing Trade
    df["Return_1d"] = df["Close"].pct_change().fillna(0)
    df["Return_5d"] = df["Close"].pct_change(5).fillna(0)
    df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["SMA_21"] = df["Close"].rolling(window=21).mean().bfill()
    df["Dist_SMA21"] = (df["Close"] - df["SMA_21"]) / (df["SMA_21"] + 1e-9)
    df["RSI_14"] = compute_rsi(df["Close"], period=14) / 100.0  # Normalizado entre 0 e 1

    # Volatilidade normalizada (True Range simplificado)
    df["Volatility_10"] = df["Return_1d"].rolling(10).std().fillna(0)

    # Remove valores nulos gerados pelas janelas móveis
    df.dropna(inplace=True)
    return df


def split_train_test(
    df: pd.DataFrame,
    split_date: str = "2023-01-01"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Divide a série temporal em dados de Treino (In-Sample) e Teste Cego (Out-of-Sample).
    """
    split_dt = pd.to_datetime(split_date)
    train_df = df[df.index < split_dt].copy()
    test_df = df[df.index >= split_dt].copy()

    print(f"[+] Divisão concluída:")
    print(f"    - Treino: {train_df.index[0].strftime('%Y-%m-%d')} até {train_df.index[-1].strftime('%Y-%m-%d')} ({len(train_df)} barras)")
    print(f"    - Teste Cego: {test_df.index[0].strftime('%Y-%m-%d')} até {test_df.index[-1].strftime('%Y-%m-%d')} ({len(test_df)} barras)")

    return train_df, test_df
