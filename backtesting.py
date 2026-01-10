"""
回測引擎 - 執行策略回測並生成報告
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List
from database import StockDatabase
from strategy import Strategy
import config

logger = logging.getLogger(__name__)


class BacktestEngine:
    """回測引擎"""
    
    def __init__(self, db: StockDatabase, strategy: Strategy, initial_capital: float = None, strategy_description: str = None):
        """
        初始化回測引擎
        
        Args:
            db: 資料庫實例
            strategy: 策略實例
            initial_capital: 初始資金
        """
        if initial_capital is None:
            initial_capital = config.INITIAL_CAPITAL
        self.db = db
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.strategy_description = strategy_description
        self.cash = initial_capital  # 可用資金
        self.positions = {}  # 持倉 {stock_id: {'quantity': int, 'cost': float}}
        self.daily_values = []  # 每日淨值記錄
        self.transactions = []  # 交易記錄
        
        logger.info(f"初始化回測引擎 - 初始資金: {initial_capital:,.0f} 元")
    
    def _calculate_fee(self, amount: float, is_buy: bool) -> int:
        """
        計算交易手續費
        
        Args:
            amount: 交易金額
            is_buy: 是否為買入
            
        Returns:
            手續費（元）
        """
        if is_buy:
            fee = round(amount * config.BUY_FEE_RATE)
        else:
            # 賣出需要加上證交稅
            fee = round(amount * config.SELL_FEE_RATE) + round(amount * config.SELL_TAX_RATE)
        
        # 手續費低消
        return max(fee, config.MIN_FEE)
    
    def _execute_buy(self, date: str, stock_id: str, price: float, amount: float = None, reason: str = None) -> bool:
        """
        執行買入操作
        
        Args:
            date: 交易日期
            stock_id: 股票代號
            price: 買入價格
            amount: 買入金額（若為 None，則使用最低交易金額）
            
        Returns:
            是否成功執行
        """
        # 檢查價格是否有效
        if price is None or price <= 0:
            logger.warning(f"{date}: 股票 {stock_id} 價格無效: {price}")
            return False
        
        # 決定買入金額
        if amount is None:
            amount = config.MIN_TRANSACTION
        
        # 檢查是否達到最低交易金額
        if amount < config.MIN_TRANSACTION:
            logger.warning(f"{date}: 買入金額 {amount:.0f} 元低於最低交易金額 {config.MIN_TRANSACTION} 元")
            return False
        
        # 計算手續費
        fee = self._calculate_fee(amount, is_buy=True)
        total_cost = amount + fee
        
        # 檢查資金是否足夠
        if self.cash < total_cost:
            logger.warning(f"{date}: 資金不足，可用: {self.cash:.0f} 元，需要: {total_cost:.0f} 元")
            return False
        
        # 計算買入股數（台股以張為單位，1張=1000股）
        quantity = int(amount / price)
        actual_amount = quantity * price
        actual_fee = self._calculate_fee(actual_amount, is_buy=True)
        actual_total_cost = actual_amount + actual_fee
        
        # 扣除資金
        self.cash -= actual_total_cost
        
        # 更新持倉
        if stock_id in self.positions:
            old_quantity = self.positions[stock_id]['quantity']
            old_cost = self.positions[stock_id]['cost']
            self.positions[stock_id]['quantity'] = old_quantity + quantity
            self.positions[stock_id]['cost'] = old_cost + actual_total_cost
        else:
            self.positions[stock_id] = {
                'quantity': quantity,
                'cost': actual_total_cost
            }
        
        # 更新策略持倉（如果策略有 update_position 方法）
        if hasattr(self.strategy, 'update_position'):
            self.strategy.update_position(stock_id, self.positions[stock_id]['quantity'], date, price)
        
        # 記錄交易
        stock_name = self.db.get_stock_name(stock_id)
        # 計算當前淨值
        current_net_value = self._calculate_total_value(date)
        self.transactions.append({
            'date': date,
            'action': 'buy',
            'stock_id': stock_id,
            'stock_name': stock_name,
            'price': price,
            'quantity': quantity,
            'amount': actual_amount,
            'fee': actual_fee,
            'cash': self.cash,
            'net_value': current_net_value,
            'reason': reason
        })
        
        logger.info(f"{date}: 買入 {stock_name}({stock_id}) {quantity} 股 @ {price:.2f} 元，"
                   f"金額: {actual_amount:.0f} 元，手續費: {actual_fee} 元，剩餘資金: {self.cash:.0f} 元")
        
        return True
    
    def _execute_sell(self, date: str, stock_id: str, price: float, quantity: int = None, reason: str = None) -> bool:
        """
        執行賣出操作
        
        Args:
            date: 交易日期
            stock_id: 股票代號
            price: 賣出價格
            quantity: 賣出股數（若為 None，則全部賣出）
            
        Returns:
            是否成功執行
        """
        # 檢查是否持有該股票
        if stock_id not in self.positions:
            logger.warning(f"{date}: 未持有股票 {stock_id}")
            return False
        
        # 決定賣出股數
        if quantity is None:
            quantity = self.positions[stock_id]['quantity']
        else:
            quantity = min(quantity, self.positions[stock_id]['quantity'])
        
        # 檢查賣出股數是否有效
        if quantity <= 0:
            logger.warning(f"{date}: 股票 {stock_id} 持倉數量為 0，無法賣出")
            return False
        
        # 計算賣出金額
        amount = quantity * price
        
        # 計算手續費和稅
        fee = self._calculate_fee(amount, is_buy=False)
        net_amount = amount - fee
        
        # 增加資金
        self.cash += net_amount
        
        # 更新持倉
        cost_per_share = self.positions[stock_id]['cost'] / self.positions[stock_id]['quantity']
        self.positions[stock_id]['quantity'] -= quantity
        self.positions[stock_id]['cost'] -= cost_per_share * quantity
        
        if self.positions[stock_id]['quantity'] == 0:
            del self.positions[stock_id]
        
        # 記錄交易
        stock_name = self.db.get_stock_name(stock_id)
        profit = net_amount - (cost_per_share * quantity)
        # 計算當前淨值
        current_net_value = self._calculate_total_value(date)
        
        self.transactions.append({
            'date': date,
            'action': 'sell',
            'stock_id': stock_id,
            'stock_name': stock_name,
            'price': price,
            'quantity': quantity,
            'amount': amount,
            'fee': fee,
            'profit': profit,
            'cash': self.cash,
            'net_value': current_net_value,
            'reason': reason
        })
        
        logger.info(f"{date}: 賣出 {stock_name}({stock_id}) {quantity} 股 @ {price:.2f} 元，"
                   f"金額: {amount:.0f} 元，手續費: {fee} 元，獲利: {profit:.0f} 元，剩餘資金: {self.cash:.0f} 元")
        
        return True
    
    def _calculate_total_value(self, date: str) -> float:
        """
        計算當日總資產
        
        Args:
            date: 日期
            
        Returns:
            總資產（元）
        """
        total = self.cash
        
        for stock_id, position in self.positions.items():
            stock_data = self.db.get_stock_data(stock_id, date)
            if stock_data:
                total += position['quantity'] * stock_data['close_price']
        
        return total
    
    def _settle_positions(self, settlement_date: str) -> bool:
        """
        清算所有持倉股票（以指定日期的收盤價變現）
        
        Args:
            settlement_date: 結算日期 (YYYY-MM-DD)
            
        Returns:
            是否成功清算所有持倉
        """
        if not self.positions:
            logger.info(f"{settlement_date}: 無需清算，沒有持倉股票")
            return True
        
        logger.info(f"{settlement_date}: 開始清算持倉股票...")
        
        all_settled = True
        for stock_id, position in list(self.positions.items()):
            stock_data = self.db.get_stock_data(stock_id, settlement_date)
            if stock_data:
                price = stock_data['close_price']
                quantity = position['quantity']
                
                # 計算變現金額
                amount = quantity * price
                fee = self._calculate_fee(amount, is_buy=False)
                net_amount = amount - fee
                
                # 更新現金
                self.cash += net_amount
                
                # 獲取股票名稱
                stock_name = stock_data.get('stock_name', f"股票{stock_id}")
                
                logger.info(f"{settlement_date}: 清算 {stock_name}({stock_id}) {quantity} 股 @ {price:.2f} 元，"
                           f"金額: {amount:.0f} 元，手續費/稅金: {fee} 元，實收: {net_amount:.0f} 元")
                
                # 記錄清算交易
                current_net_value = self.cash  # 清算時淨值就是現金
                self.transactions.append({
                    'date': settlement_date,
                    'action': '清算',
                    'stock_id': stock_id,
                    'stock_name': stock_name,
                    'price': price,
                    'quantity': quantity,
                    'amount': amount,
                    'fee': fee,
                    'profit': net_amount - (quantity * position['cost']),
                    'cash': self.cash,
                    'net_value': current_net_value,
                    'reason': None
                })
                
                # 移除持倉
                del self.positions[stock_id]
            else:
                logger.warning(f"{settlement_date}: 無法取得股票 {stock_id} 的價格，清算失敗")
                all_settled = False
        
        # 添加最終淨值紀錄
        final_total = self.cash
        final_return = ((final_total - self.initial_capital) / self.initial_capital) * 100
        
        self.daily_values.append({
            'date': settlement_date,
            'cash': self.cash,
            'total_value': final_total,
            'return': final_return,
            'is_settlement': True
        })
        
        logger.info(f"{settlement_date}: 清算完成 - 最終現金: {self.cash:,.0f} 元，最終總資產: {final_total:,.0f} 元，"
                   f"總報酬率: {final_return:.2f}%")
        
        return all_settled
    
    def run(self, start_date: str = None, end_date: str = None):
        """
        執行回測
        
        Args:
            start_date: 開始日期 (YYYY-MM-DD)，若為 None 則使用 config.BACKTEST_START_DATE
            end_date: 結束日期 (YYYY-MM-DD)，若為 None 則使用 config.BACKTEST_END_DATE
        """
        # 設定日期範圍
        if end_date is None:
            # 優先使用配置文件中的固定結束日期
            if hasattr(config, 'BACKTEST_END_DATE') and config.BACKTEST_END_DATE:
                end_date = config.BACKTEST_END_DATE
            else:
                # 如果沒有設定結束日期，使用最近的交易日（往前最多找3天內的交易日）
                end_dt = datetime.now()
                for days_back in range(0, 4):  # 最多往前找3天
                    check_dt = end_dt - timedelta(days=days_back)
                    if not self.db._is_market_closed(check_dt.strftime("%Y-%m-%d")):
                        end_date = check_dt.strftime("%Y-%m-%d")
                        break
                if end_date is None:  # 如果找不到交易日，回退到7天前
                    end_dt = datetime.now() - timedelta(days=7)
                    end_date = end_dt.strftime("%Y-%m-%d")
        
        if start_date is None:
            # 優先使用配置文件中的固定開始日期
            if hasattr(config, 'BACKTEST_START_DATE') and config.BACKTEST_START_DATE:
                start_date = config.BACKTEST_START_DATE
            else:
                # 如果沒有設定開始日期，使用結束日期往前推180天
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                start_dt = end_dt - timedelta(days=180)
                start_date = start_dt.strftime("%Y-%m-%d")
        
        logger.info(f"開始回測 - 期間: {start_date} ~ {end_date}")
        
        # 重置狀態
        self.cash = self.initial_capital
        self.positions = {}
        self.daily_values = []
        self.transactions = []
        self.strategy.reset()
        
        # 獲取日期列表（這裡簡化處理，實際應該只取交易日）
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        current_dt = start_dt
        
        while current_dt <= end_dt:
            date = current_dt.strftime("%Y-%m-%d")
            
            # 檢查是否為股市休市日期
            if self.db._is_market_closed(date):
                current_dt += timedelta(days=1)
                continue
            
            # 準備市場資料（這裡需要根據策略需要的股票取得資料）
            # 為了簡化，這裡假設策略會告訴我們需要哪些股票
            market_data = {}
            
            # 獲取策略可能需要的股票資料
            # 從策略實例中取得目標股票（如果有定義）
            target_stocks = []
            if hasattr(self.strategy, 'target_stock'):
                target_stocks = [self.strategy.target_stock]
            elif hasattr(self.strategy, 'target_stocks'):
                target_stocks = self.strategy.target_stocks
            else:
                # 默認為 2330
                target_stocks = ['2330']
            
            for stock_id in target_stocks:
                stock_data = self.db.get_stock_data(stock_id, date)
                if stock_data:
                    market_data[stock_id] = stock_data
            
            # 只在有市場資料時處理（表示是交易日）
            if market_data:
                # 獲取策略信號
                signals = self.strategy.on_data(date, market_data)
                
                # 執行交易
                for signal in signals:
                    action = signal['action']
                    stock_id = signal['stock_id']
                    reason = signal.get('reason')
                    
                    if action == 'buy':
                        price = signal.get('price')
                        amount = signal.get('amount')
                        self._execute_buy(date, stock_id, price, amount, reason=reason)
                    
                    elif action == 'sell':
                        price = signal.get('price')
                        quantity = signal.get('quantity')
                        self._execute_sell(date, stock_id, price, quantity, reason=reason)
                
                # 計算當日總資產
                total_value = self._calculate_total_value(date)
                self.daily_values.append({
                    'date': date,
                    'cash': self.cash,
                    'total_value': total_value,
                    'return': ((total_value - self.initial_capital) / self.initial_capital) * 100
                })
                
                logger.info(f"{date}: 總資產: {total_value:,.0f} 元，報酬率: "
                           f"{((total_value - self.initial_capital) / self.initial_capital) * 100:.2f}%")
            
            # 下一天
            current_dt += timedelta(days=1)
        
        # 回測結束，清算所有持倉股票（以最後一個交易日的價格變現）
        if self.daily_values:
            last_date = self.daily_values[-1]['date']
            self._settle_positions(last_date)
        
        logger.info("回測完成")
    
    def generate_report(self, output_path: str = None):
        """
        生成 HTML 報告
        
        Args:
            output_path: 報告輸出路徑
        """
        if output_path is None:
            output_path = config.REPORT_PATH
        logger.info(f"正在生成報告: {output_path}")
        
        # 計算統計數據
        if not self.daily_values:
            logger.warning("沒有回測數據，無法生成報告")
            return
        
        final_value = self.daily_values[-1]['total_value']
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100
        win_count = sum(1 for t in self.transactions if t['action'] == 'sell' and t.get('profit', 0) > 0)
        lose_count = sum(1 for t in self.transactions if t['action'] == 'sell' and t.get('profit', 0) <= 0)
        total_trades = win_count + lose_count
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
        
        # 生成 HTML
        html = f"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>回測報告</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            font-family: "Microsoft JhengHei", Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .stat-card.positive {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }}
        .stat-card.negative {{
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }}
        .stat-label {{
            font-size: 14px;
            opacity: 0.9;
        }}
        .stat-value {{
            font-size: 28px;
            font-weight: bold;
            margin-top: 5px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #4CAF50;
            color: white;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .buy {{
            color: #d32f2f;
        }}
        .sell {{
            color: #388e3c;
        }}
        .strategy-description {{
            background-color: #f0f4ff;
            border-left: 4px solid #2196F3;
            padding: 20px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        .strategy-description h3 {{
            margin-top: 0;
            color: #2196F3;
        }}
        .strategy-description ul {{
            margin: 10px 0;
        }}
        .strategy-description li {{
            margin: 5px 0;
        }}
        #chart {{
            margin-top: 30px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 台股回測報告</h1>
        
        <div class="strategy-description">
            {self.strategy_description or '未提供策略說明'}
        </div>
        
        <h2>回測概要</h2>
        <div class="stats">
            <div class="stat-card">
                <div class="stat-label">初始資金</div>
                <div class="stat-value">{self.initial_capital:,.0f} 元</div>
            </div>
            <div class="stat-card {'positive' if total_return >= 0 else 'negative'}">
                <div class="stat-label">最終資產</div>
                <div class="stat-value">{final_value:,.0f} 元</div>
            </div>
            <div class="stat-card {'positive' if total_return >= 0 else 'negative'}">
                <div class="stat-label">總報酬率</div>
                <div class="stat-value">{total_return:+.2f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">交易次數</div>
                <div class="stat-value">{len(self.transactions)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">勝率</div>
                <div class="stat-value">{win_rate:.1f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">勝/敗</div>
                <div class="stat-value">{win_count}/{lose_count}</div>
            </div>
        </div>
        
        <h2>淨值曲線</h2>
        <div id="chart"></div>
        
        <h2>交易明細</h2>
        <table>
            <thead>
                <tr>
                    <th>日期</th>
                    <th>動作</th>
                    <th>股票</th>
                    <th>價格</th>
                    <th>股數</th>
                    <th>金額</th>
                    <th>手續費</th>
                    <th>獲利</th>
                    <th>原因</th>
                    <th>剩餘資金</th>
                    <th>淨值</th>
                </tr>
            </thead>
            <tbody>
        """
        
        for t in self.transactions:
            action_class = t['action']
            action_text = '買入' if t['action'] == 'buy' else '賣出'
            profit_text = f"{t.get('profit', 0):+,.0f}" if t['action'] == 'sell' else '-'
            reason_text = t.get('reason', '-') or '-'
            
            html += f"""
                <tr>
                    <td>{t['date']}</td>
                    <td class="{action_class}">{action_text}</td>
                    <td>{t['stock_name']}({t['stock_id']})</td>
                    <td>{t['price']:.2f}</td>
                    <td>{t['quantity']}</td>
                    <td>{t['amount']:,.0f}</td>
                    <td>{t['fee']}</td>
                    <td>{profit_text}</td>
                    <td>{reason_text}</td>
                    <td>{t['cash']:,.0f}</td>
                    <td>{t.get('net_value', 0):,.0f}</td>
                </tr>
            """
        
        html += """
            </tbody>
        </table>
    </div>
    
    <script>
        // 繪製淨值曲線
        var dates = [
        """
        
        for dv in self.daily_values:
            html += f"'{dv['date']}', "
        
        html += """
        ];
        var values = [
        """
        
        for dv in self.daily_values:
            html += f"{dv['total_value']}, "
        
        html += f"""
        ];
        
        var trace = {{
            x: dates,
            y: values,
            type: 'scatter',
            mode: 'lines+markers',
            name: '總資產',
            line: {{
                color: '#4CAF50',
                width: 2
            }},
            marker: {{
                size: 6
            }}
        }};
        
        var baseline = {{
            x: dates,
            y: Array(dates.length).fill({self.initial_capital}),
            type: 'scatter',
            mode: 'lines',
            name: '初始資金',
            line: {{
                color: '#ff9800',
                width: 2,
                dash: 'dash'
            }}
        }};
        
        var layout = {{
            title: '資產變化',
            xaxis: {{
                title: '日期',
                tickangle: -45
            }},
            yaxis: {{
                title: '資產（元）',
                tickformat: ','
            }},
            hovermode: 'x unified'
        }};
        
        Plotly.newPlot('chart', [trace, baseline], layout);
    </script>
</body>
</html>
        """
        
        # 寫入檔案
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"報告已生成: {output_path}")
