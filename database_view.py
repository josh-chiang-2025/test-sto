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
    
    # 生成走勢圖
    chart_files = []
    for stock_info in summary:
        stock_id = stock_info['stock_id']
        chart_filename = db.get_chart_filename(stock_id)
        chart_path = os.path.join(CHART_PATH, chart_filename)
        
        db.plot_stock_chart(stock_id, output_path=chart_path)
        chart_files.append(chart_filename)  # 相對路徑用於 HTML
    
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
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .header {{
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            color: #333;
            margin-bottom: 10px;
            font-size: 2.5em;
        }}
        
        .header p {{
            color: #666;
            font-size: 1.1em;
        }}
        
        .stats {{
            display: flex;
            gap: 20px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }}
        
        .stat-card {{
            flex: 1;
            min-width: 200px;
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            text-align: center;
        }}
        
        .stat-card .number {{
            font-size: 3em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 10px;
        }}
        
        .stat-card .label {{
            color: #666;
            font-size: 1.1em;
        }}
        
        .stock-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
        }}
        
        .stock-card {{
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            cursor: pointer;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }}
        
        .stock-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 5px;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        }}
        
        .stock-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(0,0,0,0.3);
        }}
        
        .stock-card .stock-id {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }}
        
        .stock-card .stock-name {{
            font-size: 1.5em;
            color: #333;
            margin-bottom: 15px;
        }}
        
        .stock-card .date-range {{
            color: #666;
            font-size: 0.9em;
            margin-bottom: 5px;
        }}
        
        .stock-card .data-count {{
            color: #999;
            font-size: 0.85em;
        }}
        
        .stock-card .view-btn {{
            margin-top: 15px;
            padding: 10px 20px;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 25px;
            cursor: pointer;
            font-size: 1em;
            transition: all 0.3s ease;
        }}
        
        .stock-card .view-btn:hover {{
            transform: scale(1.05);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
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
        
        <div class="stock-grid">
"""
    
    for i, stock_info in enumerate(summary):
        html += f"""
            <div class="stock-card">
                <div class="stock-id">{stock_info['stock_id']}</div>
                <div class="stock-name">{stock_info['stock_name']}</div>
                <div class="date-range">📅 {stock_info['min_date']} ~ {stock_info['max_date']}</div>
                <div class="data-count">📈 {stock_info['data_count']} 筆資料</div>
                <button class="view-btn" onclick="showChart('{chart_files[i]}', '{stock_info['stock_id']}', '{stock_info['stock_name']}')">
                    查看走勢圖
                </button>
            </div>
"""
    
    html += """
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

