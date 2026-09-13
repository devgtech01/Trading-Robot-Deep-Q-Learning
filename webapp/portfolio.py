"""
portfolio.py - Carteira simulada (paper trading) multiativo.

Mantém o mesmo arquivo e o mesmo formato de data/paper_wallet.json já usado por
paper_trading.py, com duas contas separadas: BRL (ações da B3) e USDT (cripto).

Diferença importante em relação ao script de linha de comando: aqui cada ordem
aloca somente o tamanho configurado no ativo (nº de ações, ou valor em USDT),
em vez de 100% do caixa — necessário para operar vários ativos ao mesmo tempo.
"""

import json
import os
import threading

from webapp import config, store

_LOCK = threading.RLock()

MIN_CASH = 1.0


def _empty_wallet() -> dict:
    return {
        "BRL": {"cash": 10000.0, "initial_cash": 10000.0, "deposits": 0.0, "positions": {}, "history": []},
        "USDT": {"cash": 1000.0, "initial_cash": 1000.0, "deposits": 0.0, "positions": {}, "history": []},
    }


def load_wallet() -> dict:
    with _LOCK:
        config.ensure_dirs()
        if not os.path.exists(config.WALLET_FILE):
            wallet = _empty_wallet()
            _save(wallet)
            return wallet
        try:
            with open(config.WALLET_FILE, "r", encoding="utf-8") as f:
                wallet = json.load(f)
        except (json.JSONDecodeError, OSError):
            wallet = _empty_wallet()

        # Completa contas/campos ausentes em arquivos criados por versões anteriores
        base = _empty_wallet()
        for currency, defaults in base.items():
            account = wallet.setdefault(currency, defaults)
            for key, value in defaults.items():
                account.setdefault(key, value)
        return wallet


def _save(wallet: dict):
    config.ensure_dirs()
    tmp = f"{config.WALLET_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(wallet, f, indent=4, ensure_ascii=False)
    os.replace(tmp, config.WALLET_FILE)


def save_wallet(wallet: dict):
    with _LOCK:
        _save(wallet)


def currency_of(asset: dict) -> str:
    return config.CURRENCY[asset["asset_class"]]


def get_position(asset: dict) -> dict | None:
    account = load_wallet()[currency_of(asset)]
    pos = account["positions"].get(asset["ticker"])
    if pos and pos.get("amount", 0) > 0:
        return pos
    return None


def holding_info(asset: dict) -> tuple[bool, float]:
    """(está comprado?, preço de compra) para alimentar o estado da rede neural."""
    pos = get_position(asset)
    return (True, float(pos["buy_price"])) if pos else (False, 0.0)


# --------------------------------------------------------------------------- #
# Execução simulada
# --------------------------------------------------------------------------- #
def execute(asset: dict, action: int, price: float, quantity: float = None) -> dict:
    """
    Aplica a ação da IA na carteira simulada.

    `quantity` sobrescreve o tamanho configurado no ativo apenas nesta ordem
    (nº de ações para B3, valor em USDT para cripto). Vendas sempre encerram a
    posição inteira: o ambiente de treino é tudo-dentro/tudo-fora, então uma
    venda parcial produziria um estado que o modelo nunca viu.

    Retorna {"executed": bool, "type": "buy"|"sell"|"none", "message": str, ...}.
    """
    size = float(quantity) if quantity is not None else float(asset["quantity"])
    ticker = asset["ticker"]
    currency = currency_of(asset)
    symbol = config.CURRENCY_SYMBOL[currency]
    fee_rate = config.FEE_CRYPTO if asset["asset_class"] == config.CLASS_CRYPTO else config.FEE_STOCK

    with _LOCK:
        wallet = load_wallet()
        account = wallet[currency]
        pos = account["positions"].get(ticker)
        is_holding = bool(pos and pos.get("amount", 0) > 0)

        # ---------------- COMPRA ----------------
        if action == 1 and not is_holding:
            if asset["asset_class"] == config.CLASS_CRYPTO:
                gross = size            # tamanho da ordem em USDT
            else:
                gross = size * price    # nº de ações * preço

            if gross < MIN_CASH:
                return {"executed": False, "type": "none",
                        "message": "Tamanho de ordem configurado é muito pequeno."}
            if account["cash"] < gross:
                return {"executed": False, "type": "none",
                        "message": f"Saldo insuficiente: precisa de {symbol} {gross:,.2f} e há {symbol} {account['cash']:,.2f}."}

            fee = gross * fee_rate
            net_capital = gross - fee
            amount = net_capital / price

            account["cash"] -= gross
            account["positions"][ticker] = {
                "amount": amount,
                "buy_price": price,
                "buy_date": store.now_iso(),
                "cost_basis": net_capital,
                "fee_paid": fee,
            }
            _save(wallet)
            return {
                "executed": True, "type": "buy", "amount": amount, "price": price,
                "fee": fee, "cash_after": account["cash"],
                "message": f"COMPRA simulada: {amount:,.6f} un. de {ticker} a {symbol} {price:,.2f} (taxa {symbol} {fee:,.2f}).",
            }

        # ---------------- VENDA ----------------
        if action == 2 and is_holding:
            amount = float(pos["amount"])
            gross_sale = amount * price
            fee = gross_sale * fee_rate
            net_sale = gross_sale - fee
            cost_basis = float(pos["cost_basis"])
            profit_cash = net_sale - cost_basis
            profit_pct = profit_cash / (cost_basis + 1e-9) * 100.0

            account["cash"] += net_sale
            account["history"].insert(0, {
                "ticker": ticker,
                "asset_class": asset["asset_class"],
                "buy_date": pos.get("buy_date"),
                "buy_price": pos["buy_price"],
                "sell_date": store.now_iso(),
                "sell_price": price,
                "amount": amount,
                "profit_cash": profit_cash,
                "profit_pct": profit_pct,
                "fee_paid": float(pos.get("fee_paid", 0.0)) + fee,
            })
            del account["positions"][ticker]
            _save(wallet)
            return {
                "executed": True, "type": "sell", "amount": amount, "price": price,
                "fee": fee, "profit_cash": profit_cash, "profit_pct": profit_pct,
                "cash_after": account["cash"],
                "message": f"VENDA simulada: {ticker} a {symbol} {price:,.2f} | Resultado {symbol} {profit_cash:+,.2f} ({profit_pct:+.2f}%).",
            }

        # ---------------- SEM AÇÃO ----------------
        if is_holding:
            pnl = (price - float(pos["buy_price"])) / float(pos["buy_price"]) * 100.0
            return {"executed": False, "type": "none",
                    "message": f"Mantendo posição em {ticker} ({pnl:+.2f}%)."}
        return {"executed": False, "type": "none", "message": f"Aguardando em caixa ({currency})."}


