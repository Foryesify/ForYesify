"""拉取美股 / A股日线。

不用 Yahoo（国内极易限流），统一走东方财富：
- A股: secid = 1.xxxxxx / 0.xxxxxx
- 美股: 先搜索得到 QuoteID（如 105.AAPL / 107.SPY）再拉 K 线
本地缓存默认 12 小时，当天反复跑基本不打网。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd

from config import CACHE_DIR, CACHE_MAX_AGE_HOURS, LOOKBACK_DAYS

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_SECID_CACHE = CACHE_DIR / "us_secid.json"


@dataclass
class Quote:
    symbol: str
    market: str  # "US" | "CN"
    currency: str  # "USD" | "CNY"
    price: float
    history: pd.DataFrame  # Open High Low Close Volume
    source: str = ""


def _market_of(symbol: str) -> tuple[str, str]:
    if symbol.endswith((".SS", ".SZ")):
        return "CN", "CNY"
    return "US", "USD"


def _http_get(url: str, timeout: float = 20.0) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": _UA,
            "Referer": "https://quote.eastmoney.com/",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _normalize(df: pd.DataFrame, lookback_days: int) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None

    lower_map = {str(c).strip().lower(): c for c in df.columns}
    needed = ("open", "high", "low", "close", "volume")
    if not all(k in lower_map for k in needed):
        return None

    out = pd.DataFrame(
        {
            "Open": pd.to_numeric(df[lower_map["open"]], errors="coerce"),
            "High": pd.to_numeric(df[lower_map["high"]], errors="coerce"),
            "Low": pd.to_numeric(df[lower_map["low"]], errors="coerce"),
            "Close": pd.to_numeric(df[lower_map["close"]], errors="coerce"),
            "Volume": pd.to_numeric(df[lower_map["volume"]], errors="coerce"),
        },
        index=df.index,
    )
    out = out.dropna(subset=["Close"]).sort_index().tail(lookback_days)
    if len(out) < 25:
        return None
    return out


def _cache_path(symbol: str) -> Path:
    safe = symbol.replace("/", "_").replace("\\", "_")
    return CACHE_DIR / f"{safe}.csv"


def _load_cache(symbol: str, lookback_days: int, *, allow_stale: bool = False) -> pd.DataFrame | None:
    path = _cache_path(symbol)
    if not path.exists():
        return None
    if not allow_stale:
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        )
        if age > timedelta(hours=CACHE_MAX_AGE_HOURS):
            return None
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
    except Exception:  # noqa: BLE001
        return None
    return _normalize(df, lookback_days)


def _save_cache(symbol: str, df: pd.DataFrame) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(_cache_path(symbol))


def _cn_secid(symbol: str) -> str | None:
    if symbol.endswith(".SS"):
        return f"1.{symbol[:-3]}"
    if symbol.endswith(".SZ"):
        return f"0.{symbol[:-3]}"
    return None


def _load_secid_map() -> dict[str, str]:
    if not _SECID_CACHE.exists():
        return {}
    try:
        return json.loads(_SECID_CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_secid_map(mapping: dict[str, str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _SECID_CACHE.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _resolve_us_secid(symbol: str) -> str | None:
    """用东财搜索拿到美股 QuoteID，例如 105.AAPL / 107.SPY。"""
    mapping = _load_secid_map()
    if symbol in mapping:
        return mapping[symbol]

    url = (
        "https://searchapi.eastmoney.com/api/suggest/get"
        f"?input={quote(symbol)}"
        "&type=14"
        "&token=D43BF722C8E33BDC906FB84D85E326E8"
        "&count=10"
    )
    try:
        payload = json.loads(_http_get(url).decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        print(f"  [东财搜索失败] {symbol}: {exc}")
        # 常见 Nasdaq 美股兜底
        return f"105.{symbol}"

    rows = ((payload or {}).get("QuotationCodeTable") or {}).get("Data") or []
    secid = None
    for row in rows:
        code = str(row.get("Code") or "").upper()
        quote_id = str(row.get("QuoteID") or "")
        classify = str(row.get("Classify") or "")
        if code == symbol.upper() and quote_id and "UsStock" in classify:
            secid = quote_id
            break
    if secid is None:
        for row in rows:
            code = str(row.get("Code") or "").upper()
            quote_id = str(row.get("QuoteID") or "")
            if code == symbol.upper() and quote_id:
                secid = quote_id
                break
    if secid is None:
        secid = f"105.{symbol}"

    mapping[symbol] = secid
    _save_secid_map(mapping)
    return secid


def _fetch_eastmoney_klines(secid: str, lookback_days: int) -> pd.DataFrame | None:
    lmt = max(lookback_days + 40, 120)
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}"
        "&ut=fa5fd1943c7b386f172d6893dbfba10b"
        "&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        "&klt=101&fqt=1&end=20500101"
        f"&lmt={lmt}"
    )
    try:
        payload = json.loads(_http_get(url).decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        print(f"  [东财K线失败] {secid}: {exc}")
        return None

    data = (payload or {}).get("data") or {}
    klines = data.get("klines") or []
    if not klines:
        return None

    rows = []
    for line in klines:
        parts = str(line).split(",")
        if len(parts) < 6:
            continue
        # 东财顺序: date, open, close, high, low, volume, ...
        rows.append(
            {
                "Date": parts[0],
                "Open": parts[1],
                "Close": parts[2],
                "High": parts[3],
                "Low": parts[4],
                "Volume": parts[5],
            }
        )
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
    return _normalize(df, lookback_days)


def _fetch_remote(symbol: str, lookback_days: int) -> pd.DataFrame | None:
    market, _ = _market_of(symbol)
    if market == "CN":
        secid = _cn_secid(symbol)
    else:
        secid = _resolve_us_secid(symbol)
    if not secid:
        return None

    df = _fetch_eastmoney_klines(secid, lookback_days)
    if df is not None:
        return df

    # 美股偶发市场代码不对时，再盲试常见代码
    if market == "US":
        for mkt in ("105", "106", "107"):
            alt = f"{mkt}.{symbol}"
            if alt == secid:
                continue
            df = _fetch_eastmoney_klines(alt, lookback_days)
            if df is not None:
                mapping = _load_secid_map()
                mapping[symbol] = alt
                _save_secid_map(mapping)
                return df
    return None


def fetch_quote(symbol: str, lookback_days: int = LOOKBACK_DAYS) -> Quote | None:
    market, currency = _market_of(symbol)

    cached = _load_cache(symbol, lookback_days, allow_stale=False)
    if cached is not None:
        print(f"  缓存命中 {symbol}")
        return Quote(
            symbol=symbol,
            market=market,
            currency=currency,
            price=float(cached["Close"].iloc[-1]),
            history=cached.copy(),
            source="cache",
        )

    print(f"  拉取 {symbol} ...")
    df = _fetch_remote(symbol, lookback_days)
    if df is None:
        stale = _load_cache(symbol, lookback_days, allow_stale=True)
        if stale is not None:
            print(f"  [降级] {symbol} 使用过期缓存")
            return Quote(
                symbol=symbol,
                market=market,
                currency=currency,
                price=float(stale["Close"].iloc[-1]),
                history=stale.copy(),
                source="stale-cache",
            )
        print(f"  [跳过] {symbol} 无数据")
        return None

    _save_cache(symbol, df)
    return Quote(
        symbol=symbol,
        market=market,
        currency=currency,
        price=float(df["Close"].iloc[-1]),
        history=df.copy(),
        source="eastmoney",
    )


def fetch_many(symbols: list[str], pause_sec: float = 0.25) -> list[Quote]:
    quotes: list[Quote] = []
    for i, symbol in enumerate(symbols):
        q = fetch_quote(symbol)
        if q is not None:
            quotes.append(q)
        hit_network = q is None or q.source not in {"cache", "stale-cache"}
        if hit_network and i < len(symbols) - 1:
            time.sleep(pause_sec)
    return quotes
