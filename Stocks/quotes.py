"""股票行情获取 — 使用国内可访问的数据源，不依赖 Yahoo Finance。"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable


@dataclass
class Quote:
    symbol: str
    name: str
    market: str
    price: float
    yesterday_change: float


class QuoteError(Exception):
    pass


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn/",
}


def normalize_symbol(market: str, symbol: str) -> str:
    market = market.upper()
    symbol = symbol.strip().upper()
    if market == "CN":
        if not re.fullmatch(r"\d{6}", symbol):
            raise QuoteError("A股代码应为 6 位数字，例如 600519")
        return symbol
    if market == "HK":
        if not re.fullmatch(r"\d{1,5}", symbol):
            raise QuoteError("港股代码应为 1-5 位数字，例如 01810")
        return symbol.zfill(5)
    if market == "US":
        if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,14}", symbol):
            raise QuoteError("美股代码格式无效，例如 AAPL")
        return symbol
    raise QuoteError(f"不支持的市场: {market}")


def _http_get(url: str, timeout: float = 12.0) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _eastmoney_secids(market: str, symbol: str) -> list[str]:
    if market == "CN":
        if symbol.startswith(("5", "6", "9")):
            return [f"1.{symbol}"]
        return [f"0.{symbol}"]
    if market == "HK":
        return [f"116.{symbol}"]
    return [f"105.{symbol}", f"106.{symbol}"]


def _fetch_eastmoney(market: str, symbol: str) -> Quote | None:
    fields = "f43,f57,f58,f169,f170"
    for secid in _eastmoney_secids(market, symbol):
        url = (
            "https://push2.eastmoney.com/api/qt/stock/get"
            f"?secid={secid}&fields={fields}&fltt=2"
        )
        try:
            payload = json.loads(_http_get(url).decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
            continue

        data = payload.get("data") or {}
        price = data.get("f43")
        if price in (None, "-", 0, 0.0):
            continue

        change = data.get("f169", 0)
        display_name = data.get("f58") or data.get("f57") or symbol
        return Quote(
            symbol=symbol,
            name=str(display_name),
            market=market,
            price=float(price),
            yesterday_change=float(change or 0),
        )
    return None


def _sina_code(market: str, symbol: str) -> str:
    if market == "CN":
        prefix = "sh" if symbol.startswith(("5", "6", "9")) else "sz"
        return f"{prefix}{symbol}"
    if market == "HK":
        return f"hk{symbol}"
    return f"gb_{symbol.lower()}"


def _parse_sina_line(raw: str) -> list[str]:
    match = re.search(r'="([^"]*)"', raw)
    if not match or not match.group(1):
        return []
    return match.group(1).split(",")


def _fetch_sina(market: str, symbol: str) -> Quote | None:
    code = _sina_code(market, symbol)
    url = f"https://hq.sinajs.cn/list={code}"
    try:
        raw = _http_get(url).decode("gbk", errors="replace")
    except (urllib.error.URLError, TimeoutError):
        return None

    parts = _parse_sina_line(raw)
    if not parts:
        return None

    try:
        if market == "CN":
            name = parts[0]
            prev_close = float(parts[2] or 0)
            price = float(parts[3] or 0)
        elif market == "HK":
            name = parts[1] or symbol
            prev_close = float(parts[3] or 0)
            price = float(parts[6] or 0)
        else:
            name = parts[0] or symbol
            prev_close = float(parts[26] or 0) if len(parts) > 26 else 0.0
            price = float(parts[1] or 0)
    except (ValueError, IndexError):
        return None

    if price <= 0:
        return None

    yesterday_change = price - prev_close if prev_close > 0 else 0.0
    return Quote(
        symbol=symbol,
        name=name,
        market=market,
        price=price,
        yesterday_change=yesterday_change,
    )


def _fetch_stooq(market: str, symbol: str) -> Quote | None:
    if market != "US":
        return None

    suffix = symbol.lower().replace(".", "-")
    url = f"https://stooq.com/q/l/?s={suffix}.us&i=d"
    try:
        raw = _http_get(url).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError):
        return None

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) < 2:
        return None

    header = lines[0].split(",")
    values = lines[1].split(",")
    if len(values) < 7:
        return None

    try:
        close_idx = header.index("Close")
        open_idx = header.index("Open")
        close = float(values[close_idx])
        open_price = float(values[open_idx])
    except (ValueError, IndexError):
        return None

    if close <= 0:
        return None

    return Quote(
        symbol=symbol,
        name=symbol,
        market=market,
        price=close,
        yesterday_change=close - open_price,
    )


_FETCHERS: list[Callable[[str, str], Quote | None]] = [
    _fetch_eastmoney,
    _fetch_sina,
    _fetch_stooq,
]


def get_quote(market: str, symbol: str) -> Quote:
    market = market.upper()
    symbol = normalize_symbol(market, symbol)

    errors: list[str] = []
    for fetcher in _FETCHERS:
        try:
            quote = fetcher(market, symbol)
        except Exception as exc:  # noqa: BLE001 - collect fallback errors
            errors.append(str(exc))
            continue
        if quote is not None:
            return quote

    detail = errors[-1] if errors else "所有数据源均无响应"
    raise QuoteError(f"无法获取 {symbol} ({market}) 行情: {detail}")
