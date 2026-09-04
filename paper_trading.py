"""
paper_trading.py - Sistema de Carteira Simulada (Paper Trading) em Tempo Real para B3 e Cripto.
"""

import os
import json
import argparse
from datetime import datetime
import numpy as np
import pandas as pd
import torch

from src.b3_data import load_b3_data
from src.crypto_data import load_crypto_data
from src.dqn_agent import DQNAgent

WALLET_FILE = os.path.join("data", "paper_wallet.json")


def load_wallet() -> dict:
    """Carrega o extrato e saldo da carteira virtual."""
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(WALLET_FILE):
        initial_wallet = {
            "BRL": {
                "cash": 10000.0,
                "initial_cash": 10000.0,
                "positions": {},  # { "PETR4.SA": { "shares": 100, "buy_price": 45.5, "cost_basis": 4550 } }
                "history": []
            },
            "USDT": {
                "cash": 1000.0,
                "initial_cash": 1000.0,
                "positions": {},  # { "BTC-USD": { "amount": 0.0125, "buy_price": 80000, "cost_basis": 1000 } }
                "history": []
            }
        }
        save_wallet(initial_wallet)
        return initial_wallet

    with open(WALLET_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_wallet(wallet: dict):
    """Salva os dados da carteira virtual em arquivo JSON."""
    os.makedirs("data", exist_ok=True)
    with open(WALLET_FILE, "w", encoding="utf-8") as f:
        json.dump(wallet, f, indent=4, ensure_ascii=False)


def run_paper_trading(ticker: str, is_crypto: bool = False, models_dir: str = "models", window_size: int = 5):
    wallet = load_wallet()
    currency = "USDT" if is_crypto else "BRL"
    curr_symbol = "$" if is_crypto else "R$"
    fee_rate = 0.001 if is_crypto else 0.0003  # 0.1% cripto / 0.03% B3

    clean_ticker = ticker.replace(".SA", "").replace("-", "_").replace("/", "_")
    model_path = os.path.join(models_dir, f"{clean_ticker}_dqn.pt")

    if not os.path.exists(model_path):
        print(f"[-] Modelo {model_path} não encontrado!")
        cmd = f"python main_crypto.py --ticker {ticker}" if is_crypto else f"python main.py --ticker {ticker}"
        print(f"    Treine o modelo antes: {cmd}")
        return

    # 1. Obter dados e cotação atual
    if is_crypto:
        df = load_crypto_data(ticker=ticker, start_date="2024-01-01")
        feature_cols = ["Return_1d", "Return_5d", "Dist_SMA21", "RSI_14", "Bollinger_PctB", "Volatility_14"]
    else:
        df = load_b3_data(ticker=ticker, start_date="2023-01-01")
        feature_cols = ["Return_1d", "Return_5d", "Dist_SMA21", "RSI_14", "Volatility_10"]

    current_price = float(df.iloc[-1]["Close"])
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 2. Verificar posição na carteira
    pos = wallet[currency]["positions"].get(ticker, None)
    is_holding = pos is not None and pos["amount"] > 0
    buy_price = pos["buy_price"] if is_holding else 0.0

    unrealized_pnl = ((current_price - buy_price) / buy_price) if (is_holding and buy_price > 0) else 0.0
    holding_flag = 1.0 if is_holding else 0.0

    recent_features = df.iloc[-window_size:][feature_cols].values.flatten()
    state = np.concatenate([recent_features, [holding_flag, unrealized_pnl]]).astype(np.float32)

    # 3. Consultar a Rede Neural
    agent = DQNAgent(state_size=len(state), action_space=3)
    agent.load(model_path)

    state_t = torch.FloatTensor(state).unsqueeze(0).to(agent.device)
    with torch.no_grad():
        q_values = agent.policy_net(state_t).cpu().numpy()[0]
    action = int(np.argmax(q_values))

    # 4. Executar Ordem Simulada
    action_str = "HOLD"
    trade_executed = False

    # COMPRA (Se tiver saldo em caixa)
    if action == 1 and not is_holding and wallet[currency]["cash"] > 10.0:
        available_cash = wallet[currency]["cash"]
        fee = available_cash * fee_rate
        net_capital = available_cash - fee
        amount_bought = net_capital / current_price

        wallet[currency]["cash"] = 0.0
        wallet[currency]["positions"][ticker] = {
            "amount": amount_bought,
            "buy_price": current_price,
            "buy_date": current_date,
            "cost_basis": net_capital,
            "fee_paid": fee
        }
        action_str = "COMPRA EXECUTADA (100% do saldo alocado)"
        trade_executed = True

    # VENDA (Se estiver em custódia)
    elif action == 2 and is_holding:
        amount_held = pos["amount"]
        gross_sale = amount_held * current_price
        fee = gross_sale * fee_rate
        net_sale = gross_sale - fee

        profit_cash = net_sale - pos["cost_basis"]
        profit_pct = (profit_cash / pos["cost_basis"]) * 100.0

        wallet[currency]["cash"] += net_sale
        wallet[currency]["history"].append({
            "ticker": ticker,
            "buy_date": pos["buy_date"],
            "buy_price": pos["buy_price"],
            "sell_date": current_date,
            "sell_price": current_price,
            "amount": amount_held,
            "profit_cash": profit_cash,
            "profit_pct": profit_pct,
            "fee_paid": pos["fee_paid"] + fee
        })
        del wallet[currency]["positions"][ticker]
        action_str = f"VENDA EXECUTADA (Lucro/Prejuízo: {curr_symbol} {profit_cash:+,.2f} / {profit_pct:+.2f}%)"
        trade_executed = True

    else:
        if is_holding:
            cur_pnl = ((current_price - buy_price) / buy_price) * 100.0
            action_str = f"MANTER POSIÇÃO (Variação atual: {cur_pnl:+.2f}%)"
        else:
            action_str = "AGUARDAR EM CAIXA (Sem nova entrada)"

    save_wallet(wallet)

    # 5. Calcular Patrimônio Total Atual
    total_equity = wallet[currency]["cash"]
    for t_code, p_data in wallet[currency]["positions"].items():
        total_equity += p_data["amount"] * current_price

    total_return_pct = ((total_equity - wallet[currency]["initial_cash"]) / wallet[currency]["initial_cash"]) * 100.0

    # Exibição do Painel
    print("\n" + "=" * 65)
    print(f"       CARTEIRA SIMULADA (PAPER TRADING) - {ticker} [{currency}]")
    print("=" * 65)
    print(f"  Cotação Atual:               {curr_symbol} {current_price:>12,.2f}")
    print(f"  Ação da IA:                  {action_str}")
    print("-" * 65)
    print(f"  Saldo Líquido em Conta:      {curr_symbol} {wallet[currency]['cash']:>12,.2f}")
    print(f"  Patrimônio Total da Carteira:{curr_symbol} {total_equity:>12,.2f} ({total_return_pct:>+6.2f}%)")
    print(f"  Posições Ativas em Custódia: {len(wallet[currency]['positions'])}")
    for t_code, p_data in wallet[currency]["positions"].items():
        val = p_data["amount"] * current_price
        pnl = ((current_price - p_data["buy_price"]) / p_data["buy_price"]) * 100.0
        print(f"    -> {t_code}: {p_data['amount']:.4f} un. | Custo: {curr_symbol} {p_data['buy_price']:.2f} | Atual: {curr_symbol} {val:,.2f} ({pnl:+.2f}%)")

    print(f"  Histórico de Trades Fechados:{len(wallet[currency]['history'])}")
    print("=" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Paper Trading em Tempo Real (Simulador)")
    parser.add_argument("--ticker", type=str, default="PETR4.SA", help="Código do ativo (ex: PETR4.SA, VALE3.SA, BTC-USD)")
    parser.add_argument("--crypto", action="store_true", help="Passe esta flag se o ativo for uma Criptomoeda")
    parser.add_argument("--models-dir", type=str, default="models", help="Pasta com os modelos")

    args = parser.parse_args()
    is_crypto = args.crypto or ("-USD" in args.ticker.upper())
    run_paper_trading(ticker=args.ticker, is_crypto=is_crypto, models_dir=args.models_dir)


if __name__ == "__main__":
    main()
