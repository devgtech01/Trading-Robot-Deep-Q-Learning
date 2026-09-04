"""
main.py - Script principal para treinamento e teste de Robô de Trading DQN na B3.
"""

import os
import argparse
from tqdm import tqdm

from src.b3_data import load_b3_data, split_train_test
from src.environment import B3TradingEnv
from src.dqn_agent import DQNAgent
from src.evaluator import calculate_metrics, plot_backtest_report, print_metrics_summary


def train_agent(
    env: B3TradingEnv,
    agent: DQNAgent,
    episodes: int = 25,
    batch_size: int = 32,
    target_update_freq: int = 3,
) -> DQNAgent:
    """Executa o loop de treinamento de Deep Q-Learning."""
    print(f"\n[+] Iniciando treinamento ({episodes} episódios)...")

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

        # Atualiza a Target Network periodicamente
        if episode % target_update_freq == 0:
            agent.update_target_network()

        final_portfolio = env.portfolio_history[-1]
        pnl_pct = ((final_portfolio - env.initial_balance) / env.initial_balance) * 100.0
        avg_loss = total_loss / max(1, loss_steps)

        print(
            f"  -> Ep {episode:02d}/{episodes:02d} | "
            f"Saldo Final: R$ {final_portfolio:9.2f} ({pnl_pct:+6.2f}%) | "
            f"Epsilon: {agent.epsilon:.3f} | "
            f"Trades: {len(env.trade_log):2d} | "
            f"Loss Média: {avg_loss:.5f}"
        )

    return agent


def evaluate_agent(
    env: B3TradingEnv,
    agent: DQNAgent,
    ticker: str,
    reports_dir: str = "reports"
) -> dict:
    """Executa o teste cego fora da amostra (Backtest)."""
    print(f"\n[*] Executando Teste Cego Fora da Amostra (Out-of-Sample)...")
    state = env.reset()
    done = False

    while not done:
        action = agent.act(state, evaluate=True)  # Deterministico: epsilon = 0
        next_state, reward, done, info = env.step(action)
        state = next_state

    # Cálculo do retorno do Benchmark (Buy & Hold do ativo no mesmo período)
    first_price = float(env.df.iloc[env.window_size]["Close"])
    last_price = float(env.df.iloc[-1]["Close"])
    benchmark_return = ((last_price - first_price) / first_price) * 100.0

    metrics = calculate_metrics(env.portfolio_history, env.trade_log, benchmark_return)
    print_metrics_summary(metrics, ticker)

    report_path = plot_backtest_report(
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
    parser = argparse.ArgumentParser(description="Robô de Trading B3 com Deep Q-Learning (PyTorch)")
    parser.add_argument("--ticker", type=str, default="PETR4.SA", help="Código da ação na B3 (ex: PETR4.SA, VALE3.SA, WEGE3.SA, BOVA11.SA)")
    parser.add_argument("--start-date", type=str, default="2018-01-01", help="Data de início do histórico (AAAA-MM-DD)")
    parser.add_argument("--split-date", type=str, default="2023-01-01", help="Data de corte para o teste cego (AAAA-MM-DD)")
    parser.add_argument("--episodes", type=int, default=20, help="Quantidade de episódios de treinamento")
    parser.add_argument("--batch-size", type=int, default=32, help="Tamanho do lote de treino do DQN")
    parser.add_argument("--capital", type=float, default=10000.0, help="Capital inicial em R$")
    parser.add_argument("--models-dir", type=str, default="models", help="Diretório para salvar o modelo treinado")
    parser.add_argument("--reports-dir", type=str, default="reports", help="Diretório para salvar relatórios gráficos")

    args = parser.parse_args()

    os.makedirs(args.models_dir, exist_ok=True)
    os.makedirs(args.reports_dir, exist_ok=True)

    # 1. Carregamento e Preparação dos Dados
    raw_df = load_b3_data(args.ticker, start_date=args.start_date)
    train_df, test_df = split_train_test(raw_df, split_date=args.split_date)

    # 2. Criação dos Ambientes de Treino e Teste
    train_env = B3TradingEnv(train_df, initial_balance=args.capital)
    test_env = B3TradingEnv(test_df, initial_balance=args.capital)

    # 3. Inicialização do Agente DQN
    agent = DQNAgent(state_size=train_env.state_size, action_space=train_env.action_space)

    # 4. Treinamento
    agent = train_agent(train_env, agent, episodes=args.episodes, batch_size=args.batch_size)

    # 5. Salvar o Modelo Treinado
    clean_ticker = args.ticker.replace(".SA", "").replace("/", "_")
    model_path = os.path.join(args.models_dir, f"{clean_ticker}_dqn.pt")
    agent.save(model_path)
    print(f"\n[+] Modelo treinado salvo em: {model_path}")

    # 6. Avaliação e Teste Cego
    evaluate_agent(test_env, agent, ticker=args.ticker, reports_dir=args.reports_dir)


if __name__ == "__main__":
    main()
