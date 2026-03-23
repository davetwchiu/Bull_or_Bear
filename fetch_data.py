import requests
import json
import os
import yfinance as yf
import pandas as pd
from datetime import datetime

# 從 GitHub Secrets 讀取 API Key
API_KEY = os.environ.get('FRED_API_KEY')

def get_fred_data(series_id, limit=1):
    """向 FRED API 獲取數據"""
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={API_KEY}&file_type=json&sort_order=desc&limit={limit}"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    valid_values = [float(obs['value']) for obs in data['observations'] if obs['value'] != '.']
    return valid_values

def calculate_at50():
    """自家製 $SPXA50R：計算 S&P 500 有幾多 % 股票高於 50天線"""
    print("正在從 Wikipedia 獲取 S&P 500 成份股名單...")
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    table = pd.read_html(url)[0]
    tickers = table['Symbol'].tolist()
    
    # 修正 Yahoo Finance 格式 (例如 BRK.B 轉 BRK-B)
    tickers = [t.replace('.', '-') for t in tickers]

    print(f"正在下載 {len(tickers)} 隻股票過去 3 個月嘅數據 (需時約 1-2 分鐘)...")
    # 批量下載數據，過濾走冇用嘅提示訊息
    data = yf.download(tickers, period="3mo", interval="1d", auto_adjust=True, progress=False)['Close']
    
    # 獲取最新一日嘅收市價
    latest_prices = data.iloc[-1]
    # 計算過去 50 日嘅移動平均線，並抽最後一日出嚟
    ma50 = data.rolling(window=50).mean().iloc[-1]
    
    # 比較：最新價 > 50天線
    above_50ma = (latest_prices > ma50).sum()
    total_valid = latest_prices.notna().sum() # 扣除當日停牌或冇數據嘅股票
    
    at50_percent = (above_50ma / total_valid) * 100
    print(f"AT50 計算完成: {above_50ma} / {total_valid} = {at50_percent:.2f}%")
    return round(at50_percent, 2)

def main():
    try:
        print("正在獲取 FRED 宏觀數據...")
        
        # 1. 獲取 S&P 500 及計算 200天線 / 企穩日數
        sp500_history = get_fred_data('SP500', limit=600)
        sp500_current = sp500_history[0]
        ma200 = sum(sp500_history[:200]) / 200

        stable_days = 0
        streak_started = False
        for i in range(250):
            price = sp500_history[i]
            historical_ma200 = sum(sp500_history[i : i+200]) / 200
            if price > historical_ma200:
                streak_started = True
                stable_days += 1
            else:
                if streak_started: break

        # 2. VIX 恐慌指數
        vix = get_fred_data('VIXCLS', limit=10)[0]

        # 3. High Yield Credit Spread (bp)
        spread_percent = get_fred_data('BAMLH0A0HYM2', limit=10)[0]
        spread_bp = spread_percent * 100

        # 4. Richmond Fed SOS
        iursa_history = get_fred_data('IURSA', limit=100)
        ma26_list = [sum(iursa_history[i : i+26]) / 26 for i in range(52)]
        sos = ma26_list[0] - min(ma26_list)

        # 5. 自家製 AT50 ($SPXA50R)
        at50_value = calculate_at50()

        # 整合輸出
        live_data = {
            "sp500": round(sp500_current, 2),
            "ma200": round(ma200, 2),
            "vix": round(vix, 2),
            "spread": int(spread_bp),
            "sos": round(sos, 3),
            "at50": at50_value,       # <--- 新增呢粒數！
            "stable_days": stable_days,
            "last_updated": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        }

        os.makedirs('data', exist_ok=True)
        with open('data/live.json', 'w', encoding='utf-8') as f:
            json.dump(live_data, f, indent=4)
            
        print("✅ 數據更新成功！")

    except Exception as e:
        print(f"❌ 獲取數據失敗: {e}")
        exit(1)

if __name__ == "__main__":
    if not API_KEY:
        print("找不到 FRED_API_KEY 環境變數！")
        exit(1)
    main()
