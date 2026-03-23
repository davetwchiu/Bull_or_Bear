import requests
import json
import os
from datetime import datetime

# 從 GitHub Secrets 讀取 API Key
API_KEY = os.environ.get('FRED_API_KEY')

def get_fred_data(series_id, limit=1):
    """向 FRED API 獲取數據，自動過濾節假日無效數據('.')"""
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={API_KEY}&file_type=json&sort_order=desc&limit={limit}"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    
    # 過濾出有效的浮點數
    valid_values = [float(obs['value']) for obs in data['observations'] if obs['value'] != '.']
    return valid_values

def main():
    try:
        print("正在獲取市場數據...")
        
        # ==========================================
        # 1. 獲取 S&P 500 及計算 200天線 / 企穩日數
        # ==========================================
        sp500_history = get_fred_data('SP500', limit=600)
        sp500_current = sp500_history[0]
        ma200 = sum(sp500_history[:200]) / 200

        # 自動計算「跌破前連續企穩 200天線日數」
        stable_days = 0
        streak_started = False
        
        # 迴圈由最新嗰日 (index 0) 向過去推算 250 個交易日 (大約 1 年)
        for i in range(250):
            price = sp500_history[i]
            # 計算當時嗰日嘅 200MA
            historical_ma200 = sum(sp500_history[i : i+200]) / 200
            is_above_ma = price > historical_ma200

            if is_above_ma:
                streak_started = True
                stable_days += 1
            else:
                if streak_started:
                    # 如果之前係「企穩(True)」，而家遇到「跌穿(False)」，代表個 streak 完咗
                    break

        # ==========================================
        # 2. 獲取 VIX 恐慌指數
        # ==========================================
        vix = get_fred_data('VIXCLS', limit=10)[0]

        # ==========================================
        # 3. 獲取 High Yield Credit Spread (轉換為 bp)
        # ==========================================
        spread_percent = get_fred_data('BAMLH0A0HYM2', limit=10)[0]
        spread_bp = spread_percent * 100

        # ==========================================
        # 4. 獲取並計算 Richmond Fed SOS (基於 IURSA 數據)
        # ==========================================
        iursa_history = get_fred_data('IURSA', limit=100)
        ma26_list = []
        for i in range(52):
            ma26 = sum(iursa_history[i : i+26]) / 26
            ma26_list.append(ma26)
            
        current_ma26 = ma26_list[0]
        min_ma26_past_52_weeks = min(ma26_list)
        sos = current_ma26 - min_ma26_past_52_weeks # SOS 衰退指標公式

        # ==========================================
        # 5. 整合輸出 JSON (最重要：加入咗 stable_days)
        # ==========================================
        live_data = {
            "sp500": round(sp500_current, 2),
            "ma200": round(ma200, 2),
            "vix": round(vix, 2),
            "spread": int(spread_bp),
            "sos": round(sos, 3),
            "stable_days": stable_days,  # <--- 呢度就係你網頁要讀取嗰粒數！
            "last_updated": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        }

        # 確保 data 資料夾存在並寫入 JSON
        os.makedirs('data', exist_ok=True)
        with open('data/live.json', 'w', encoding='utf-8') as f:
            json.dump(live_data, f, indent=4)
            
        print("✅ 數據更新成功！", live_data)

    except Exception as e:
        print(f"❌ 獲取數據失敗: {e}")
        exit(1)

if __name__ == "__main__":
    if not API_KEY:
        print("找不到 FRED_API_KEY 環境變數！")
        exit(1)
    main()
