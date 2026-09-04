"""
predict_crypto.py - Consulta o sinal de Trading de Criptomoedas para o dia de hoje.
"""

import os
import argparse
import numpy as np
import pandas as pd
import torch

from src.crypto_data import load_crypto_data
from src.dqn_agent import DQNAgent


def get_crypto_prediction(ticker: str = "BTC-USD", is_holding: bool = False, buy_price: float = 0.0, models_dir: str = "models", window_size: int = 5):
    clean_ticker = ticker.replace("-", "_").replace("/", "_")
    model_path = os.path.join(models_dir, f"{clean_ticker}_dqn.pt")

    if not os.path.exists(model_path):
        print(f"[-] Modelo {model_path} não encontrado!")
        print(f"    Por favor, treine o modelo primeiro com: python main_crypto.py --ticker {ticker} --episodes 25")
        return

    df = load_crypto_data(ticker=ticker, start_date="2024-01-01")
    if len(df) < window_size + 1:
        print(f"[-] Dados insuficientes para montar o estado.")
        return

    feature_cols = [
        "Return_1d",
        "Return_5d",
        "Dist_SMA21",
        "RSI_14",
        "Bollinger_PctB",
        "Volatility_14",
    ]
    recent_features = df.iloc[-window_size:][feature_cols].values.flatten()

    last_row = df.iloc[-1]
    current_price = float(last_row["Close"])
    last_date = df.index[-1].strftime("%d/%m/%Y")

    unrealized_pnl = 0.0
    holding_flag = 1.0 if is_holding else 0.0
    if is_holding and buy_price > 0:
        unrealized_pnl = (current_price - buy_price) / buy_price

    state = np.concatenate([recent_features, [holding_flag, unrealized_pnl]]).astype(np.float32)
    state_size = len(state)

    agent = DQNAgent(state_size=state_size, action_space=3)
    agent.load(model_path)

    state_t = torch.FloatTensor(state).unsqueeze(0).to(agent.device)
    with torch.no_grad():
        q_values = agent.policy_net(state_t).cpu().numpy()[0]

    action = int(np.argmax(q_values))

    action_map = {
        0: ("AGUARDAR / FICAR EM USDT", "Manter posição atual em USDT ou em cripto sem novas operações."),
        1: ("COMPRAR CRIPTO", f"Entrada em posição comprada ao preço de mercado (~$ {current_price:,.2f} USD)."),
        2: ("VENDER PARA USDT", f"Realizar lucros ou proteger capital convertendo para USDT (~$ {current_price:,.2f} USD)."),
    }

    final_action = action
    if action == 1 and is_holding:
        final_action = 0
    elif action == 2 and not is_holding:
        final_action = 0

    title, description = action_map[final_action]

    print("\n" + "=" * 60)
    print(f"       RECOMENDAÇÃO DO ROBÔ DQN DE CRIPTO - {ticker}")
    print("=" * 60)
    print(f"  Última Cotação:              $ {current_price:>12,.2f} USD (Data: {last_date})")
    print(f"  RSI (14 períodos):             {last_row['RSI_14'] * 100:>11.1f} %")
    print(f"  Distância da Média (SMA 21):   {last_row['Dist_SMA21'] * 100:>+11.2f} %")
    print(f"  Posição nas Bollinger (%B):    {last_row['Bollinger_PctB'] * 100:>11.1f} %")
    print(f"  Retorno 24h (1d):              {last_row['Return_1d'] * 100:>+11.2f} %")
    print(f"  Sua Posição Atual:             {'COMPRADO ($ ' + str(round(buy_price, 2)) + ')' if is_holding else 'EM USDT (LÍQUIDO)'}")
    print("-" * 60)
    print(f"  >>> SINAL DA IA:   [ {title} ] <<<")
    print(f"  Explicação: {description}")
    print("-" * 60)
    print("  Valores Q da Rede Neural (Estimativa de Retorno Futuro):")
    print(f"    - Hold (USDT/Manter): Q = {q_values[0]:+.4f}")
    print(f"    - Buy  (Comprar):     Q = {q_values[1]:+.4f}")
    print(f"    - Sell (Vender):      Q = {q_values[2]:+.4f}")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Consulta de Sinal de Cripto do Robô DQN")
    parser.add_argument("--ticker", type=str, default="BTC-USD", help="Par da cripto (ex: BTC-USD, ETH-USD, SOL-USD)")
    parser.add_argument("--holding", action="store_true", help="Passe esta flag se você já estiver com a cripto na carteira")
    parser.add_argument("--buy-price", type=float, default=0.0, help="Preço de compra (em USD) se estiver comprado")
    parser.add_argument("--models-dir", type=str, default="models", help="Pasta com os modelos treinados")

    args = parser.parse_args()
    get_crypto_prediction(
        ticker=args.ticker,
        is_holding=args.holding,
        buy_price=args.buy_price,
        models_dir=args.models_dir
    )


if __name__ == "__main__":
    main()
