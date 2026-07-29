"""纸上账户：双币现金 + 持仓持久化。"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import (
    INITIAL_CNY,
    INITIAL_USD,
    PORTFOLIO_PATH,
    POSITION_PCT,
    TRADE_LOG_PATH,
)
from strategy import Action, Signal


@dataclass
class Position:
    symbol: str
    market: str
    currency: str
    shares: float
    avg_cost: float


@dataclass
class Portfolio:
    cash_cny: float = INITIAL_CNY
    cash_usd: float = INITIAL_USD
    positions: dict[str, Position] = field(default_factory=dict)
    updated_at: str = ""

    def cash(self, currency: str) -> float:
        return self.cash_cny if currency == "CNY" else self.cash_usd

    def set_cash(self, currency: str, value: float) -> None:
        if currency == "CNY":
            self.cash_cny = value
        else:
            self.cash_usd = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "cash_cny": self.cash_cny,
            "cash_usd": self.cash_usd,
            "positions": {k: asdict(v) for k, v in self.positions.items()},
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Portfolio":
        positions = {
            k: Position(**v) for k, v in data.get("positions", {}).items()
        }
        return cls(
            cash_cny=float(data.get("cash_cny", INITIAL_CNY)),
            cash_usd=float(data.get("cash_usd", INITIAL_USD)),
            positions=positions,
            updated_at=str(data.get("updated_at", "")),
        )


def load_portfolio(path: Path = PORTFOLIO_PATH) -> Portfolio:
    if not path.exists():
        p = Portfolio()
        p.updated_at = _now()
        save_portfolio(p, path)
        print(f"已创建新模拟账户 → {path.name}")
        print(f"  初始本金: ¥{INITIAL_CNY:,.2f} + ${INITIAL_USD:,.2f}")
        return p
    with path.open("r", encoding="utf-8") as f:
        return Portfolio.from_dict(json.load(f))


def save_portfolio(portfolio: Portfolio, path: Path = PORTFOLIO_PATH) -> None:
    portfolio.updated_at = _now()
    with path.open("w", encoding="utf-8") as f:
        json.dump(portfolio.to_dict(), f, ensure_ascii=False, indent=2)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _append_trade(row: dict[str, Any]) -> None:
    exists = TRADE_LOG_PATH.exists()
    with TRADE_LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "time",
                "action",
                "symbol",
                "market",
                "currency",
                "shares",
                "price",
                "amount",
                "reason",
            ],
        )
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def execute_signal(portfolio: Portfolio, signal: Signal) -> str:
    """按信号做纸上成交，返回人类可读结果。"""
    symbol = signal.symbol
    price = signal.price
    currency = signal.currency
    pos = portfolio.positions.get(symbol)

    if signal.action == Action.HOLD:
        held = pos.shares if pos else 0.0
        return f"HOLD {symbol} @ {price:.4f}（持仓 {held:g}）— {signal.reason}"

    if signal.action == Action.BUY:
        # 已持仓不再加仓，避免每天跑脚本把现金打光
        if pos is not None and pos.shares > 0:
            return (
                f"BUY 跳过 {symbol}：已持有 {pos.shares:g} 股，不加仓 — "
                f"{signal.reason}"
            )

        cash = portfolio.cash(currency)
        budget = cash * POSITION_PCT
        if budget < price:
            return f"BUY 跳过 {symbol}：现金不足（可用 {currency} {cash:.2f}）"

        shares = budget / price
        # A股一手 100 股；美股按小数股模拟（方便小资金）
        if currency == "CNY":
            shares = (shares // 100) * 100
            if shares < 100:
                return f"BUY 跳过 {symbol}：不够一手（需约 {price * 100:.2f} CNY）"

        cost = shares * price
        if cost > cash:
            return f"BUY 跳过 {symbol}：现金不足"

        portfolio.positions[symbol] = Position(
            symbol=symbol,
            market=signal.market,
            currency=currency,
            shares=shares,
            avg_cost=price,
        )

        portfolio.set_cash(currency, cash - cost)
        _append_trade(
            {
                "time": _now(),
                "action": "BUY",
                "symbol": symbol,
                "market": signal.market,
                "currency": currency,
                "shares": f"{shares:g}",
                "price": f"{price:.4f}",
                "amount": f"{cost:.2f}",
                "reason": signal.reason,
            }
        )
        unit = "¥" if currency == "CNY" else "$"
        return (
            f"BUY  {symbol} x{shares:g} @ {price:.4f} "
            f"花费 {unit}{cost:,.2f} — {signal.reason}"
        )

    # SELL
    if pos is None or pos.shares <= 0:
        return f"SELL 跳过 {symbol}：无持仓 — {signal.reason}"

    shares = pos.shares
    # A股卖出按整手；若不足一手则全清
    if currency == "CNY" and shares >= 100:
        sell_shares = (shares // 100) * 100
        # 信号为卖出时清掉整手部分；若剩零股一并清
        if sell_shares == shares or shares - sell_shares < 100:
            sell_shares = shares
    else:
        sell_shares = shares

    proceeds = sell_shares * price
    cash = portfolio.cash(currency)
    portfolio.set_cash(currency, cash + proceeds)

    pnl = (price - pos.avg_cost) * sell_shares
    pos.shares -= sell_shares
    if pos.shares <= 1e-9:
        del portfolio.positions[symbol]

    _append_trade(
        {
            "time": _now(),
            "action": "SELL",
            "symbol": symbol,
            "market": signal.market,
            "currency": currency,
            "shares": f"{sell_shares:g}",
            "price": f"{price:.4f}",
            "amount": f"{proceeds:.2f}",
            "reason": signal.reason,
        }
    )
    unit = "¥" if currency == "CNY" else "$"
    return (
        f"SELL {symbol} x{sell_shares:g} @ {price:.4f} "
        f"收回 {unit}{proceeds:,.2f}（浮动盈亏 {unit}{pnl:,.2f}）— {signal.reason}"
    )


def mark_to_market(
    portfolio: Portfolio, prices: dict[str, float]
) -> dict[str, float]:
    """按最新价估算市值（分币种，不做汇率换算）。"""
    equity_cny = portfolio.cash_cny
    equity_usd = portfolio.cash_usd
    for symbol, pos in portfolio.positions.items():
        px = prices.get(symbol, pos.avg_cost)
        value = pos.shares * px
        if pos.currency == "CNY":
            equity_cny += value
        else:
            equity_usd += value
    return {
        "equity_cny": equity_cny,
        "equity_usd": equity_usd,
        "pnl_cny": equity_cny - INITIAL_CNY,
        "pnl_usd": equity_usd - INITIAL_USD,
    }
