"""
crypto_evaluator.py - Avaliação e geração de relatórios gráficos para Criptomoedas (USDT).
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def calculate_crypto_metrics(portfolio_history: list[float], trade_log: list[dict], benchmark_return: float) -> dict:
    """Calcula as métricas financeiras para o backtest de Criptomoedas."""
    equity = np.array(portfolio_history)
    initial_val = equity[0]
    final_val = equity[-1]

    total_return = ((final_val - initial_val) / initial_val) * 100.0

    peaks = np.maximum.accumulate(equity)
    drawdowns = (equity - peaks) / (peaks + 1e-9) * 100.0
    max_drawdown = float(np.min(drawdowns))

    total_trades = len(trade_log)
    if total_trades > 0:
        profits = [t["profit_pct"] for t in trade_log]
        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p <= 0]

        win_rate = (len(wins) / total_trades) * 100.0
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0

        total_gain = sum([t["profit_cash"] for t in trade_log if t["profit_cash"] > 0])
        total_loss = abs(sum([t["profit_cash"] for t in trade_log if t["profit_cash"] < 0]))
        profit_factor = (total_gain / (total_loss + 1e-9)) if total_loss > 0 else float("inf")
    else:
        win_rate = 0.0
        avg_win = 0.0
        avg_loss = 0.0
        profit_factor = 0.0

    daily_returns = np.diff(equity) / (equity[:-1] + 1e-9)
    if len(daily_returns) > 1 and np.std(daily_returns) > 0:
        # Cripto opera 365 dias ao ano
        sharpe = float(np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(365))
    else:
        sharpe = 0.0

    return {
        "initial_balance": initial_val,
        "final_balance": final_val,
        "total_return_pct": total_return,
        "benchmark_return_pct": benchmark_return,
        "max_drawdown_pct": max_drawdown,
        "total_trades": total_trades,
        "win_rate_pct": win_rate,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe,
    }


def plot_crypto_backtest_report(
    dates: list,
    portfolio_history: list[float],
    df_prices: pd.DataFrame,
    trade_log: list[dict],
    metrics: dict,
    ticker: str,
    output_dir: str = "reports"
) -> str:
    """Gera um gráfico visual do robô de Cripto."""
    os.makedirs(output_dir, exist_ok=True)
    clean_ticker = ticker.replace("-", "_").replace("/", "_")
    output_path = os.path.join(output_dir, f"{clean_ticker}_backtest_report.png")

    dates = pd.to_datetime(dates)
    equity = np.array(portfolio_history)

    prices = df_prices["Close"].values[len(df_prices) - len(dates):]
    norm_benchmark = (prices / prices[0]) * metrics["initial_balance"]

    peaks = np.maximum.accumulate(equity)
    drawdowns = (equity - peaks) / (peaks + 1e-9) * 100.0

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(13, 11), sharex=True, gridspec_kw={'height_ratios': [2.5, 1.8, 1]})

    ax1.set_title(
        f"Relatório de Desempenho Cripto DQN: {ticker} (24/7)\n"
        f"Retorno Robô: {metrics['total_return_pct']:+.2f}% | Buy & Hold: {metrics['benchmark_return_pct']:+.2f}% | "
        f"Max Drawdown: {metrics['max_drawdown_pct']:.2f}% | Win Rate: {metrics['win_rate_pct']:.1f}%",
        fontsize=13, fontweight="bold", pad=12
    )
    ax1.plot(dates, equity, label=f"Robô DQN USDT (Final: $ {metrics['final_balance']:,.2f})", color="#00E676", linewidth=2.2)
    ax1.plot(dates, norm_benchmark, label=f"Buy & Hold {ticker} (Final: $ {norm_benchmark[-1]:,.2f})", color="#B0BEC5", linestyle="--", linewidth=1.5)
    ax1.set_ylabel("Patrimônio (USDT)", fontsize=11)
    ax1.legend(loc="upper left", frameon=True)
    ax1.grid(True, alpha=0.3)

    ax2.plot(dates, prices, label=f"Preço {ticker} (USD)", color="#FFB300", linewidth=1.4)
    if trade_log:
        buy_dates = pd.to_datetime([t["buy_date"] for t in trade_log])
        buy_prices = [t["buy_price"] for t in trade_log]
        sell_dates = pd.to_datetime([t["sell_date"] for t in trade_log])
        sell_prices = [t["sell_price"] for t in trade_log]

        ax2.scatter(buy_dates, buy_prices, marker="^", color="#00E676", s=90, label="Compra (Buy)", zorder=5)
        ax2.scatter(sell_dates, sell_prices, marker="v", color="#FF1744", s=90, label="Venda (Sell)", zorder=5)

    ax2.set_ylabel("Cotação (USD)", fontsize=11)
    ax2.legend(loc="upper left", frameon=True)
    ax2.grid(True, alpha=0.3)

    ax3.fill_between(dates, drawdowns, 0, color="#EF5350", alpha=0.4, label="Drawdown (%)")
    ax3.plot(dates, drawdowns, color="#D32F2F", linewidth=1.0)
    ax3.set_ylabel("Drawdown (%)", fontsize=11)
    ax3.set_xlabel("Data", fontsize=11)
    ax3.grid(True, alpha=0.3)
    ax3.legend(loc="lower left", frameon=True)

    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()

    return output_path


def print_crypto_metrics_summary(metrics: dict, ticker: str):
    """Imprime tabela formatada com o resultado do backtest de Cripto."""
    print("\n" + "=" * 55)
    print(f"     RESULTADO DO TESTE CEGO DE CRIPTO - {ticker}")
    print("=" * 55)
    print(f"  Saldo Inicial:             $ {metrics['initial_balance']:>12,.2f} USDT")
    print(f"  Saldo Final:               $ {metrics['final_balance']:>12,.2f} USDT")
    print(f"  Retorno do Robô:              {metrics['total_return_pct']:>11.2f} %")
    print(f"  Retorno Buy & Hold:           {metrics['benchmark_return_pct']:>11.2f} %")
    print(f"  Max Drawdown (Maior Queda):   {metrics['max_drawdown_pct']:>11.2f} %")
    print(f"  Índice Sharpe (365d):         {metrics['sharpe_ratio']:>11.2f}")
    print("-" * 55)
    print(f"  Total de Operações:           {metrics['total_trades']:>11d}")
    print(f"  Taxa de Acerto (Win Rate):    {metrics['win_rate_pct']:>11.2f} %")
    print(f"  Ganho Médio por Trade:        {metrics['avg_win_pct']:>11.2f} %")
    print(f"  Perda Média por Trade:        {metrics['avg_loss_pct']:>11.2f} %")
    print(f"  Fator de Lucro (Profit Factor):{metrics['profit_factor']:>10.2f}")
    print("=" * 55 + "\n")
