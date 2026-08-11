"""模拟持仓、多币种本金与默认建仓。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from config import (
    CAUTIOUS_US,
    CAUTIOUS_WEIGHT,
    CN_LOT_SIZE,
    INITIAL_CASH,
    MARKET_CURRENCY,
    RECOMMENDED_HK,
    RECOMMENDED_US,
    RECOMMENDED_WEIGHT,
    US_SHARE_PRECISION,
)
from quotes import Quote, QuoteError, get_quote


@dataclass
class Holding:
    id: int
    symbol: str
    name: str
    market: str
    buy_price: float
    shares: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Holding:
        return cls(
            id=int(data["id"]),
            symbol=str(data["symbol"]),
            name=str(data["name"]),
            market=str(data["market"]).upper(),
            buy_price=float(data["buy_price"]),
            shares=float(data.get("shares", 1)),
        )

    @property
    def cost(self) -> float:
        return self.buy_price * self.shares


class PortfolioError(Exception):
    pass


class Portfolio:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.initialized = False
        self.cash: dict[str, float] = dict(INITIAL_CASH)
        self.holdings: list[Holding] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return

        with self.path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)

        self.initialized = bool(data.get("initialized", False))
        self.cash = {key: float(value) for key, value in data.get("cash", INITIAL_CASH).items()}
        self.holdings = [Holding.from_dict(item) for item in data.get("holdings", [])]
        self._renumber()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "initialized": self.initialized,
            "cash": self.cash,
            "holdings": [asdict(item) for item in self.holdings],
        }
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    def _renumber(self) -> None:
        for index, holding in enumerate(self.holdings, start=1):
            holding.id = index

    def ensure_initialized(self) -> None:
        if self.initialized:
            return

        self.cash = dict(INITIAL_CASH)
        self.holdings = []
        self._init_default_holdings()
        self.initialized = True
        self._renumber()
        self._save()

    def _init_default_holdings(self) -> None:
        total_weight = len(RECOMMENDED_US) * RECOMMENDED_WEIGHT + len(CAUTIOUS_US) * CAUTIOUS_WEIGHT
        us_total = INITIAL_CASH["USD"]
        recommended_pool = us_total * len(RECOMMENDED_US) * RECOMMENDED_WEIGHT / total_weight
        cautious_pool = us_total * len(CAUTIOUS_US) * CAUTIOUS_WEIGHT / total_weight

        self._allocate_pool(RECOMMENDED_US, "US", recommended_pool)
        self._allocate_pool(CAUTIOUS_US, "US", cautious_pool)

        for symbol in RECOMMENDED_HK:
            self._buy_with_budget(symbol, "HK", self.cash["HKD"])

    def _allocate_pool(self, symbols: list[str], market: str, pool: float) -> None:
        if not symbols or pool <= 0:
            return

        remaining = pool
        per_stock = pool / len(symbols)

        for symbol in symbols:
            spent = self._buy_with_budget(symbol, market, min(per_stock, remaining))
            remaining -= spent

        while remaining > 0:
            bought_any = False
            for symbol in symbols:
                spent = self._buy_with_budget(symbol, market, remaining)
                if spent <= 0:
                    continue
                remaining -= spent
                bought_any = True
            if not bought_any:
                break

    @staticmethod
    def _shares_for_amount(market: str, price: float, amount: float) -> float:
        if price <= 0 or amount <= 0:
            return 0.0

        market = market.upper()
        if market == "US":
            return round(amount / price, US_SHARE_PRECISION)

        whole_shares = int(amount // price)
        if market == "CN":
            lots = whole_shares // CN_LOT_SIZE
            return float(lots * CN_LOT_SIZE)
        return float(whole_shares)

    def _find_holding(self, symbol: str, market: str) -> Holding | None:
        market = market.upper()
        for holding in self.holdings:
            if holding.symbol == symbol and holding.market == market:
                return holding
        return None

    def _merge_or_add(self, quote: Quote, shares: float, cost: float) -> Holding:
        existing = self._find_holding(quote.symbol, quote.market)
        if existing is None:
            holding = Holding(
                id=len(self.holdings) + 1,
                symbol=quote.symbol,
                name=quote.name,
                market=quote.market,
                buy_price=quote.price,
                shares=shares,
            )
            self.holdings.append(holding)
            return holding

        total_cost = existing.buy_price * existing.shares + cost
        existing.shares += shares
        existing.buy_price = total_cost / existing.shares
        existing.name = quote.name
        return existing

    def _buy_with_budget(self, symbol: str, market: str, budget: float) -> float:
        if budget <= 0:
            return 0.0

        try:
            quote = get_quote(market, symbol)
        except QuoteError:
            return 0.0

        currency = MARKET_CURRENCY[market]
        affordable = min(budget, self.cash[currency])
        shares = self._shares_for_amount(market, quote.price, affordable)
        if shares <= 0:
            return 0.0

        cost = affordable if market.upper() == "US" else shares * quote.price
        self.cash[currency] -= cost
        self._merge_or_add(quote, shares, cost)
        return cost

    def buy_by_amount(self, symbol: str, market: str, quote: Quote, amount: float) -> Holding:
        market = market.upper()
        currency = MARKET_CURRENCY[market]

        if amount <= 0:
            raise PortfolioError("买入金额必须大于 0")

        if amount > self.cash[currency]:
            raise PortfolioError(
                f"{currency} 余额不足，需要 {amount:.2f}，当前 {self.cash[currency]:.2f}"
            )

        shares = self._shares_for_amount(market, quote.price, amount)
        if shares <= 0:
            if market == "CN":
                min_cost = quote.price * CN_LOT_SIZE
                raise PortfolioError(
                    f"金额不足以买入一手（{CN_LOT_SIZE} 股），至少需要 {min_cost:.2f} {currency}"
                )
            raise PortfolioError(f"金额不足以买入 1 股，至少需要 {quote.price:.2f} {currency}")

        cost = amount if market == "US" else shares * quote.price
        self.cash[currency] -= cost
        holding = self._merge_or_add(quote, shares, cost)
        self._renumber()
        self._save()
        return holding

    def sell(self, holding_id: int, quote: Quote) -> Holding:
        holding = self.get(holding_id)
        currency = MARKET_CURRENCY[holding.market]
        proceeds = quote.price * holding.shares
        self.cash[currency] += proceeds

        for index, item in enumerate(self.holdings):
            if item.id == holding_id:
                removed = self.holdings.pop(index)
                self._renumber()
                self._save()
                return removed

        raise KeyError(f"未找到 ID {holding_id}")

    def get(self, holding_id: int) -> Holding:
        for holding in self.holdings:
            if holding.id == holding_id:
                return holding
        raise KeyError(f"未找到 ID {holding_id}")
