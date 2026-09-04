"""
main_crypto.py - Script principal para treinamento e teste de Robô de Trading DQN em Criptomoedas.
"""

import os
import argparse
from tqdm import tqdm

from src.crypto_data import load_crypto_data, split_crypto_train_test
from src.crypto_env import CryptoTradingEnv
from src.dqn_agent import DQNAgent
from src.crypto_evaluator import calculate_crypto_metrics, plot_crypto_backtest_report, print_crypto_metrics_summary


def train_crypto_agent(
    env: CryptoTradingEnv,
    agent: DQNAgent,
    episodes: int = 25,
    batch_size: int = 32,
    target_update_freq: int = 3,
) -> DQNAgent:
    """Treina o agente de Deep Q-Learning no histórico de criptomoedas."""
    print(f"\n[+] Iniciando treinamento de Cripto ({episodes} episódios)...")

    for episode in range(1, episodes + 1):
        state = env.reset()
        done = False
        total_loss = 0.0
        loss_steps = 0

        with tqdm(total=len(env.df) - env.window_size - 1, desc=f"Episódio {episode:02d}/{episodes:02d}", leave=False) as pbar:
            while not done:
                action = agent.act(state, evaluate=False)
                next_state, reward, done, info = env.step(action)

                agent.remember(state, action, reward, next_state, done)
                state = next_state

                if len(agent.memory) > batch_size:
                    loss = agent.replay(batch_size)
                    total_loss += loss
                    loss_steps += 1

                pbar.update(1)

        if episode % target_update_freq == 0:
            agent.update_target_network()

        final_portfolio = env.portfolio_history[-1]
        pnl_pct = ((final_portfolio - env.initial_balance) / env.initial_balance) * 100.0
        avg_loss = total_loss / max(1, loss_steps)

        print(
            f"  -> Ep {episode:02d}/{episodes:02d} | "
            f"Saldo: $ {final_portfolio:9.2f} USDT ({pnl_pct:+6.2f}%) | "
            f"Epsilon: {agent.epsilon:.3f} | "
            f"Trades: {len(env.trade_log):2d} | "
            f"Loss Média: {avg_loss:.5f}"
        )

    return agent


def evaluate_crypto_agent(
    env: CryptoTradingEnv,
    agent: DQNAgent,
    ticker: str,
    reports_dir: str = "reports"
) -> dict:
    """Executa o teste cego fora da amostra para o par de criptomoeda."""
    print(f"\n[*] Executando Teste Cego Fora da Amostra em Cripto...")
    state = env.reset()
    done = False

    while not done:
        action = agent.act(state, evaluate=True)
        next_state, reward, done, info = env.step(action)
        state = next_state

    first_price = float(env.df.iloc[env.window_size]["Close"])
    last_price = float(env.df.iloc[-1]["Close"])
    benchmark_return = ((last_price - first_price) / first_price) * 100.0

    metrics = calculate_crypto_metrics(env.portfolio_history, env.trade_log, benchmark_return)
    print_crypto_metrics_summary(metrics, ticker)

    report_path = plot_crypto_backtest_report(
        dates=env.dates_history,
        portfolio_history=env.portfolio_history,
        df_prices=env.df,
        trade_log=env.trade_log,
        metrics=metrics,
        ticker=ticker,
        output_dir=reports_dir
    )
    print(f"[+] Gráfico visual de backtest salvo em: {report_path}")
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Robô de Trading em Criptomoedas com Deep Q-Learning")
    parser.add_argument("--ticker", type=str, default="BTC-USD", help="Par da criptomoeda (ex: BTC-USD, ETH-USD, SOL-USD, BNB-USD)")
    parser.add_argument("--start-date", type=str, default="2019-01-01", help="Data de início do histórico (AAAA-MM-DD)")
    parser.add_argument("--split-date", type=str, default="2024-01-01", help="Data de corte para o teste cego (AAAA-MM-DD)")
    parser.add_argument("--episodes", type=int, default=25, help="Quantidade de episódios de treinamento")
    parser.add_argument("--batch-size", type=int, default=32, help="Tamanho do lote de treino do DQN")
    parser.add_argument("--capital", type=float, default=1000.0, help="Capital inicial em USDT ($)")
    parser.add_argument("--models-dir", type=str, default="models", help="Diretório para salvar o modelo treinado")
    parser.add_argument("--reports-dir", type=str, default="reports", help="Diretório para salvar relatórios gráficos")

    args = parser.parse_args()

    os.makedirs(args.models_dir, exist_ok=True)
    os.makedirs(args.reports_dir, exist_ok=True)

    # 1. Carregar dados de Cripto
    raw_df = load_crypto_data(args.ticker, start_date=args.start_date)
    train_df, test_df = split_crypto_train_test(raw_df, split_date=args.split_date)

    # 2. Criar ambientes de Treino e Teste
    train_env = CryptoTradingEnv(train_df, initial_balance=args.capital)
    test_env = CryptoTradingEnv(test_df, initial_balance=args.capital)

    # 3. Inicializar Agente DQN
    agent = DQNAgent(state_size=train_env.state_size, action_space=train_env.action_space)

    # 4. Treinar
    agent = train_crypto_agent(train_env, agent, episodes=args.episodes, batch_size=args.batch_size)

    # 5. Salvar Modelo
    clean_ticker = args.ticker.replace("-", "_").replace("/", "_")
    model_path = os.path.join(args.models_dir, f"{clean_ticker}_dqn.pt")
    agent.save(model_path)
    print(f"\n[+] Modelo treinado salvo em: {model_path}")

    # 6. Avaliar no Teste Cego
    evaluate_crypto_agent(test_env, agent, ticker=args.ticker, reports_dir=args.reports_dir)


if __name__ == "__main__":
    main()
