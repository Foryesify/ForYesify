"""模拟盘配置：本金、标的池、策略参数。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORTFOLIO_PATH = ROOT / "portfolio.json"
TRADE_LOG_PATH = ROOT / "trade_log.csv"
CACHE_DIR = ROOT / "data_cache"

# 行情本地缓存时长（小时）。同一天反复跑会直接读缓存，避免被限流。
CACHE_MAX_AGE_HOURS = 12

# 初始本金（模拟，非真实资金）
INITIAL_CNY = 10_000.0
INITIAL_USD = 10_000.0

# 每次运行拉取的历史天数（用于算均线）
LOOKBACK_DAYS = 90

# 双均线：短均线 / 长均线
SMA_SHORT = 5
SMA_LONG = 20

# RSI 过滤：过高不追买，过低不急卖
RSI_BUY_MAX = 75
RSI_SELL_MIN = 30

# 单次开仓最多占用该币种现金的比例；同一标的已持仓则不再加仓
POSITION_PCT = 0.25

# 美股标的（yfinance ticker）
US_WATCHLIST = [
    "AAPL",  # 苹果
    "MSFT",  # 微软
    "NVDA",  # 英伟达
    "SPY",   # 标普500 ETF
    "QQQ",   # 纳斯达克100 ETF
]

# A股标的（yfinance：上海 .SS，深圳 .SZ）
# 本金只有 1 万人民币，优先用 ETF/中低价股，避免「一手买不起」
CN_WATCHLIST = [
    "510300.SS",  # 沪深300 ETF
    "159915.SZ",  # 创业板 ETF
    "510500.SS",  # 中证500 ETF
    "000001.SZ",  # 平安银行
    "600036.SS",  # 招商银行
]
