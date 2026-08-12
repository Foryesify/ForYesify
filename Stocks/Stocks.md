# Stocks

一个模拟股票交易的命令行工具，从可用的源拉取股票情况并提供模拟买入、买出等功能。

支持A股、港股和美股，随便玩玩而已，

全项目使用AI完成。

## 我看好的几个无脑股

美股那边经济正常的情况下简直是捡钱，这几个股票我觉得无脑长线就行：

- QQQM （对应NASDAQ）
- VOO （对应S&P 500）
- AAPL
- GOOG
- MSFT （三巨头）
- NVDA
- SPCX
- NET （Cloudflare感觉潜力还可以）
- P （Everpure一个玩B端的公司）

谨慎购买的：

- AMAT
- AMD （这俩冲太高了最近一直在跌）
- GE
- BA
- PEP
- HD
- SBUX （几个老登股，不太看好，不过收益应该也会还行）

港股方面，买小米，今年下半年小米大概率会涨，长线应该冲100没问题。

- 1810 （Xiaomi）

## 命令行

```plain
python Stocks.py --list
  ID: 1, NAME: xxx CN|HK|US, PRICE: xxx, YESTERDAY: +|-xxx, RETURN_TOTAL: +|-xxx%
  ID: 2, NAME: xxx CN|HK|US, PRICE: xxx, YESTERDAY: +|-xxx, RETURN_TOTAL: +|-xxx%
  ID: 3, NAME: xxx CN|HK|US, PRICE: xxx, YESTERDAY: +|-xxx, RETURN_TOTAL: +|-xxx%
python Stocks.py --total
  TOTAL: CNY +|-xxx (+|-xxx%), HKD +|-xxx (+|-xxx%), USD +|-xxx (+|-xxx%)
  failed, reason: xxx
python Stocks.py --buy STOCK_NAME --in CN|HK|US --amount xxx （若amount不足且不支持碎股则拒绝）
  success, ID: xxx
  failed, reason: xxx
python Stocks.py --sell ID
  success, RETURN_TOTAL: +|-xxx%
  failed, reason: xxx
```

ID要求连续。

## 其他要求

本金：RMB 5000 HKD 3000 USD 3000。

默认长期持有我上面推荐的股票，谨慎购买的股票应当金额少于推荐股。

A股初始化时暂不购买，因为过于诡异。
