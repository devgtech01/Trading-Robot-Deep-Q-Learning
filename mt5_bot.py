"""
mt5_bot.py - Robô Automatizado para execução direta no MetaTrader 5 (Simulador / Real).
"""

import os
import time
import argparse
from datetime import datetime
import numpy as np
import torch
import MetaTrader5 as mt5

from src.b3_data import load_b3_data
from src.dqn_agent import DQNAgent
from src.mt5_executor import connect_mt5, get_mt5_positions, send_buy_order, send_close_position


def execute_strategy(ticker: str, volume: float = 100.0, models_dir: str = "models", window_size: int = 5):
    """Executa um ciclo completo de análise e envio de ordens no MetaTrader 5."""
    clean_ticker = ticker.replace(".SA", "").replace("/", "_")
    model_path = os.path.join(models_dir, f"{clean_ticker}_dqn.pt")

    if not os.path.exists(model_path):
        print(f"[-] Modelo {model_path} não encontrado! Treine com: python main.py --ticker {ticker}")
        return

    # 1. Verificar posições ativas no MT5
    positions = get_mt5_positions(clean_ticker)
    is_holding = len(positions) > 0
    buy_price = positions[0].price_open if is_holding else 0.0

    # 2. Carregar dados de mercado recentes
    yfinance_ticker = ticker if ticker.endswith(".SA") else ticker + ".SA"
    df = load_b3_data(ticker=yfinance_ticker, start_date="2023-01-01")
    current_price = float(df.iloc[-1]["Close"])

    feature_cols = ["Return_1d", "Return_5d", "Dist_SMA21", "RSI_14", "Volatility_10"]
    recent_features = df.iloc[-window_size:][feature_cols].values.flatten()

    unrealized_pnl = ((current_price - buy_price) / buy_price) if (is_holding and buy_price > 0) else 0.0
    holding_flag = 1.0 if is_holding else 0.0

    state = np.concatenate([recent_features, [holding_flag, unrealized_pnl]]).astype(np.float32)

    # 3. Consultar a Rede Neural
    agent = DQNAgent(state_size=len(state), action_space=3)
    agent.load(model_path)

    state_t = torch.FloatTensor(state).unsqueeze(0).to(agent.device)
    with torch.no_grad():
        q_values = agent.policy_net(state_t).cpu().numpy()[0]
    action = int(np.argmax(q_values))

    # 4. Tomada de Decisão Automatizada
    print(f"\n[*] Status do Robô em {clean_ticker} ({datetime.now().strftime('%d/%m/%Y %H:%M:%S')}):")
    print(f"    - Preço Atual: R$ {current_price:.2f}")
    print(f"    - Posição no MT5: {'COMPRADO (' + str(len(positions)) + ' ordens)' if is_holding else 'EM CAIXA (LÍQUIDO)'}")
    print(f"    - Q-Values: Hold={q_values[0]:.4f} | Buy={q_values[1]:.4f} | Sell={q_values[2]:.4f}")

    if action == 1:
        if not is_holding:
            print("    -> DECISÃO: COMPRAR! Enviando ordem automática para o MT5...")
            send_buy_order(symbol=clean_ticker, volume=volume)
        else:
            print("    -> DECISÃO: MANTER POSIÇÃO COMPRADA (Já estamos posicionados).")

    elif action == 2:
        if is_holding:
            print("    -> DECISÃO: VENDER! Encerrando posições abertas no MT5...")
            for pos in positions:
                send_close_position(pos)
        else:
            print("    -> DECISÃO: AGUARDAR FORA DO MERCADO (Nenhuma ação em custódia).")

    else:
        print("    -> DECISÃO: AGUARDAR / MANTER (Sem novas ordens necessárias).")


def main():
    parser = argparse.ArgumentParser(description="Robô de Trading Automatizado com MetaTrader 5")
    parser.add_argument("--ticker", type=str, default="PETR4.SA", help="Código da ação (ex: PETR4.SA, VALE3.SA)")
    parser.add_argument("--volume", type=float, default=100.0, help="Quantidade de ações por operação (ex: 100 para lote padrão, 10 para fracionário)")
    parser.add_argument("--loop", action="store_true", help="Se ativado, roda continuamente em segundo plano")
    parser.add_argument("--interval-minutes", type=int, default=60, help="Intervalo de verificação em minutos (no modo loop)")

    args = parser.parse_args()

    # Conectar ao MetaTrader 5
    if not connect_mt5():
        print("[-] Certifique-se de que o MetaTrader 5 está instalado e aberto no seu Windows.")
        return

    try:
        if args.loop:
            print(f"[+] Modo Loop Automático ativado! Verificando a cada {args.interval_minutes} minutos. Pressione Ctrl+C para parar.")
            while True:
                execute_strategy(ticker=args.ticker, volume=args.volume)
                time.sleep(args.interval_minutes * 60)
        else:
            execute_strategy(ticker=args.ticker, volume=args.volume)

    finally:
        mt5.shutdown()
        print("[*] Conexão com o MetaTrader 5 encerrada.")


if __name__ == "__main__":
    main()
