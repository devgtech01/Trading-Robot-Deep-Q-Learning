"""
crypto_env.py - Ambiente de simulação para Criptomoedas com taxas de Exchange (Binance/Bybit).
"""

import numpy as np
import pandas as pd


class CryptoTradingEnv:
    """
    Ambiente de simulação de negociação para pares de Cripto (ex: BTC/USDT).
    """

    def __init__(
        self,
        df: pd.DataFrame,
        initial_balance: float = 1000.0,  # $ 1.000 USDT
        exchange_fee: float = 0.001,      # 0,10% (taxa padrão de corretoras de cripto)
        window_size: int = 5,
    ):
        self.df = df.reset_index()
        self.initial_balance = initial_balance
        self.exchange_fee = exchange_fee
        self.window_size = window_size

        # Features adaptadas para cripto
        self.feature_cols = [
            "Return_1d",
            "Return_5d",
            "Dist_SMA21",
            "RSI_14",
            "Bollinger_PctB",
            "Volatility_14",
        ]
        self.n_features = len(self.feature_cols)

        # Tamanho do estado
        self.state_size = (self.window_size * self.n_features) + 2
        self.action_space = 3  # 0: Hold, 1: Buy, 2: Sell

        self.reset()

    def reset(self):
        """Reinicia o ambiente para uma nova época de simulação."""
        self.current_step = self.window_size
        self.balance = self.initial_balance
        self.crypto_held = 0.0
        self.buy_price = 0.0
        self.buy_step = 0
        self.cost_basis = 0.0
        self.total_fees_paid = 0.0

        self.portfolio_history = [self.initial_balance]
        self.dates_history = [self.df.loc[self.current_step, "Date"]]
        self.trade_log = []

        return self._get_state()

    def _get_state(self) -> np.ndarray:
        """Monta o vetor de estado para a rede neural."""
        start = self.current_step - self.window_size
        end = self.current_step

        window_features = self.df.loc[start:end - 1, self.feature_cols].values.flatten()

        current_price = float(self.df.loc[self.current_step, "Close"])
        is_holding = 1.0 if self.crypto_held > 0 else 0.0
        unrealized_pnl = 0.0
        if self.crypto_held > 0 and self.buy_price > 0:
            unrealized_pnl = (current_price - self.buy_price) / self.buy_price

        state = np.concatenate([window_features, [is_holding, unrealized_pnl]])
        return state.astype(np.float32)

    def step(self, action: int):
        """
        Executa uma ação no mercado cripto.
        0: Hold (Manter/Aguardar)
        1: Buy (Comprar 100% em Cripto)
        2: Sell (Vender 100% para USDT)
        """
        current_price = float(self.df.loc[self.current_step, "Close"])
        current_date = self.df.loc[self.current_step, "Date"]
        reward = 0.0

        # 1. COMPRA
        if action == 1 and self.crypto_held == 0:
            fee = self.balance * self.exchange_fee
            capital_available = self.balance - fee
            self.cost_basis = capital_available
            self.crypto_held = capital_available / current_price
            self.buy_price = current_price
            self.buy_step = self.current_step
            self.balance = 0.0
            self.total_fees_paid += fee

        # 2. VENDA
        elif action == 2 and self.crypto_held > 0:
            gross_sale = self.crypto_held * current_price
            fee = gross_sale * self.exchange_fee
            net_sale = gross_sale - fee
            self.total_fees_paid += fee

            trade_profit_cash = net_sale - self.cost_basis
            trade_profit_pct = (current_price - self.buy_price) / self.buy_price
            net_profit_pct = trade_profit_cash / (self.cost_basis + 1e-9)

            self.balance = net_sale
            self.crypto_held = 0.0

            # Recompensa por trade líquido (amplificada para guiar a rede neural)
            reward = net_profit_pct * 10.0

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
            if self.crypto_held > 0:
                daily_return = float(self.df.loc[self.current_step, "Return_1d"])
                reward = daily_return * 0.5
            else:
                daily_return = float(self.df.loc[self.current_step, "Return_1d"])
                if daily_return < -0.02:
                    reward = 0.03  # Bônus por ficar em USDT durante um 'dump' de cripto

        portfolio_value = self.balance + (self.crypto_held * current_price)
        self.portfolio_history.append(portfolio_value)
        self.dates_history.append(current_date)

        self.current_step += 1
        done = self.current_step >= len(self.df) - 1

        next_state = self._get_state() if not done else np.zeros(self.state_size, dtype=np.float32)

        return next_state, reward, done, {"portfolio_value": portfolio_value}
