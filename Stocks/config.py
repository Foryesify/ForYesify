"""模拟交易配置：本金、默认持仓与分配权重。"""

from __future__ import annotations

INITIAL_CASH = {
    "CNY": 5000.0,
    "HKD": 3000.0,
    "USD": 3000.0,
}

RECOMMENDED_US = [
    "QQQM",
    "VOO",
    "AAPL",
    "GOOG",
    "MSFT",
    "NVDA",
    "SPCX",
    "NET",
    "P",
]

CAUTIOUS_US = [
    "AMAT",
    "AMD",
    "GE",
    "BA",
    "PEP",
    "HD",
    "SBUX",
]

RECOMMENDED_HK = ["1810"]

RECOMMENDED_WEIGHT = 2
CAUTIOUS_WEIGHT = 1

US_SHARE_PRECISION = 6
CN_LOT_SIZE = 100

MARKET_CURRENCY = {
    "CN": "CNY",
    "HK": "HKD",
    "US": "USD",
}
