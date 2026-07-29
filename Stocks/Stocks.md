# Stocks — 纸上模拟量化

每次运行 `simulate.py` 会：

1. 拉取美股 + A股日线（统一走 **东方财富**；不用 Yahoo，避免限流）  
2. 用 **双均线趋势 + RSI**：空仓遇多头开仓、持仓遇空头平仓（已持有不加仓）  
3. 在本地纸上账户成交（初始 **¥10,000 + $10,000**）

> 这是玩具模拟，不是投资建议。真实市场有手续费、滑点、涨跌停、汇率、税费……这里都极度简化了。

## 快速开始

```bash
cd Stocks
pip install -r requirements.txt
python simulate.py
```

再次运行会在同一账户上继续（状态在 `portfolio.json`）。  
行情会缓存到 `data_cache/`（默认 12 小时），当天反复跑基本不打网。

## 文件

| 文件 | 作用 |
|------|------|
| `simulate.py` | 入口 |
| `config.py` | 本金、标的池、均线参数、缓存时长 |
| `market_data.py` | 拉行情（东方财富 + 本地缓存） |
| `strategy.py` | 信号逻辑 |
| `portfolio.py` | 现金/持仓/成交 |
| `portfolio.json` | 运行后生成的账户快照 |
| `trade_log.csv` | 运行后生成的成交流水 |
| `data_cache/` | 运行后生成的行情缓存 |

## 想改什么

- 标的：改 `config.py` 里的 `US_WATCHLIST` / `CN_WATCHLIST`  
- 激进度：改 `POSITION_PCT`（单次开仓占该币种现金比例）  
- 均线：改 `SMA_SHORT` / `SMA_LONG`  
- 清空重来：删掉 `portfolio.json` 和 `trade_log.csv` 再运行
