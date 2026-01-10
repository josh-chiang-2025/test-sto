"""
主程式 - 台股回測工具
"""

import logging
import os
import argparse
import importlib
from database import StockDatabase
from backtesting import BacktestEngine
import config

# 確保 output 目錄存在
os.makedirs('output', exist_ok=True)

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_PATH, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def parse_arguments():
    """解析命令列參數"""
    parser = argparse.ArgumentParser(
        description='台股回測工具 - 支持命令列參數指定策略',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
範例用法:
  python main.py                                    # 使用 config.py 中的預設策略
  python main.py -s strategy.strategy_sample1       # 使用 sample1 策略
  python main.py --strategy strategy.strategy_sample2  # 使用 sample2 策略
        '''
    )
    
    parser.add_argument(
        '-s', '--strategy',
        dest='strategy',
        type=str,
        default=None,
        help='策略模組路徑 (預設: 使用 config.py 中的 STRATEGY_MODULE)'
    )
    
    return parser.parse_args()


def main():
    """主函數"""
    logger.info("=" * 80)
    logger.info("台股回測工具啟動")
    logger.info("=" * 80)
    
    try:
        # 解析命令列參數
        args = parse_arguments()
        
        # 決定使用的策略模組
        strategy_module_path = args.strategy if args.strategy else config.STRATEGY_MODULE
        
        # 動態導入策略模組
        logger.info(f"步驟 0: 加載策略模組 ({strategy_module_path})")
        strategy_module = importlib.import_module(strategy_module_path)
        
        # 初始化資料庫
        logger.info("步驟 1: 初始化資料庫")
        db = StockDatabase()
        
        # 初始化策略（可以在這裡改變使用的策略）
        logger.info("步驟 2: 初始化策略")
        strategy = strategy_module.StrategyInstance(db)
        strategy_description = strategy_module.get_strategy_description()
        report_name = strategy_module.get_report_name()
        
        # 預先載入目標股票的資料（避免回測時反覆從網路下載）
        logger.info("步驟 2.5: 預先載入目標股票資料")
        if hasattr(strategy, 'target_stocks'):
            for stock_id in strategy.target_stocks:
                logger.info(f"  預載股票 {stock_id}...")
                db._ensure_stock_data(stock_id)
        
        # 初始化回測引擎
        logger.info("步驟 3: 初始化回測引擎")
        engine = BacktestEngine(db, strategy, config.INITIAL_CAPITAL, strategy_description)
        
        # 執行回測
        logger.info("步驟 4: 執行回測")
        engine.run()
        
        # 生成報告
        logger.info("步驟 5: 生成報告")
        report_path = f"output/report_{report_name}.html"
        engine.generate_report(report_path)
        
        logger.info("=" * 80)
        logger.info(f"回測完成！報告已儲存至: {report_path}")
        logger.info("=" * 80)
        
        # 關閉資料庫
        db.close()
        
    except Exception as e:
        logger.error(f"執行過程中發生錯誤: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
