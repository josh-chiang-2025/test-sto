"""
資料庫視覺化工具 - 提供互動式介面查看資料庫狀態
"""

import logging
from database import StockDatabase
from config import CHART_PATH
import os

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def generate_database_view(output_path: str = None):
    """
    生成資料庫視覺化頁面
    
    Args:
        output_path: 輸出檔案路徑，若為 None 則預設為 CHART_PATH/database_view.html
    
    Returns:
        輸出檔案路徑
    """
    if output_path is None:
        output_path = os.path.join(CHART_PATH, "database_overview.html")
    
    logger.info("開始生成資料庫視覺化頁面")
    
    # 初始化資料庫
    db = StockDatabase()
    
    # 取得資料庫概覽
    summary = db.get_database_summary()
    
    if not summary:
        logger.warning("資料庫中沒有任何股票資料")
        db.close()
        return None
    
    # 建立個股圖表的子資料夾
    charts_dir = os.path.join(CHART_PATH, "stock_charts")
    os.makedirs(charts_dir, exist_ok=True)
    
    # 生成走勢圖
    chart_files = []
    for stock_info in summary:
        stock_id = stock_info['stock_id']
        chart_filename = db.get_chart_filename(stock_id)
        chart_path = os.path.join(charts_dir, chart_filename)
        
        db.plot_stock_chart(stock_id, output_path=chart_path)
        chart_files.append(f"stock_charts/{chart_filename}")  # 相對路徑用於 HTML
    
    # 生成 HTML
    html = f"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>資料庫視覺化 - 台股回測工具</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: "Microsoft JhengHei", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1600px;
            margin: 0 auto;
        }}
        
        .header {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            margin-bottom: 20px;
            text-align: center;
        }}
        
        .header h1 {{
            color: #333;
            margin-bottom: 5px;
            font-size: 1.8em;
        }}
        
        .header p {{
            color: #666;
            font-size: 0.95em;
        }}
        
        .stats {{
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        
        .stat-card {{
            flex: 1;
            min-width: 150px;
            background: white;
            padding: 15px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            text-align: center;
        }}
        
        .stat-card .number {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }}
        
        .stat-card .label {{
            color: #666;
            font-size: 0.9em;
        }}
        
        .stock-table-container {{
            background: white;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            overflow: hidden;
        }}
        
        .stock-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        .stock-table thead {{
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        
        .stock-table th {{
            padding: 15px;
            text-align: left;
            font-weight: 600;
            font-size: 0.95em;
        }}
        
        .stock-table td {{
            padding: 12px 15px;
            border-bottom: 1px solid #f0f0f0;
        }}
        
        .stock-table tbody tr {{
            transition: background-color 0.2s ease;
        }}
        
        .stock-table tbody tr:hover {{
            background-color: #f8f9ff;
        }}
        
        .stock-id {{
            font-weight: bold;
            color: #667eea;
            font-size: 1.1em;
        }}
        
        .stock-name {{
            color: #333;
            font-weight: 500;
        }}
        
        .date-range {{
            color: #666;
            font-size: 0.9em;
        }}
        
        .data-count {{
            color: #666;
            font-size: 0.9em;
        }}
        
        .view-btn {{
            padding: 8px 16px;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 20px;
            cursor: pointer;
            font-size: 0.9em;
            transition: all 0.3s ease;
        }}
        
        .view-btn:hover {{
            transform: scale(1.05);
            box-shadow: 0 3px 10px rgba(102, 126, 234, 0.4);
        }}
        
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.8);
            animation: fadeIn 0.3s ease;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}
        
        .modal-content {{
            position: relative;
            background-color: white;
            margin: 2% auto;
            padding: 0;
            width: 95%;
            max-width: 1400px;
            border-radius: 15px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            animation: slideIn 0.3s ease;
        }}
        
        @keyframes slideIn {{
            from {{ transform: translateY(-50px); opacity: 0; }}
            to {{ transform: translateY(0); opacity: 1; }}
        }}
        
        .close {{
            position: absolute;
            right: 20px;
            top: 15px;
            color: #aaa;
            font-size: 35px;
            font-weight: bold;
            cursor: pointer;
            z-index: 1001;
            transition: color 0.3s ease;
        }}
        
        .close:hover {{
            color: #000;
        }}
        
        .chart-container {{
            width: 100%;
            height: 85vh;
            overflow: auto;
        }}
        
        .chart-container iframe {{
            width: 100%;
            height: 100%;
            border: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 資料庫視覺化</h1>
            <p>台股回測工具 - 資料庫狀態總覽</p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="number">{len(summary)}</div>
                <div class="label">股票數量</div>
            </div>
            <div class="stat-card">
                <div class="number">{sum(s['data_count'] for s in summary)}</div>
                <div class="label">資料筆數</div>
            </div>
        </div>
        
        <div class="stock-table-container">
            <table class="stock-table">
                <thead>
                    <tr>
                        <th>代碼</th>
                        <th>名稱</th>
                        <th>資料期間</th>
                        <th>筆數</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
"""
    
    for i, stock_info in enumerate(summary):
        html += f"""
                    <tr>
                        <td><span class="stock-id">{stock_info['stock_id']}</span></td>
                        <td><span class="stock-name">{stock_info['stock_name']}</span></td>
                        <td><span class="date-range">{stock_info['min_date']} ~ {stock_info['max_date']}</span></td>
                        <td><span class="data-count">{stock_info['data_count']}</span></td>
                        <td>
                            <button class="view-btn" onclick="showChart('{chart_files[i]}', '{stock_info['stock_id']}', '{stock_info['stock_name']}')">
                                查看走勢
                            </button>
                        </td>
                    </tr>
"""
    
    html += """
                </tbody>
            </table>
        </div>
    </div>
    
    <div id="chartModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal()">&times;</span>
            <div class="chart-container">
                <iframe id="chartFrame" src=""></iframe>
            </div>
        </div>
    </div>
    
    <script>
        function showChart(chartFile, stockId, stockName) {
            const modal = document.getElementById('chartModal');
            const iframe = document.getElementById('chartFrame');
            iframe.src = chartFile;
            modal.style.display = 'block';
            
            // 阻止背景滾動
            document.body.style.overflow = 'hidden';
        }
        
        function closeModal() {
            const modal = document.getElementById('chartModal');
            modal.style.display = 'none';
            
            // 恢復背景滾動
            document.body.style.overflow = 'auto';
        }
        
        // 點擊模態框外部關閉
        window.onclick = function(event) {
            const modal = document.getElementById('chartModal');
            if (event.target == modal) {
                closeModal();
            }
        }
        
        // ESC 鍵關閉
        document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') {
                closeModal();
            }
        });
    </script>
</body>
</html>
"""
    
    # 寫入檔案
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    logger.info(f"視覺化頁面已儲存至: {output_path}")
    
    # 關閉資料庫
    db.close()
    
    return output_path


def main():
    """主函數"""
    logger.info("=" * 80)
    logger.info("資料庫視覺化工具啟動")
    logger.info("=" * 80)
    
    try:
        output_path = generate_database_view()
        
        if output_path:
            logger.info("=" * 80)
            logger.info(f"視覺化頁面已生成: {output_path}")
            logger.info("請用瀏覽器開啟查看")
            logger.info("=" * 80)
        else:
            logger.warning("資料庫中沒有資料，無法生成視覺化頁面")
    
    except Exception as e:
        logger.error(f"執行過程中發生錯誤: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()

