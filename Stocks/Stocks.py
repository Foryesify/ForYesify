#!/usr/bin/env python3
"""模拟股票交易命令行工具。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from portfolio import Portfolio, PortfolioError
from quotes import QuoteError, get_quote


def fmt_signed(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}"


def fmt_return_pct(buy_price: float, current_price: float) -> str:
    if buy_price <= 0:
        return "N/A"
    pct = (current_price - buy_price) / buy_price * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def print_cash(portfolio: Portfolio) -> None:
    print(
        "CASH: "
        f"CNY {portfolio.cash['CNY']:.2f}, "
        f"HKD {portfolio.cash['HKD']:.2f}, "
        f"USD {portfolio.cash['USD']:.2f}"
    )


def cmd_list(portfolio: Portfolio) -> int:
    if not portfolio.holdings:
        print_cash(portfolio)
        return 0

    for holding in portfolio.holdings:
        try:
            quote = get_quote(holding.market, holding.symbol)
        except QuoteError as exc:
            print(
                f"ID: {holding.id}, NAME: {holding.symbol} {holding.market}, "
                f"PRICE: N/A, YESTERDAY: N/A, RETURN_TOTAL: N/A "
                f"(行情获取失败: {exc})"
            )
            continue

        total_return = fmt_return_pct(holding.buy_price, quote.price)
        print(
            f"ID: {holding.id}, NAME: {quote.name} {holding.market}, "
            f"PRICE: {quote.price:.2f}, "
            f"YESTERDAY: {fmt_signed(quote.yesterday_change)}, "
            f"RETURN_TOTAL: {total_return}"
        )

    print_cash(portfolio)
    return 0


def cmd_buy(portfolio: Portfolio, symbol: str, market: str, amount: float) -> int:
    market = market.upper()
    try:
        quote = get_quote(market, symbol)
        holding = portfolio.buy_by_amount(symbol, market, quote, amount)
    except QuoteError as exc:
        print(f"failed, reason: {exc}")
        return 1
    except PortfolioError as exc:
        print(f"failed, reason: {exc}")
        return 1

    print(f"success, ID: {holding.id}")
    return 0


def cmd_sell(portfolio: Portfolio, holding_id: int) -> int:
    try:
        holding = portfolio.get(holding_id)
        quote = get_quote(holding.market, holding.symbol)
        total_return = fmt_return_pct(holding.buy_price, quote.price)
        portfolio.sell(holding_id, quote)
    except KeyError as exc:
        print(f"failed, reason: {exc}")
        return 1
    except QuoteError as exc:
        print(f"failed, reason: {exc}")
        return 1

    print(f"success, RETURN_TOTAL: {total_return}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="模拟股票交易 CLI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="列出当前持仓")
    group.add_argument("--buy", metavar="STOCK_NAME", help="模拟买入股票")
    group.add_argument("--sell", metavar="ID", type=int, help="按 ID 卖出持仓")
    parser.add_argument(
        "--in",
        dest="market",
        choices=["CN", "HK", "US"],
        help="市场：CN(A股) / HK(港股) / US(美股)，买入时必填",
    )
    parser.add_argument(
        "--amount",
        type=float,
        help="买入金额，币种与 --in 对应；美股支持碎股按金额成交",
    )
    return parser


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)

    data_path = Path(__file__).resolve().parent / "portfolio.json"
    portfolio = Portfolio(data_path)
    portfolio.ensure_initialized()

    if args.list:
        return cmd_list(portfolio)

    if args.buy:
        if not args.market:
            print("failed, reason: 买入时必须指定 --in CN|HK|US")
            return 1
        if args.amount is None:
            print("failed, reason: 买入时必须指定 --amount 金额")
            return 1
        return cmd_buy(portfolio, args.buy, args.market, args.amount)

    if args.sell is not None:
        return cmd_sell(portfolio, args.sell)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
