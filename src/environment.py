"""
environment.py - Ambiente de simulação realista para Swing Trade na B3.
"""

import numpy as np
import pandas as pd


class B3TradingEnv:
    """
    Ambiente de simulação de negociação com custos reais da B3.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        initial_balance: float = 10000.0,
        transaction_fee: float = 0.0003,  # 0,03% (taxas B3 + corretagem média)
        window_size: int = 5,
    ):
        self.df = df.reset_index()
        self.initial_balance = initial_balance
        self.transaction_fee = transaction_fee
        self.window_size = window_size

        # Features utilizadas no estado
        self.feature_cols = [
            "Return_1d",
            "Return_5d",
            "Dist_SMA21",
            "RSI_14",
            "Volatility_10",
        ]
        self.n_features = len(self.feature_cols)

        # Tamanho do estado: (window_size * n_features) + 2 (posição atual + lucro não realizado)
        self.state_size = (self.window_size * self.n_features) + 2
        self.action_space = 3  # 0: Hold, 1: Buy, 2: Sell

        self.reset()

    def reset(self):
        """Reinicia o ambiente para um novo episódio de simulação."""
        self.current_step = self.window_size
        self.balance = self.initial_balance
        self.shares_held = 0
        self.buy_price = 0.0
        self.buy_step = 0
        self.cost_basis = 0.0
        self.total_fees_paid = 0.0

        # Históricos
        self.portfolio_history = [self.initial_balance]
        self.dates_history = [self.df.loc[self.current_step, "Date"]]
        self.trade_log = []

        return self._get_state()

    def _get_state(self) -> np.ndarray:
        """Monta o vetor de estado que alimenta a rede neural."""
        start = self.current_step - self.window_size
        end = self.current_step

        window_features = self.df.loc[start:end - 1, self.feature_cols].values.flatten()

        current_price = float(self.df.loc[self.current_step, "Close"])
        is_holding = 1.0 if self.shares_held > 0 else 0.0
        unrealized_pnl = 0.0
        if self.shares_held > 0 and self.buy_price > 0:
            unrealized_pnl = (current_price - self.buy_price) / self.buy_price

        state = np.concatenate([window_features, [is_holding, unrealized_pnl]])
        return state.astype(np.float32)

    def step(self, action: int):
        """
        Executa uma ação no ambiente.
        Ações:
            0: Hold (Manter)
            1: Buy (Comprar)
            2: Sell (Vender)
        """
        current_price = float(self.df.loc[self.current_step, "Close"])
        current_date = self.df.loc[self.current_step, "Date"]
        reward = 0.0

        # 1. COMPRA
        if action == 1 and self.shares_held == 0:
            fee = self.balance * self.transaction_fee
            capital_available = self.balance - fee
            self.cost_basis = capital_available
            self.shares_held = capital_available / current_price
            self.buy_price = current_price
            self.buy_step = self.current_step
            self.balance = 0.0
            self.total_fees_paid += fee

        # 2. VENDA
        elif action == 2 and self.shares_held > 0:
            gross_sale = self.shares_held * current_price
            fee = gross_sale * self.transaction_fee
            net_sale = gross_sale - fee
            self.total_fees_paid += fee

            trade_profit_cash = net_sale - self.cost_basis
            trade_profit_pct = (current_price - self.buy_price) / self.buy_price
            net_profit_pct = trade_profit_cash / (self.cost_basis + 1e-9)

            self.balance = net_sale
            self.shares_held = 0

            # Recompensa com penalização real de risco
            reward = net_profit_pct * 10.0

            # Registra o trade
            self.trade_log.append({
                "buy_date": self.df.loc[self.buy_step, "Date"],
                "buy_price": self.buy_price,
                "sell_date": current_date,
                "sell_price": current_price,
                "profit_pct": net_profit_pct * 100.0,
                "profit_cash": trade_profit_cash,
            })
            self.buy_price = 0.0
            self.cost_basis = 0.0

        # 3. MANTER (HOLD)
        else:
            if self.shares_held > 0:
                # Pequena recompensa/penalidade diária pelo movimento da ação mantida
                daily_return = float(self.df.loc[self.current_step, "Return_1d"])
                reward = daily_return * 0.5
            else:
                # Se estiver fora do mercado quando ele cai, preservou capital
                daily_return = float(self.df.loc[self.current_step, "Return_1d"])
                if daily_return < -0.01:
                    reward = 0.02  # Bônus por ficar líquido durante queda acentuada

        # Atualiza o patrimônio atual (Equity)
        portfolio_value = self.balance + (self.shares_held * current_price)
        self.portfolio_history.append(portfolio_value)
        self.dates_history.append(current_date)

        # Avança para o próximo dia
        self.current_step += 1
        done = self.current_step >= len(self.df) - 1

        next_state = self._get_state() if not done else np.zeros(self.state_size, dtype=np.float32)

        return next_state, reward, done, {"portfolio_value": portfolio_value}
