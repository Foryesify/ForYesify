"""极简趋势策略：双均线排列 + RSI 过滤。

规则（纸上模拟，不是投资建议）：
- 空仓 + 多头排列(SMA短 > SMA长) + RSI 未过热 → 买入开仓
- 持仓 + 空头排列(SMA短 < SMA长) + RSI 未超卖 → 卖出平仓
- 其余观望（已持有且仍多头时不会反复加仓）

以前只在「金叉当天」才买，多数日子会一直空仓；现在按趋势状态开平仓。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from config import RSI_BUY_MAX, RSI_SELL_MIN, SMA_LONG, SMA_SHORT
from market_data import Quote


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Signal:
    symbol: str
    market: str
    currency: str
    price: float
    action: Action
    reason: str
    sma_short: float
    sma_long: float
    rsi: float


def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = float(rsi.iloc[-1])
    return val if np.isfinite(val) else 50.0


def decide(
    quote: Quote,
    *,
    has_position: bool = False,
    short: int = SMA_SHORT,
    long: int = SMA_LONG,
) -> Signal:
    close = quote.history["Close"].astype(float)
    sma_s = float(close.rolling(short).mean().iloc[-1])
    sma_l = float(close.rolling(long).mean().iloc[-1])
    rsi = _rsi(close)

    bullish = sma_s > sma_l
    bearish = sma_s < sma_l

    if not has_position and bullish and rsi < RSI_BUY_MAX:
        action = Action.BUY
        reason = (
            f"空仓且多头排列(SMA{short}>{long}) "
            f"RSI={rsi:.1f}<{RSI_BUY_MAX}，开仓"
        )
    elif has_position and bearish and rsi > RSI_SELL_MIN:
        action = Action.SELL
        reason = (
            f"持仓且空头排列(SMA{short}<{long}) "
            f"RSI={rsi:.1f}>{RSI_SELL_MIN}，平仓"
        )
    elif has_position and bullish:
        action = Action.HOLD
        reason = f"已持有且仍多头，继续持有 RSI={rsi:.1f}"
    elif not has_position and bullish and rsi >= RSI_BUY_MAX:
        action = Action.HOLD
        reason = f"多头但 RSI={rsi:.1f}≥{RSI_BUY_MAX} 偏热，暂不追高"
    elif not has_position and bearish:
        action = Action.HOLD
        reason = f"空仓且空头排列，观望 SMA{short}={sma_s:.2f} SMA{long}={sma_l:.2f}"
    else:
        action = Action.HOLD
        reason = (
            f"观望 SMA{short}={sma_s:.2f} SMA{long}={sma_l:.2f} RSI={rsi:.1f}"
        )

    return Signal(
        symbol=quote.symbol,
        market=quote.market,
        currency=quote.currency,
        price=quote.price,
        action=action,
        reason=reason,
        sma_short=sma_s,
        sma_long=sma_l,
        rsi=rsi,
    )
