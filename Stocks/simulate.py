"""
模拟量化投资 — 每次运行：
1. 拉取美股 / A股日线
2. 用双均线+RSI 生成买卖信号
3. 在纸上账户成交并保存

用法（在 Stocks 目录下）:
  pip install -r requirements.txt
  python simulate.py
"""

from __future__ import annotations

import sys

from config import CN_WATCHLIST, US_WATCHLIST
from market_data import fetch_many
from portfolio import execute_signal, load_portfolio, mark_to_market, save_portfolio
from strategy import decide

# Windows 控制台默认可能是 cp1252，避免中文打印炸裂
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _banner(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    _banner("Foryesify 纸上模拟盘（非真实交易）")
    print("策略: 空仓遇多头开仓 / 持仓遇空头平仓（双均线+RSI）")
    print("本金账户: 人民币 / 美元 分开记账，不做汇率换算")

    portfolio = load_portfolio()

    _banner("1) 拉取行情")
    print("美股:")
    us_quotes = fetch_many(US_WATCHLIST)
    print("A股:")
    cn_quotes = fetch_many(CN_WATCHLIST)
    quotes = us_quotes + cn_quotes
    if not quotes:
        print("全部拉取失败，请检查网络后重试。")
        return

    prices = {q.symbol: q.price for q in quotes}

    _banner("2) 生成信号并纸上成交")
    for q in quotes:
        has_pos = q.symbol in portfolio.positions
        signal = decide(q, has_position=has_pos)
        msg = execute_signal(portfolio, signal)
        print(f"  {msg}")

    save_portfolio(portfolio)
    mtm = mark_to_market(portfolio, prices)

    _banner("3) 账户快照")
    print(f"  现金 CNY: ¥{portfolio.cash_cny:,.2f}")
    print(f"  现金 USD: ${portfolio.cash_usd:,.2f}")
    if portfolio.positions:
        print("  持仓:")
        for pos in portfolio.positions.values():
            px = prices.get(pos.symbol, pos.avg_cost)
            value = pos.shares * px
            pnl = (px - pos.avg_cost) * pos.shares
            unit = "¥" if pos.currency == "CNY" else "$"
            print(
                f"    {pos.symbol:12} {pos.shares:g} 股  "
                f"成本 {unit}{pos.avg_cost:.2f}  现价 {unit}{px:.2f}  "
                f"市值 {unit}{value:,.2f}  盈亏 {unit}{pnl:,.2f}"
            )
    else:
        print("  持仓: （空仓）")

    print()
    print(
        f"  权益估值  CNY ¥{mtm['equity_cny']:,.2f} "
        f"（相对初始 {mtm['pnl_cny']:+,.2f}）"
    )
    print(
        f"  权益估值  USD ${mtm['equity_usd']:,.2f} "
        f"（相对初始 {mtm['pnl_usd']:+,.2f}）"
    )
    print()
    print("状态已写入 portfolio.json，成交记录见 trade_log.csv")
    print("再次运行本脚本会在同一账户上继续模拟。")


if __name__ == "__main__":
    main()
