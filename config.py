"""
配置文件 - 台股回測工具全局配置
"""

# 策略設定
STRATEGY_MODULE = "strategy.strategy_sample1"  # 使用的策略模組
# 可選值：
#   - "strategy.strategy_sample1"  # 2330 漲幅策略
#   - "strategy.strategy_sample2"  # 0050 成交量策略

# 回測設定
INITIAL_CAPITAL = 100000  # 初始資金（元）
BACKTEST_DAYS = 180  # 回測區間（天數）

# 交易成本
BUY_FEE_RATE = 0.0004  # 買入手續費率 0.04%
SELL_FEE_RATE = 0.0004  # 賣出手續費率 0.04%
SELL_TAX_RATE = 0.003   # 證交稅率 0.3%
MIN_FEE = 1  # 手續費最低消費（元）
MIN_TRANSACTION = 6000  # 最低交易金額（元）

# 資料庫設定
DB_PATH = "data/stock_data.db"  # 本地資料庫路徑

# 日誌設定
LOG_PATH = "output/running.log"  # 日誌檔案路徑

# 報告設定
REPORT_PATH = "output/report.html"  # 回測報告路徑
CHART_PATH = "output"  # 圖表輸出路徑
CHART_FILENAME_TEMPLATE = "database_{stock_id}_chart.html"  # 圖表檔案名稱範本