# --------------------------------------------------------------------------- #
# Consolidação
# --------------------------------------------------------------------------- #
def summary(prices: dict) -> dict:
    """
    Consolida as duas contas. `prices` mapeia ticker -> última cotação conhecida;
    posições sem cotação disponível são avaliadas pelo preço de compra.
    """
    wallet = load_wallet()
    out = {}
    for currency, account in wallet.items():
        positions = []
        invested = 0.0
        for ticker, pos in account["positions"].items():
            price = float(prices.get(ticker) or pos["buy_price"])
            value = float(pos["amount"]) * price
            cost = float(pos["cost_basis"])
            invested += value
            positions.append({
                "ticker": ticker,
                "amount": float(pos["amount"]),
                "buy_price": float(pos["buy_price"]),
                "buy_date": pos.get("buy_date"),
                "current_price": price,
                "market_value": value,
                "cost_basis": cost,
                "pnl_cash": value - cost,
                "pnl_pct": (value - cost) / (cost + 1e-9) * 100.0,
                "priced": ticker in prices,
            })

        equity = account["cash"] + invested
        base = float(account["initial_cash"]) + float(account.get("deposits", 0.0))
        realized = sum(float(h["profit_cash"]) for h in account["history"])
        wins = [h for h in account["history"] if float(h["profit_cash"]) > 0]

        out[currency] = {
            "currency": currency,
            "symbol": config.CURRENCY_SYMBOL[currency],
            "cash": account["cash"],
            "invested": invested,
            "equity": equity,
            "initial_cash": base,
            "total_return_pct": (equity - base) / (base + 1e-9) * 100.0,
            "total_return_cash": equity - base,
            "realized_pnl": realized,
            "open_positions": len(positions),
            "closed_trades": len(account["history"]),
            "win_rate_pct": (len(wins) / len(account["history"]) * 100.0) if account["history"] else 0.0,
            "positions": sorted(positions, key=lambda p: -p["market_value"]),
        }
    return out


def history(currency: str = None, limit: int = 100) -> list:
    wallet = load_wallet()
    entries = []
    for cur, account in wallet.items():
        if currency and cur != currency:
            continue
        for h in account["history"]:
            entries.append({**h, "currency": cur, "symbol": config.CURRENCY_SYMBOL[cur]})
    entries.sort(key=lambda e: str(e.get("sell_date") or ""), reverse=True)
    return entries[:limit]


def reset_account(currency: str, initial_cash: float) -> dict:
    with _LOCK:
        wallet = load_wallet()
        if currency not in wallet:
            raise ValueError(f"Conta {currency} inexistente.")
        wallet[currency] = {
            "cash": float(initial_cash),
            "initial_cash": float(initial_cash),
            "deposits": 0.0,
            "positions": {},
            "history": [],
        }
        _save(wallet)
        return wallet[currency]


def deposit(currency: str, amount: float) -> dict:
    with _LOCK:
        wallet = load_wallet()
        if currency not in wallet:
            raise ValueError(f"Conta {currency} inexistente.")
        wallet[currency]["cash"] += float(amount)
        wallet[currency]["deposits"] = float(wallet[currency].get("deposits", 0.0)) + float(amount)
        _save(wallet)
        return wallet[currency]
