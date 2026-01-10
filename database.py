"""
資料庫模組 - 管理台股歷史資料
"""

import sqlite3
import logging
import os
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Set
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import config

logger = logging.getLogger(__name__)


class StockDatabase:
    """台股資料庫類別"""
    
    # 假日資料檔案路徑
    HOLIDAYS_FILE = "data/holidays.json"
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = config.DB_PATH
        """
        初始化資料庫連接
        
        Args:
            db_path: 資料庫檔案路徑
        """
        self.db_path = db_path
        self.conn = None
        self._holidays_cache: Optional[Set[str]] = None  # 假日緩存
        self._init_database()
    
    def _init_database(self):
        """初始化資料庫結構"""
        logger.info(f"初始化資料庫: {self.db_path}")
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()
        
        # 建立股票基本資料表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_info (
                stock_id TEXT PRIMARY KEY,
                stock_name TEXT NOT NULL
            )
        ''')
        
        # 建立股票每日資料表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_daily (
                stock_id TEXT,
                date TEXT,
                open_price REAL,
                close_price REAL,
                high_price REAL,
                low_price REAL,
                volume INTEGER,
                change_rate REAL,
                PRIMARY KEY (stock_id, date),
                FOREIGN KEY (stock_id) REFERENCES stock_info(stock_id)
            )
        ''')
        
        self.conn.commit()
        logger.info("資料庫初始化完成")
    
    def _validate_stock_id(self, stock_id: str) -> bool:
        """
        驗證股票代號格式
        
        Args:
            stock_id: 股票代號
            
        Returns:
            是否為有效的股票代號
        """
        if not stock_id:
            return False
        # 台股代號通常是4位或6位數字
        return stock_id.isdigit() and len(stock_id) in [4, 6]
    
    def _load_holidays(self) -> Set[str]:
        """
        從本地 JSON 檔案載入假日資料（假日 + 臨時休市日）
        
        Returns:
            假日日期集合 (YYYY-MM-DD 格式)
        """
        if self._holidays_cache is not None:
            return self._holidays_cache
        
        try:
            if os.path.exists(self.HOLIDAYS_FILE):
                with open(self.HOLIDAYS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    holidays_set = set()
                    
                    # 載入假日清單
                    holidays = data.get('holidays', [])
                    if isinstance(holidays, list):
                        holidays_set.update(holidays)
                    
                    # 載入臨時休市日
                    temporary_closures = data.get('temporary_closures', [])
                    if isinstance(temporary_closures, list):
                        holidays_set.update(temporary_closures)
                    
                    self._holidays_cache = holidays_set
                    logger.info(f"成功載入 {len(self._holidays_cache)} 個休市日期")
                    return self._holidays_cache
            else:
                logger.warning(f"假日資料檔案不存在: {self.HOLIDAYS_FILE}")
                self._holidays_cache = set()
                return self._holidays_cache
        except Exception as e:
            logger.error(f"載入假日資料時出錯: {e}")
            self._holidays_cache = set()
            return self._holidays_cache
    
    def _save_holidays(self, holidays: Set[str]) -> bool:
        """
        將假日資料保存到本地 JSON 檔案 (舊版本，保留向後相容)
        
        Args:
            holidays: 假日日期集合
            
        Returns:
            是否保存成功
        """
        try:
            data = {
                'description': '台灣股市假日資料 - 包含周末和特殊假日',
                'last_updated': datetime.now().strftime('%Y-%m-%d'),
                'holidays': sorted(list(holidays)),
                'notes': '此檔案由系統自動維護。若需更新可編輯此檔案或調用 update_holidays() 方法'
            }
            
            with open(self.HOLIDAYS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"成功保存 {len(holidays)} 個假日資料到 {self.HOLIDAYS_FILE}")
            return True
        except Exception as e:
            logger.error(f"保存假日資料時出錯: {e}")
            return False
    
    def _is_market_closed(self, date: str) -> bool:
        """
        判斷指定日期是否為股市休市日期（周末或假日）
        
        Args:
            date: 日期 (YYYY-MM-DD)
            
        Returns:
            是否為股市休市日期
        """
        dt = datetime.strptime(date, "%Y-%m-%d")
        
        # 檢查是否為周末（0=Monday, 6=Sunday）
        if dt.weekday() >= 5:  # Saturday or Sunday
            return True
        
        # 從緩存檔案檢查假日
        holidays = self._load_holidays()
        return date in holidays
    
    def _fetch_stock_data_from_web(self, stock_id: str, start_date: str, end_date: str) -> List[Dict]:
        """
        從網路抓取股票資料（使用台灣證券交易所公開資料或備用API）
        
        Args:
            stock_id: 股票代號
            start_date: 開始日期 (YYYY-MM-DD)
            end_date: 結束日期 (YYYY-MM-DD)
            
        Returns:
            股票資料列表
        """
        # 驗證日期範圍
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        if start_dt > end_dt:
            logger.warning(f"無效的日期範圍: {start_date} > {end_date}，跳過抓取")
            return []
        
        logger.info(f"正在從網路抓取股票 {stock_id} 的資料 ({start_date} ~ {end_date})")
        
        # 這裡使用 twse (台灣證券交易所) API
        # 注意：實際使用時需要處理 API 限制和錯誤
        data_list = []
        
        try:
            # 逐月抓取（TWSE API 限制）
            current_date = start_dt
            while current_date <= end_dt:
                year = current_date.year
                month = current_date.month
                
                url = f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
                params = {
                    'date': f'{year}{month:02d}01',
                    'stockNo': stock_id,
                    'response': 'json'
                }
                
                logger.info(f"正在抓取 {year}年{month}月 的資料...")
                
                try:
                    response = requests.get(url, params=params, timeout=10)
                    
                    if response.status_code == 200:
                        json_data = response.json()
                        
                        # 檢查是否有資料
                        if json_data.get('stat') == 'OK' and 'data' in json_data:
                            for row in json_data['data']:
                                # row 格式: [日期, 成交股數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, 漲跌價差, 成交筆數]
                                try:
                                    date_str = row[0].replace('/', '-')  # 轉換日期格式
                                    # 將民國年轉換為西元年
                                    date_parts = date_str.split('-')
                                    roc_year = int(date_parts[0])
                                    date_str = f"{roc_year + 1911}-{date_parts[1]}-{date_parts[2]}"
                                    
                                    # 檢查日期是否在範圍內
                                    row_date = datetime.strptime(date_str, "%Y-%m-%d")
                                    if start_dt <= row_date <= end_dt:
                                        # 處理價格字串（移除逗號）
                                        open_price = float(row[3].replace(',', ''))
                                        high_price = float(row[4].replace(',', ''))
                                        low_price = float(row[5].replace(',', ''))
                                        close_price = float(row[6].replace(',', ''))
                                        volume = int(row[1].replace(',', ''))
                                        
                                        # 計算漲跌幅
                                        change_rate = 0.0
                                        if len(data_list) > 0:
                                            prev_close = data_list[-1]['close_price']
                                            if prev_close > 0:
                                                change_rate = ((close_price - prev_close) / prev_close) * 100
                                        
                                        data_list.append({
                                            'date': date_str,
                                            'open_price': open_price,
                                            'close_price': close_price,
                                            'high_price': high_price,
                                            'low_price': low_price,
                                            'volume': volume,
                                            'change_rate': change_rate
                                        })
                                except (ValueError, IndexError) as e:
                                    logger.debug(f"處理資料行時出錯: {e}")
                                    continue
                        else:
                            logger.debug(f"API 回應狀態異常或無資料: {json_data.get('stat')}")
                    else:
                        logger.debug(f"HTTP 請求失敗，狀態碼: {response.status_code}")
                    
                except requests.RequestException as e:
                    logger.warning(f"網路請求錯誤: {e}")
                except Exception as e:
                    logger.warning(f"處理 API 回應時出錯: {e}")
                
                # 移到下個月
                if current_date.month == 12:
                    current_date = current_date.replace(year=current_date.year + 1, month=1)
                else:
                    current_date = current_date.replace(month=current_date.month + 1)
            
            logger.info(f"成功抓取 {len(data_list)} 筆資料")
            
        except Exception as e:
            logger.error(f"抓取資料時發生錯誤: {e}")
        
        return data_list
    
    def _get_stock_name_from_web(self, stock_id: str) -> Optional[str]:
        """
        從網路取得股票名稱
        
        Args:
            stock_id: 股票代號
            
        Returns:
            股票名稱，若取得失敗則返回 None
        """
        logger.info(f"正在從網路查詢股票 {stock_id} 的名稱")
        
        try:
            # 使用證交所 API 取得股票基本資料
            url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
            params = {
                'response': 'json',
                'date': datetime.now().strftime('%Y%m01'),
                'stockNo': stock_id
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                json_data = response.json()
                if json_data.get('stat') == 'OK' and 'title' in json_data:
                    # title 格式: "XXX年XX月 XXXX 各日成交資訊"
                    title = json_data['title']
                    # 提取股票名稱（在股票代號後面）
                    stock_name = title.split(stock_id)[-1].strip().split()[0] if stock_id in title else None
                    if stock_name:
                        logger.info(f"查詢到股票名稱: {stock_name}")
                        return stock_name
        
        except Exception as e:
            logger.error(f"查詢股票名稱時發生錯誤: {e}")
        
        logger.warning(f"無法取得股票 {stock_id} 的名稱")
        return f"股票{stock_id}"  # 返回預設名稱
    
    def add_temporary_closure(self, date: str) -> bool:
        """
        添加臨時休市日期 (e.g. 颱風、天然災害)
        
        Args:
            date: 日期 (YYYY-MM-DD)
            
        Returns:
            是否添加成功
        """
        if not self._is_valid_date(date):
            logger.warning(f"無效的日期格式: {date}")
            return False
        
        try:
            with open(self.HOLIDAYS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            temporary_closures = data.get('temporary_closures', [])
            
            # 檢查是否已存在
            if date in temporary_closures:
                logger.warning(f"日期 {date} 已在臨時休市清單中")
                return False
            
            # 添加新的臨時休市日期
            temporary_closures.append(date)
            data['temporary_closures'] = temporary_closures
            data['last_updated'] = datetime.now().strftime('%Y-%m-%d')
            
            with open(self.HOLIDAYS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 清除緩存
            self._holidays_cache = None
            
            logger.info(f"已添加臨時休市日期: {date}")
            return True
        except Exception as e:
            logger.error(f"添加臨時休市日期時出錯: {e}")
            return False
    
    def remove_temporary_closure(self, date: str) -> bool:
        """
        移除臨時休市日期
        
        Args:
            date: 日期 (YYYY-MM-DD)
            
        Returns:
            是否移除成功
        """
        if not self._is_valid_date(date):
            logger.warning(f"無效的日期格式: {date}")
            return False
        
        try:
            with open(self.HOLIDAYS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            temporary_closures = data.get('temporary_closures', [])
            
            # 尋找並移除
            if date not in temporary_closures:
                logger.warning(f"未找到臨時休市日期: {date}")
                return False
            
            temporary_closures.remove(date)
            data['temporary_closures'] = temporary_closures
            data['last_updated'] = datetime.now().strftime('%Y-%m-%d')
            
            with open(self.HOLIDAYS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 清除緩存
            self._holidays_cache = None
            
            logger.info(f"已移除臨時休市日期: {date}")
            return True
        except Exception as e:
            logger.error(f"移除臨時休市日期時出錯: {e}")
            return False
    
    def get_temporary_closures(self) -> List[str]:
        """
        取得所有臨時休市日期
        
        Returns:
            臨時休市日期清單
        """
        try:
            if os.path.exists(self.HOLIDAYS_FILE):
                with open(self.HOLIDAYS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('temporary_closures', [])
        except Exception as e:
            logger.error(f"取得臨時休市日期時出錯: {e}")
        
        return []
    
    def update_holidays(self, year: int = None, add_holidays: List[str] = None, remove_holidays: List[str] = None) -> bool:
        """
        更新假日資料（從線上來源或手動添加）
        
        Args:
            year: 要更新的年份（若為 None，則更新目前年份和下一年份）
            add_holidays: 要添加的假日日期列表 (YYYY-MM-DD)
            remove_holidays: 要移除的假日日期列表 (YYYY-MM-DD)
            
        Returns:
            是否更新成功
        """
        try:
            holidays = self._load_holidays()
            
            # 添加假日
            if add_holidays:
                for date_str in add_holidays:
                    if self._is_valid_date(date_str):
                        holidays.add(date_str)
                        logger.info(f"添加假日: {date_str}")
                    else:
                        logger.warning(f"無效的日期格式: {date_str}")
            
            # 移除假日
            if remove_holidays:
                for date_str in remove_holidays:
                    if date_str in holidays:
                        holidays.discard(date_str)
                        logger.info(f"移除假日: {date_str}")
            
            # 清除緩存並保存
            self._holidays_cache = holidays
            success = self._save_holidays(holidays)
            
            if success:
                logger.info("假日資料已更新")
            
            return success
        except Exception as e:
            logger.error(f"更新假日資料時出錯: {e}")
            return False
    
    def get_holidays(self) -> Set[str]:
        """
        取得所有假日資料
        
        Returns:
            假日日期集合
        """
        return self._load_holidays()
    
    def _is_valid_date(self, date_str: str) -> bool:
        """
        驗證日期格式是否正確
        
        Args:
            date_str: 日期字串 (YYYY-MM-DD)
            
        Returns:
            是否為有效日期
        """
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False
    
    def get_stock_name(self, stock_id: str) -> Optional[str]:
        """
        取得股票名稱
        
        Args:
            stock_id: 股票代號
            
        Returns:
            股票名稱，若股票代號無效則返回 None
        """
        if not self._validate_stock_id(stock_id):
            logger.error(f"無效的股票代號: {stock_id}")
            return None
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT stock_name FROM stock_info WHERE stock_id = ?", (stock_id,))
        result = cursor.fetchone()
        
        if result:
            return result[0]
        
        # 資料庫中沒有，從網路取得
        stock_name = self._get_stock_name_from_web(stock_id)
        if stock_name:
            # 儲存到資料庫
            cursor.execute(
                "INSERT OR REPLACE INTO stock_info (stock_id, stock_name) VALUES (?, ?)",
                (stock_id, stock_name)
            )
            self.conn.commit()
        
        return stock_name
    
    def get_stock_data(self, stock_id: str, date: str) -> Optional[Dict]:
        """
        取得指定日期的股票資料
        
        Args:
            stock_id: 股票代號
            date: 日期 (YYYY-MM-DD)
            
        Returns:
            包含股票資料的字典，若無資料則返回 None
            {
                'stock_name': str,
                'date': str,
                'open_price': float,
                'close_price': float,
                'change_rate': float
            }
        """
        if not self._validate_stock_id(stock_id):
            logger.error(f"無效的股票代號: {stock_id}")
            return None
        
        # 檢查是否為股市休市日期
        if self._is_market_closed(date):
            logger.warning(f"{date} 是股市休市日期，無法獲取交易資料")
            return None
        
        # 先檢查是否為休市日期，避免不必要的網路請求
        if self._is_market_closed(date):
            logger.debug(f"日期 {date} 為股市休市日，無法取得股票資料")
            return None
        
        # 檢查資料庫中是否已有資料
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT open_price, close_price, volume, change_rate FROM stock_daily WHERE stock_id = ? AND date = ?",
            (stock_id, date)
        )
        result = cursor.fetchone()
        
        if not result:
            # 資料庫中沒有，先嘗試找附近交易日的資料
            logger.info(f"資料庫中沒有股票 {stock_id} 在 {date} 的資料，嘗試找附近的交易日...")
            current_date = datetime.strptime(date, "%Y-%m-%d")
            
            # 往前後各找最多 5 個交易日
            for offset in range(1, 6):
                # 往前找
                prev_date = (current_date - timedelta(days=offset)).strftime("%Y-%m-%d")
                if not self._is_market_closed(prev_date):
                    cursor.execute(
                        "SELECT open_price, close_price, volume, change_rate FROM stock_daily WHERE stock_id = ? AND date = ?",
                        (stock_id, prev_date)
                    )
                    result = cursor.fetchone()
                    if result:
                        logger.info(f"找到股票 {stock_id} 最近的資料在 {prev_date}")
                        date = prev_date
                        break
                
                # 往後找
                next_date = (current_date + timedelta(days=offset)).strftime("%Y-%m-%d")
                if not self._is_market_closed(next_date):
                    cursor.execute(
                        "SELECT open_price, close_price, volume, change_rate FROM stock_daily WHERE stock_id = ? AND date = ?",
                        (stock_id, next_date)
                    )
                    result = cursor.fetchone()
                    if result:
                        logger.info(f"找到股票 {stock_id} 最近的資料在 {next_date}")
                        date = next_date
                        break
        
        if result:
            stock_name = self.get_stock_name(stock_id)
            return {
                'stock_name': stock_name,
                'date': date,
                'open_price': result[0],
                'close_price': result[1],
                'volume': result[2],
                'change_rate': result[3]
            }
        
        logger.warning(f"找不到股票 {stock_id} 在 {date} 附近的資料")
        return None
    
    def _get_trading_day_in_range(self, start: datetime, end: datetime, direction: str = 'backward') -> datetime:
        """
        在指定範圍內找最接近的交易日
        
        Args:
            start: 搜尋起點
            end: 搜尋終點
            direction: 搜尋方向 ('backward'=從後往前, 'forward'=從前往後)
            
        Returns:
            找到的交易日，若無找到則返回 None
        """
        if direction == 'backward':
            check_date = start
            while check_date >= end:
                date_str = check_date.strftime("%Y-%m-%d")
                if not self._is_market_closed(date_str):
                    logger.debug(f"找到最後交易日: {date_str}")
                    return check_date
                check_date -= timedelta(days=1)
        else:  # forward
            check_date = start
            while check_date <= end:
                date_str = check_date.strftime("%Y-%m-%d")
                if not self._is_market_closed(date_str):
                    logger.debug(f"找到最早交易日: {date_str}")
                    return check_date
                check_date += timedelta(days=1)
        return None
    
    def _ensure_stock_data(self, stock_id: str):
        """
        確保資料庫中有該股票近期的資料
        
        Args:
            stock_id: 股票代號
        """
        # 計算需要的日期範圍，確保end_date是交易日
        end_date = datetime.now()
        start_date = end_date - timedelta(days=config.BACKTEST_DAYS)
        
        # 調整為實際的交易日
        # 從今天開始往前找最後的交易日（往前最多找7天）
        last_trading_day = self._get_trading_day_in_range(end_date, end_date - timedelta(days=7), direction='backward')
        if not last_trading_day:
            logger.warning(f"在過去7天內未找到交易日，無法補充資料")
            return
        
        # 從開始日期往前找最前的交易日
        first_trading_day = self._get_trading_day_in_range(start_date, start_date - timedelta(days=7), direction='backward')
        if not first_trading_day:
            first_trading_day = start_date
        
        # 檢查資料庫中已有的資料範圍
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT MIN(date), MAX(date) FROM stock_daily WHERE stock_id = ?",
            (stock_id,)
        )
        db_result = cursor.fetchone()
        
        if db_result[0] is None:
            # 完全沒有資料，需要從first_trading_day開始抓取到last_trading_day
            fetch_start = first_trading_day.strftime("%Y-%m-%d")
            fetch_end = last_trading_day.strftime("%Y-%m-%d")
            logger.info(f"資料庫中沒有股票 {stock_id} 的資料，準備從 {fetch_start} 到 {fetch_end} 抓取")
            data_list = self._fetch_stock_data_from_web(stock_id, fetch_start, fetch_end)
            if data_list:
                self._save_stock_data_to_db(stock_id, data_list)
        else:
            # 已有部分資料，檢查是否需要補充
            db_start = datetime.strptime(db_result[0], "%Y-%m-%d")
            db_end = datetime.strptime(db_result[1], "%Y-%m-%d")
            
            # 檢查是否需要補充前期資料
            if db_start > first_trading_day:
                fetch_start = first_trading_day.strftime("%Y-%m-%d")
                fetch_end = (db_start - timedelta(days=1)).strftime("%Y-%m-%d")
                logger.info(f"需要補充股票 {stock_id} 前期資料 ({fetch_start} ~ {fetch_end})")
                data_list = self._fetch_stock_data_from_web(stock_id, fetch_start, fetch_end)
                if data_list:
                    self._save_stock_data_to_db(stock_id, data_list)
            
            # 檢查是否需要補充後期資料
            # 只有當數據庫最新日期距離上次交易日超過2天時才補充（避免API延遲導致重複抓取）
            days_behind = (last_trading_day - db_end).days
            if days_behind > 2:
                fetch_start = (db_end + timedelta(days=1)).strftime("%Y-%m-%d")
                fetch_end = last_trading_day.strftime("%Y-%m-%d")
                
                # 檢查日期範圍是否有效
                if fetch_start <= fetch_end:
                    logger.info(f"需要補充股票 {stock_id} 後期資料 ({fetch_start} ~ {fetch_end})，落後 {days_behind} 天")
                    data_list = self._fetch_stock_data_from_web(stock_id, fetch_start, fetch_end)
                    if data_list:
                        self._save_stock_data_to_db(stock_id, data_list)
                    else:
                        logger.warning(f"股票 {stock_id} 在 {fetch_start} ~ {fetch_end} 期間無交易數據")
                else:
                    logger.warning(f"後期資料補充的日期範圍異常 ({fetch_start} ~ {fetch_end})，跳過補充")
            elif days_behind > 0:
                logger.debug(f"股票 {stock_id} 數據僅落後 {days_behind} 天，跳過補充（可能是API延遲）")
            
            # 資料已經完全涵蓋所需範圍
            if db_start <= first_trading_day and db_end >= last_trading_day:
                logger.info(f"股票 {stock_id} 的資料已完整涵蓋所需範圍 ({db_start.strftime('%Y-%m-%d')} ~ {db_end.strftime('%Y-%m-%d')})")
    
    def _save_stock_data_to_db(self, stock_id: str, data_list: List[Dict]):
        """
        將股票資料儲存到資料庫
        
        Args:
            stock_id: 股票代號
            data_list: 股票資料列表
        """
        cursor = self.conn.cursor()
        logger.info(f"正在儲存 {len(data_list)} 筆股票 {stock_id} 的資料到資料庫...")
        for data in data_list:
            cursor.execute('''
                INSERT OR REPLACE INTO stock_daily 
                (stock_id, date, open_price, close_price, high_price, low_price, volume, change_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                stock_id,
                data['date'],
                data['open_price'],
                data['close_price'],
                data['high_price'],
                data['low_price'],
                data['volume'],
                data['change_rate']
            ))
        self.conn.commit()
        logger.info("資料儲存完成")
    
    def get_chart_filename(self, stock_id: str) -> str:
        """
        取得圖表檔案名稱
        
        Args:
            stock_id: 股票代號
            
        Returns:
            圖表檔案名稱
        """
        return config.CHART_FILENAME_TEMPLATE.format(stock_id=stock_id)
    
    def get_date_range_data(self, stock_id: str, start_date: str, end_date: str) -> List[Dict]:
        """
        取得指定日期範圍的股票資料
        
        Args:
            stock_id: 股票代號
            start_date: 開始日期 (YYYY-MM-DD)
            end_date: 結束日期 (YYYY-MM-DD)
            
        Returns:
            股票資料列表
        """
        if not self._validate_stock_id(stock_id):
            logger.error(f"無效的股票代號: {stock_id}")
            return []
        
        # 確保資料庫中有資料
        self._ensure_stock_data(stock_id)
        
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT date, open_price, close_price, high_price, low_price, volume, change_rate
            FROM stock_daily
            WHERE stock_id = ? AND date >= ? AND date <= ?
            ORDER BY date
        ''', (stock_id, start_date, end_date))
        
        results = cursor.fetchall()
        stock_name = self.get_stock_name(stock_id)
        
        data_list = []
        for row in results:
            data_list.append({
                'stock_name': stock_name,
                'date': row[0],
                'open_price': row[1],
                'close_price': row[2],
                'high_price': row[3],
                'low_price': row[4],
                'volume': row[5],
                'change_rate': row[6]
            })
        
        return data_list
    
    def plot_stock_chart(self, stock_id: str, start_date: str = None, end_date: str = None, output_path: str = None):
        """
        繪製個股歷史走勢圖（含成交量）
        
        Args:
            stock_id: 股票代號
            start_date: 開始日期 (YYYY-MM-DD)，若為 None 則使用資料庫中最早的日期
            end_date: 結束日期 (YYYY-MM-DD)，若為 None 則使用資料庫中最晚的日期
            output_path: 輸出檔案路徑，若為 None 則預設為 'stock_{stock_id}_chart.html'
        
        Returns:
            輸出檔案路徑
        """
        if not self._validate_stock_id(stock_id):
            logger.error(f"無效的股票代號: {stock_id}")
            return None
        
        # 取得股票名稱
        stock_name = self.get_stock_name(stock_id)
        if not stock_name:
            logger.error(f"找不到股票 {stock_id} 的資料")
            return None
        
        # 查詢資料
        cursor = self.conn.cursor()
        
        if start_date and end_date:
            cursor.execute(
                "SELECT date, open_price, high_price, low_price, close_price, volume, change_rate "
                "FROM stock_daily WHERE stock_id = ? AND date >= ? AND date <= ? ORDER BY date",
                (stock_id, start_date, end_date)
            )
        else:
            cursor.execute(
                "SELECT date, open_price, high_price, low_price, close_price, volume, change_rate "
                "FROM stock_daily WHERE stock_id = ? ORDER BY date",
                (stock_id,)
            )
        
        rows = cursor.fetchall()
        
        if not rows:
            logger.warning(f"沒有股票 {stock_id} 的歷史資料")
            return None
        
        # 解析資料
        dates = [row[0] for row in rows]
        open_prices = [row[1] for row in rows]
        high_prices = [row[2] for row in rows]
        low_prices = [row[3] for row in rows]
        close_prices = [row[4] for row in rows]
        volumes = [row[5] for row in rows]
        change_rates = [row[6] for row in rows]
        
        # 建立圖表（含雙軸）
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            row_heights=[0.7, 0.3],
            specs=[
                [{"secondary_y": False}],
                [{"secondary_y": False}]
            ]
        )
        
        # 添加 K 線圖到第一個圖表
        fig.add_trace(
            go.Candlestick(
                x=dates,
                open=open_prices,
                high=high_prices,
                low=low_prices,
                close=close_prices,
                name='K線'
            ),
            row=1, col=1
        )
        
        # 添加成交量柱狀圖到第二個圖表
        colors = ['red' if close >= open_val else 'green' 
                  for close, open_val in zip(close_prices, open_prices)]
        
        fig.add_trace(
            go.Bar(
                x=dates,
                y=volumes,
                name='成交量',
                marker=dict(color=colors, opacity=0.7),
                showlegend=True
            ),
            row=2, col=1
        )
        
        # 更新版面配置
        fig.update_layout(
            title=f'{stock_name}({stock_id}) 歷史走勢圖 - 含成交量',
            height=800,
            template='plotly_white',
            hovermode='x unified'
        )
        
        # 更新第一個 Y 軸（價格）
        fig.update_yaxes(title_text="價格（元）", row=1, col=1)
        
        # 更新第二個 Y 軸（成交量）
        fig.update_yaxes(title_text="成交量（股）", row=2, col=1)
        
        # 更新 X 軸
        fig.update_xaxes(title_text="日期", row=2, col=1)
        
        # 輸出檔案
        if output_path is None:
            os.makedirs(config.CHART_PATH, exist_ok=True)
            chart_filename = self.get_chart_filename(stock_id)
            output_path = os.path.join(config.CHART_PATH, chart_filename)
        else:
            # 確保目錄存在
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
        
        fig.write_html(output_path)
        logger.info(f"走勢圖已儲存至: {output_path}")
        
        return output_path
    
    def get_database_summary(self) -> List[Dict]:
        """
        取得資料庫中所有股票的概覽資訊
        
        Returns:
            股票資訊列表 [{'stock_id': str, 'stock_name': str, 'min_date': str, 'max_date': str, 'data_count': int}, ...]
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                si.stock_id,
                si.stock_name,
                MIN(sd.date) as min_date,
                MAX(sd.date) as max_date,
                COUNT(*) as data_count
            FROM stock_info si
            LEFT JOIN stock_daily sd ON si.stock_id = sd.stock_id
            GROUP BY si.stock_id, si.stock_name
            HAVING data_count > 0
            ORDER BY si.stock_id
        """)
        
        rows = cursor.fetchall()
        
        summary = []
        for row in rows:
            summary.append({
                'stock_id': row[0],
                'stock_name': row[1],
                'min_date': row[2],
                'max_date': row[3],
                'data_count': row[4]
            })
        
        logger.info(f"資料庫中共有 {len(summary)} 支股票的資料")
        return summary
    
    def close(self):
        """關閉資料庫連接"""
        if self.conn:
            self.conn.close()
            logger.info("資料庫連接已關閉")


if __name__ == "__main__":
    import argparse
    
    # 設定命令行參數
    parser = argparse.ArgumentParser(
        description="台股資料庫命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例：
  # 查詢數據庫概覽
  python database.py summary
  
  # 查詢特定股票的資料
  python database.py query --stock 2330
  python database.py query --stock 0050 --start 2025-09-01 --end 2025-09-30
  
  # 刪除特定股票的資料
  python database.py delete --stock 2330
  
  # 刪除特定日期範圍的資料
  python database.py delete --stock 0050 --start 2025-09-01 --end 2025-09-30
  
  # 刪除整個資料庫
  python database.py delete --all
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='命令類型')
    
    # 查詢命令
    query_parser = subparsers.add_parser('query', help='查詢股票資料')
    query_parser.add_argument('--stock', type=str, help='股票代號（如：2330）')
    query_parser.add_argument('--start', type=str, help='開始日期（YYYY-MM-DD）')
    query_parser.add_argument('--end', type=str, help='結束日期（YYYY-MM-DD）')
    
    # 刪除命令
    delete_parser = subparsers.add_parser('delete', help='刪除股票資料')
    delete_parser.add_argument('--stock', type=str, help='股票代號（如：2330）')
    delete_parser.add_argument('--start', type=str, help='開始日期（YYYY-MM-DD）')
    delete_parser.add_argument('--end', type=str, help='結束日期（YYYY-MM-DD）')
    delete_parser.add_argument('--all', action='store_true', help='刪除整個資料庫')
    
    # 概覽命令
    summary_parser = subparsers.add_parser('summary', help='查詢資料庫概覽')
    
    args = parser.parse_args()
    
    # 初始化資料庫
    db = StockDatabase()
    
    try:
        if args.command == 'summary':
            # 顯示資料庫概覽
            summary = db.get_database_summary()
            if summary:
                print("\n" + "=" * 80)
                print("資料庫概覽")
                print("=" * 80)
                print(f"{'股票代號':<10} {'股票名稱':<20} {'最早日期':<15} {'最晚日期':<15} {'資料筆數':<10}")
                print("-" * 80)
                for item in summary:
                    print(f"{item['stock_id']:<10} {item['stock_name']:<20} {item['min_date']:<15} {item['max_date']:<15} {item['data_count']:<10}")
                print("=" * 80 + "\n")
            else:
                print("資料庫中沒有任何股票資料")
        
        elif args.command == 'query':
            if not args.stock:
                print("✗ 錯誤：查詢時必須指定 --stock 股票代號")
            else:
                cursor = db.conn.cursor()
                
                if args.start and args.end:
                    # 查詢日期範圍內的資料
                    cursor.execute("""
                        SELECT date, open_price, close_price, high_price, low_price, volume, change_rate
                        FROM stock_daily
                        WHERE stock_id = ? AND date >= ? AND date <= ?
                        ORDER BY date
                    """, (args.stock, args.start, args.end))
                else:
                    # 查詢所有資料
                    cursor.execute("""
                        SELECT date, open_price, close_price, high_price, low_price, volume, change_rate
                        FROM stock_daily
                        WHERE stock_id = ?
                        ORDER BY date
                    """, (args.stock,))
                
                rows = cursor.fetchall()
                
                if rows:
                    stock_name = db.get_stock_name(args.stock)
                    date_range = ""
                    if args.start and args.end:
                        date_range = f"({args.start} ~ {args.end})"
                    
                    print("\n" + "=" * 120)
                    print(f"股票 {args.stock} ({stock_name}) {date_range}")
                    print("=" * 120)
                    print(f"{'日期':<15} {'開盤':<10} {'收盤':<10} {'最高':<10} {'最低':<10} {'成交量':<15} {'漲跌幅':<10}")
                    print("-" * 120)
                    
                    for row in rows:
                        date, open_p, close_p, high_p, low_p, volume, change_rate = row
                        print(f"{date:<15} {open_p:<10.2f} {close_p:<10.2f} {high_p:<10.2f} {low_p:<10.2f} {volume:>13,} {change_rate:>8.2f}%")
                    
                    print("=" * 120 + "\n")
                else:
                    print(f"\n✗ 找不到股票 {args.stock} 的資料\n")
        
        elif args.command == 'delete':
            cursor = db.conn.cursor()
            
            if args.all:
                # 刪除整個資料庫
                confirm = input("⚠ 確認要刪除整個資料庫嗎？(yes/no): ")
                if confirm.lower() == 'yes':
                    cursor.execute("DELETE FROM stock_daily")
                    cursor.execute("DELETE FROM stock_info")
                    db.conn.commit()
                    print("✓ 資料庫已清空")
                else:
                    print("✗ 已取消操作")
            
            elif args.stock:
                if args.start and args.end:
                    # 刪除特定日期範圍的資料
                    confirm = input(f"⚠ 確認要刪除 {args.stock} 的 {args.start} ~ {args.end} 資料嗎？(yes/no): ")
                    if confirm.lower() == 'yes':
                        cursor.execute("""
                            DELETE FROM stock_daily
                            WHERE stock_id = ? AND date >= ? AND date <= ?
                        """, (args.stock, args.start, args.end))
                        db.conn.commit()
                        deleted_count = cursor.rowcount
                        print(f"✓ 已刪除 {deleted_count} 筆資料")
                    else:
                        print("✗ 已取消操作")
                else:
                    # 刪除所有該股票的資料
                    confirm = input(f"⚠ 確認要刪除 {args.stock} 的所有資料嗎？(yes/no): ")
                    if confirm.lower() == 'yes':
                        cursor.execute("DELETE FROM stock_daily WHERE stock_id = ?", (args.stock,))
                        cursor.execute("DELETE FROM stock_info WHERE stock_id = ?", (args.stock,))
                        db.conn.commit()
                        deleted_count = cursor.rowcount
                        print(f"✓ 已刪除 {deleted_count} 筆資料")
                    else:
                        print("✗ 已取消操作")
            else:
                print("✗ 錯誤：刪除時必須指定 --stock 或 --all")
        
        else:
            parser.print_help()
    
    finally:
        db.close()
