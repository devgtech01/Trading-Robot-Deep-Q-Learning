"""
binance_bot.py - Robô Automatizado para execução direta na Binance (Spot Testnet e Real).
"""

import os
import time
import argparse
from datetime import datetime
import numpy as np
import torch
from binance.client import Client

from src.crypto_data import load_crypto_data
from src.dqn_agent import DQNAgent


def get_binance_client(api_key: str, secret_key: str, testnet: bool = True) -> Client:
    """Cria e retorna o cliente da Binance conectado à Testnet ou Produção."""
    client = Client(api_key, secret_key, testnet=testnet)
    if testnet:
        client.API_URL = "https://testnet.binance.vision/api"

    # A Binance recusa requisição assinada cujo timestamp esteja mais de 1000 ms
    # adiantado em relação ao servidor dela (erro -1021), e o python-binance usa
    # o relógio local sem sincronizar. Medimos o desvio e ficamos 500 ms atrás,
    # que é o lado tolerado da janela.
    before = time.time() * 1000
    server_time = client.get_server_time()["serverTime"]
    after = time.time() * 1000
    client.timestamp_offset = int(server_time - (before + after) / 2) - 500

    print("\n" + "=" * 55)
    print("       BINANCE CONECTADA COM SUCESSO!")
    print("=" * 55)
    print(f"  Ambiente:        {'TESTNET (SIMULADOR / DINHEIRO VIRTUAL)' if testnet else 'PRODUÇÃO (CONTA REAL)'}")

    # Verificar saldo em USDT
    account = client.get_account()
    for balance in account["balances"]:
        asset = balance["asset"]
        free = float(balance["free"])
        if asset in ["USDT", "BTC", "ETH", "SOL", "BRL"] and free > 0:
            print(f"  Saldo {asset:<5}:    {free:>12.6f} (Livre)")
    print("=" * 55 + "\n")
    return client


def execute_crypto_strategy(
    client: Client,
    ticker: str = "BTC-USD",
    binance_symbol: str = "BTCUSDT",
    trade_amount_usdt: float = 100.0,
    models_dir: str = "models",
    window_size: int = 5
):
    """Executa um ciclo completo de análise e envio de ordens na Binance."""
    clean_ticker = ticker.replace("-", "_").replace("/", "_")
    model_path = os.path.join(models_dir, f"{clean_ticker}_dqn.pt")

    if not os.path.exists(model_path):
        print(f"[-] Modelo {model_path} não encontrado! Treine com: python main_crypto.py --ticker {ticker}")
        return

    # 1. Verificar saldos atuais na Binance
    base_asset = binance_symbol.replace("USDT", "")
    usdt_balance = float(client.get_asset_balance(asset="USDT")["free"])
    crypto_balance = float(client.get_asset_balance(asset=base_asset)["free"])

    # 2. Carregar dados de mercado recentes
    df = load_crypto_data(ticker=ticker, start_date="2024-01-01")
    current_price = float(df.iloc[-1]["Close"])

    feature_cols = ["Return_1d", "Return_5d", "Dist_SMA21", "RSI_14", "Bollinger_PctB", "Volatility_14"]
    recent_features = df.iloc[-window_size:][feature_cols].values.flatten()

    crypto_value_usdt = crypto_balance * current_price
    is_holding = crypto_value_usdt > 10.0  # Considera posicionado se tiver mais de $10 na moeda

    holding_flag = 1.0 if is_holding else 0.0
    unrealized_pnl = 0.0  # Estimativa simplificada

    state = np.concatenate([recent_features, [holding_flag, unrealized_pnl]]).astype(np.float32)

    # 3. Consultar a Rede Neural DQN
    agent = DQNAgent(state_size=len(state), action_space=3)
    agent.load(model_path)

    state_t = torch.FloatTensor(state).unsqueeze(0).to(agent.device)
    with torch.no_grad():
        q_values = agent.policy_net(state_t).cpu().numpy()[0]
    action = int(np.argmax(q_values))

    # 4. Tomada de Decisão Automatizada
    print(f"\n[*] Status do Robô em {binance_symbol} ({datetime.now().strftime('%d/%m/%Y %H:%M:%S')}):")
    print(f"    - Preço Atual: $ {current_price:,.2f} USD")
    print(f"    - Saldo USDT: $ {usdt_balance:.2f} | Saldo {base_asset}: {crypto_balance:.6f} (~$ {crypto_value_usdt:.2f})")
    print(f"    - Posição Atual: {'COMPRADO EM ' + base_asset if is_holding else 'EM USDT (LÍQUIDO)'}")
    print(f"    - Q-Values: Hold={q_values[0]:.4f} | Buy={q_values[1]:.4f} | Sell={q_values[2]:.4f}")

    if action == 1:
        if not is_holding and usdt_balance >= trade_amount_usdt:
            print(f"    -> DECISÃO: COMPRAR! Enviando ordem a mercado de $ {trade_amount_usdt:.2f} USDT para Binance...")
            try:
                order = client.create_order(
                    symbol=binance_symbol,
                    side=Client.SIDE_BUY,
                    type=Client.ORDER_TYPE_MARKET,
                    quoteOrderQty=trade_amount_usdt
                )
                print(f"[+] COMPRA EXECUTADA NA BINANCE! Order ID #{order['orderId']}")
            except Exception as e:
                print(f"[-] Erro ao enviar ordem de compra: {e}")
        else:
            print("    -> DECISÃO: MANTER POSIÇÃO (Já posicionado ou saldo insuficiente).")

    elif action == 2:
        if is_holding and crypto_balance > 0.0001:
            print(f"    -> DECISÃO: VENDER! Vendendo {crypto_balance:.6f} {base_asset} a mercado na Binance...")
            try:
                # Ajusta precisão de quantidade para evitar erro de lot size
                qty = round(crypto_balance, 5)
                order = client.create_order(
                    symbol=binance_symbol,
                    side=Client.SIDE_SELL,
                    type=Client.ORDER_TYPE_MARKET,
                    quantity=qty
                )
                print(f"[+] VENDA EXECUTADA NA BINANCE! Convertido para USDT. Order ID #{order['orderId']}")
            except Exception as e:
                print(f"[-] Erro ao enviar ordem de venda: {e}")
        else:
            print("    -> DECISÃO: AGUARDAR EM USDT (Nenhuma cripto para vender).")

    else:
        print("    -> DECISÃO: AGUARDAR / MANTER (Sem novas ordens necessárias).")


