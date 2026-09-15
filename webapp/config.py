"""
config.py - Caminhos, constantes e catálogo padrão de ativos do painel.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODELS_DIR = os.path.join(BASE_DIR, "models")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

ASSETS_FILE = os.path.join(DATA_DIR, "assets.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
ACTIVITY_FILE = os.path.join(DATA_DIR, "activity_log.json")
WALLET_FILE = os.path.join(DATA_DIR, "paper_wallet.json")

WINDOW_SIZE = 5

# Classes de ativo
CLASS_STOCK = "stock"    # Ações / ETFs da B3 (MetaTrader 5)
CLASS_CRYPTO = "crypto"  # Criptomoedas (Binance)

# Features usadas por cada classe (espelham src/environment.py e src/crypto_env.py)
FEATURES_STOCK = ["Return_1d", "Return_5d", "Dist_SMA21", "RSI_14", "Volatility_10"]
FEATURES_CRYPTO = ["Return_1d", "Return_5d", "Dist_SMA21", "RSI_14", "Bollinger_PctB", "Volatility_14"]

# Custos operacionais simulados
FEE_STOCK = 0.0003   # 0,03% B3 + corretagem média
FEE_CRYPTO = 0.001   # 0,10% padrão de exchange

CURRENCY = {CLASS_STOCK: "BRL", CLASS_CRYPTO: "USDT"}
CURRENCY_SYMBOL = {"BRL": "R$", "USDT": "$"}

# Modos de execução da automação
MODE_SIGNAL = "signal"            # Apenas registra o sinal (nenhuma ordem)
MODE_PAPER = "paper"              # Carteira simulada local
MODE_MT5 = "mt5"                  # Envia ordem ao MetaTrader 5 (ações)
MODE_BINANCE_TEST = "binance_testnet"
MODE_BINANCE_REAL = "binance_real"

# A MetaQuotes publica a biblioteca MetaTrader5 apenas para Windows -- nao existe
# nenhuma versao para Linux. Numa VPS Linux o modo MT5 so poderia falhar, entao
# ele nem aparece como opcao: ações continuam com sinal e carteira simulada.
MT5_SUPORTADO = sys.platform == "win32"

MODES_BY_CLASS = {
    CLASS_STOCK: [MODE_SIGNAL, MODE_PAPER] + ([MODE_MT5] if MT5_SUPORTADO else []),
    CLASS_CRYPTO: [MODE_SIGNAL, MODE_PAPER, MODE_BINANCE_TEST, MODE_BINANCE_REAL],
}

LIVE_MODES = {MODE_MT5, MODE_BINANCE_TEST, MODE_BINANCE_REAL}
REAL_MONEY_MODES = {MODE_MT5, MODE_BINANCE_REAL}

ACTION_LABELS = {0: "AGUARDAR", 1: "COMPRAR", 2: "VENDER"}

# Catálogo inicial (é gravado em data/assets.json na primeira execução e depois editável pela UI)
DEFAULT_ASSETS = [
    # --- Ações e ETFs da B3 ---
    {"ticker": "PETR4.SA", "name": "Petrobras PN", "asset_class": CLASS_STOCK,
     "broker_symbol": "PETR4", "quantity": 100, "start_date": "2018-01-01", "split_date": "2023-01-01"},
    {"ticker": "VALE3.SA", "name": "Vale ON", "asset_class": CLASS_STOCK,
     "broker_symbol": "VALE3", "quantity": 100, "start_date": "2018-01-01", "split_date": "2023-01-01"},
    {"ticker": "WEGE3.SA", "name": "WEG ON", "asset_class": CLASS_STOCK,
     "broker_symbol": "WEGE3", "quantity": 100, "start_date": "2018-01-01", "split_date": "2023-01-01"},
    {"ticker": "ITUB4.SA", "name": "Itaú Unibanco PN", "asset_class": CLASS_STOCK,
     "broker_symbol": "ITUB4", "quantity": 100, "start_date": "2018-01-01", "split_date": "2023-01-01"},
    {"ticker": "BOVA11.SA", "name": "ETF Ibovespa", "asset_class": CLASS_STOCK,
     "broker_symbol": "BOVA11", "quantity": 10, "start_date": "2018-01-01", "split_date": "2023-01-01"},
    # --- Criptomoedas ---
    {"ticker": "BTC-USD", "name": "Bitcoin", "asset_class": CLASS_CRYPTO,
     "broker_symbol": "BTCUSDT", "quantity": 100.0, "start_date": "2019-01-01", "split_date": "2024-01-01"},
    {"ticker": "ETH-USD", "name": "Ethereum", "asset_class": CLASS_CRYPTO,
     "broker_symbol": "ETHUSDT", "quantity": 100.0, "start_date": "2019-01-01", "split_date": "2024-01-01"},
    {"ticker": "SOL-USD", "name": "Solana", "asset_class": CLASS_CRYPTO,
     "broker_symbol": "SOLUSDT", "quantity": 100.0, "start_date": "2019-01-01", "split_date": "2024-01-01"},
]

DEFAULT_SETTINGS = {
    "automation_master_enabled": False,
    "binance_api_key": "",
    "binance_secret_key": "",
    "allow_real_money": False,     # trava de segurança para modos de dinheiro real
    "quote_cache_minutes": 15,
    "password_hash": "",           # hash da senha do painel (nunca a senha)
    "secret_key": "",              # assina os cookies de sessão; criado no 1º uso
}


def clean_ticker(ticker: str) -> str:
    """Converte o ticker de mercado no nome usado nos arquivos de modelo/relatório."""
    return ticker.replace(".SA", "").replace("-", "_").replace("/", "_").upper()


def model_path(ticker: str) -> str:
    return os.path.join(MODELS_DIR, f"{clean_ticker(ticker)}_dqn.pt")


def report_path(ticker: str) -> str:
    return os.path.join(REPORTS_DIR, f"{clean_ticker(ticker)}_backtest_report.png")


def guess_class(ticker: str) -> str:
    """Deduz se um ticker é cripto ou ação a partir do formato."""
    t = ticker.upper()
    if t.endswith(".SA") or t.endswith(".SAO"):
        return CLASS_STOCK
    if "-USD" in t or t.endswith("USDT") or t.endswith("-BRL"):
        return CLASS_CRYPTO
    return CLASS_STOCK


def ensure_dirs():
    for d in (DATA_DIR, MODELS_DIR, REPORTS_DIR):
        os.makedirs(d, exist_ok=True)
