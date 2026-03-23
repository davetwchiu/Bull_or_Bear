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
        
        # 1. 獲取 S&P 500 (拎多啲數據確保扣除假日後有足夠 200 日計 MA)
        sp500_history = get_fred_data('SP500', limit=300)
        sp500_current = sp500_history[0]
        # 計算 200天線 (前 200 個有效交易日嘅平均值)
        ma200 = sum(sp500_history[:200]) / 200

        # 2. 獲取 VIX 恐慌指數
        vix = get_fred_data('VIXCLS', limit=10)[0]

        # 3. 獲取 High Yield Credit Spread (FRED 預設為 %, 轉換為 bp x100)
        spread_percent = get_fred_data('BAMLH0A0HYM2', limit=10)[0]
        spread_bp = spread_percent * 100

       # 4. 獲取並計算 Richmond Fed SOS (基於 IURSA 數據)
        # 官方邏輯：最新 26 週 IURSA 平均值 - 過去 52 週內該 26 週平均值嘅最低點
        # 需要最少 26 + 52 = 78 週數據，我哋安全起見拎 100 週
        iursa_history = get_fred_data('IURSA', limit=100)
        
        # 計算過去 52 週，每一週嘅 26 週移動平均線 (MA26)
        # index 0 係最新嗰週
        ma26_list = []
        for i in range(52):
            # iursa_history[i : i+26] 會拎到由第 i 週開始，向後數 26 週嘅歷史數據
            ma26 = sum(iursa_history[i : i+26]) / 26
            ma26_list.append(ma26)
            
        current_ma26 = ma26_list[0]
        min_ma26_past_52_weeks = min(ma26_list)
        
        # SOS 衰退指標 = 最新 MA26 - 過去一年最低嘅 MA26
        sos = current_ma26 - min_ma26_past_52_weeks

        # 整合輸出 JSON
        live_data = {
            "sp500": round(sp500_current, 2),
            "ma200": round(ma200, 2),
            "vix": round(vix, 2),
            "spread": int(spread_bp),
            "sos": round(sos, 3),
            "last_updated": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        }

        # 確保 data 資料夾存在
        os.makedirs('data', exist_ok=True)
        
        # 寫入 JSON 檔案
        with open('data/live.json', 'w', encoding='utf-8') as f:
            json.dump(live_data, f, indent=4)
            
        print("✅ 數據更新成功！", live_data)

    except Exception as e:
        print(f"❌ 獲取數據失敗: {e}")
        exit(1) # 讓 GitHub Actions 知道執行失敗

if __name__ == "__main__":
    if not API_KEY:
        print("找不到 FRED_API_KEY 環境變數！")
        exit(1)
    main()