def main():
    parser = argparse.ArgumentParser(description="Robô de Trading em Criptomoedas com Binance")
    parser.add_argument("--api-key", type=str, default="", help="Binance API Key")
    parser.add_argument("--secret-key", type=str, default="", help="Binance Secret Key")
    parser.add_argument("--real", action="store_true", help="Se definido, opera na conta REAL (padrão é Testnet simulada)")
    parser.add_argument("--ticker", type=str, default="BTC-USD", help="Ticker de treino (ex: BTC-USD, ETH-USD, SOL-USD)")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Símbolo na Binance (ex: BTCUSDT, ETHUSDT, SOLUSDT)")
    parser.add_argument("--amount", type=float, default=100.0, help="Valor em USDT para comprar a cada entrada")
    parser.add_argument("--loop", action="store_true", help="Se ativado, roda continuamente")
    parser.add_argument("--interval-minutes", type=int, default=60, help="Intervalo de verificação em minutos")

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("BINANCE_API_KEY", "")
    secret_key = args.secret_key or os.environ.get("BINANCE_SECRET_KEY", "")

    if not api_key or not secret_key:
        print("[-] API Key e Secret Key da Binance são obrigatórias.")
        print("    Exemplo de uso na Testnet Simulada:")
        print("    python binance_bot.py --api-key SUAKEY --secret-key SUASECRET --ticker BTC-USD --symbol BTCUSDT")
        return

    is_testnet = not args.real
    client = get_binance_client(api_key, secret_key, testnet=is_testnet)

    if args.loop:
        print(f"[+] Modo Loop Automático Binance ativado! Verificando a cada {args.interval_minutes} minutos.")
        while True:
            execute_crypto_strategy(
                client=client,
                ticker=args.ticker,
                binance_symbol=args.symbol,
                trade_amount_usdt=args.amount
            )
            time.sleep(args.interval_minutes * 60)
    else:
        execute_crypto_strategy(
            client=client,
            ticker=args.ticker,
            binance_symbol=args.symbol,
            trade_amount_usdt=args.amount
        )


if __name__ == "__main__":
    main()
