"""
predict_today.py - Consulta o sinal de Swing Trade para o dia de hoje.
"""

import os
import argparse
import numpy as np
import pandas as pd
import torch

from src.b3_data import load_b3_data
from src.dqn_agent import DQNAgent


def get_today_prediction(ticker: str = "PETR4.SA", is_holding: bool = False, buy_price: float = 0.0, models_dir: str = "models", window_size: int = 5):
    clean_ticker = ticker.replace(".SA", "").replace("/", "_")
    model_path = os.path.join(models_dir, f"{clean_ticker}_dqn.pt")

    if not os.path.exists(model_path):
        print(f"[-] Modelo {model_path} não encontrado!")
        print(f"    Por favor, treine o modelo primeiro com: python main.py --ticker {ticker} --episodes 20")
        return

    # 1. Baixar dados recentes
    df = load_b3_data(ticker=ticker, start_date="2023-01-01")
    if len(df) < window_size + 1:
        print(f"[-] Dados insuficientes para montar o estado.")
        return

    # 2. Montar o estado mais recente
    feature_cols = ["Return_1d", "Return_5d", "Dist_SMA21", "RSI_14", "Volatility_10"]
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

    # 3. Carregar o agente treinado
    agent = DQNAgent(state_size=state_size, action_space=3)
    agent.load(model_path)

    # 4. Avaliar decisão da rede neural
    state_t = torch.FloatTensor(state).unsqueeze(0).to(agent.device)
    with torch.no_grad():
        q_values = agent.policy_net(state_t).cpu().numpy()[0]

    action = int(np.argmax(q_values))

    # Ações: 0: Hold, 1: Buy, 2: Sell
    action_map = {
        0: ("AGUARDAR / MANTER", "Ficar líquido ou manter a posição atual sem novas operações."),
        1: ("COMPRAR", f"Entrada em posição comprada ao preço de fechamento/mercado (~R$ {current_price:.2f})."),
        2: ("VENDER", f"Encerrar posição comprada e realizar lucros/proteger capital (~R$ {current_price:.2f})."),
    }

    # Validação da posição informada
    final_action = action
    if action == 1 and is_holding:
        final_action = 0  # Já está comprado, mantém
    elif action == 2 and not is_holding:
        final_action = 0  # Não está comprado, fica fora

    title, description = action_map[final_action]

    # Exibição do Painel
    print("\n" + "=" * 60)
    print(f"           RECOMENDAÇÃO DO ROBÔ DQN - {ticker}")
    print("=" * 60)
    print(f"  Última Cotação Registrada:   R$ {current_price:>8.2f} (Data: {last_date})")
    print(f"  RSI (14 períodos):             {last_row['RSI_14'] * 100:>8.1f} %")
    print(f"  Distância da Média (SMA 21):   {last_row['Dist_SMA21'] * 100:>+8.2f} %")
    print(f"  Retorno no Último Dia:         {last_row['Return_1d'] * 100:>+8.2f} %")
    print(f"  Sua Posição Atual:             {'COMPRADO (R$ ' + str(round(buy_price, 2)) + ')' if is_holding else 'EM CAIXA (LÍQUIDO)'}")
    print("-" * 60)
    print(f"  >>> SINAL DA IA:   [ {title} ] <<<")
    print(f"  Explicação: {description}")
    print("-" * 60)
    print("  Valores Q da Rede Neural (Estimativa de Retorno Futuro):")
    print(f"    - Hold (Aguardar): Q = {q_values[0]:+.4f}")
    print(f"    - Buy  (Comprar):  Q = {q_values[1]:+.4f}")
    print(f"    - Sell (Vender):   Q = {q_values[2]:+.4f}")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Consulta de Sinal de Trading do Robô DQN")
    parser.add_argument("--ticker", type=str, default="PETR4.SA", help="Código da ação (ex: PETR4.SA, VALE3.SA, ITUB4.SA)")
    parser.add_argument("--holding", action="store_true", help="Passe esta flag se você já tiver comprado a ação")
    parser.add_argument("--buy-price", type=float, default=0.0, help="Preço pelo qual você comprou (se estiver comprado)")
    parser.add_argument("--models-dir", type=str, default="models", help="Pasta com os modelos treinados")

    args = parser.parse_args()
    get_today_prediction(
        ticker=args.ticker,
        is_holding=args.holding,
        buy_price=args.buy_price,
        models_dir=args.models_dir
    )


if __name__ == "__main__":
    main()
