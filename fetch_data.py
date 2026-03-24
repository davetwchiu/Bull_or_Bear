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
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    html_data = requests.get(url, headers=headers).text
    table = pd.read_html(html_data)[0]
    tickers = table['Symbol'].tolist()
    tickers = [t.replace('.', '-') for t in tickers]

    print(f"正在下載 {len(tickers)} 隻股票數據 (需時約 1 分鐘)...")
    data = yf.download(tickers, period="3mo", interval="1d", auto_adjust=True, progress=False)['Close']
    
    latest_prices = data.iloc[-1]
    ma50 = data.rolling(window=50).mean().iloc[-1]
    
    above_50ma = (latest_prices > ma50).sum()
    total_valid = latest_prices.notna().sum()
    
    at50_percent = (above_50ma / total_valid) * 100
    print(f"AT50 計算完成: {at50_percent:.2f}%")
    return round(at50_percent, 2)

def main():
    try:
        # ==========================================
        # 1. 獲取 S&P 500 (改用 Yahoo Finance 解決 FRED 延遲問題)
        # ==========================================
        print("正在從 Yahoo Finance 獲取 S&P 500 最新報價...")
        # 拎過去 2 年數據，確保有足夠日數計 200MA 同埋回溯
        spx_data = yf.download('^GSPC', period="2y", interval="1d", progress=False)['Close']
        spx_data = spx_data.dropna() # 清理空值
        
        # 將 Series 轉為 1D 陣列 (解決 pandas 新版本警告)
        if isinstance(spx_data, pd.DataFrame):
            spx_data = spx_data.squeeze()

        sp500_current = float(spx_data.iloc[-1])
        
        # 計算每日的 200天線
        ma200_series = spx_data.rolling(window=200).mean().dropna()
        ma200 = float(ma200_series.iloc[-1])

        # 計算企穩日數 (由最新一日開始向過去推算)
        stable_days = 0
        streak_started = False
        
        # 將數據反轉，由最新日期開始向後 Check
        prices_reversed = spx_data.loc[ma200_series.index][::-1]
        ma200_reversed = ma200_series[::-1]

        for i in range(len(prices_reversed)):
            if i >= 250: # 最多回溯大約 1 年 (250 個交易日)
                break
                
            price = float(prices_reversed.iloc[i])
            historical_ma200 = float(ma200_reversed.iloc[i])
            
            if price > historical_ma200:
                streak_started = True
                stable_days += 1
            else:
                if streak_started:
                    break

        # ==========================================
        # 2. 獲取 FRED 宏觀數據 (VIX, Spread, SOS)
        # ==========================================
        print("正在獲取 FRED 宏觀數據...")
        vix = get_fred_data('VIXCLS', limit=10)[0]
        
        spread_percent = get_fred_data('BAMLH0A0HYM2', limit=10)[0]
        spread_bp = spread_percent * 100

        iursa_history = get_fred_data('IURSA', limit=100)
        ma26_list = [sum(iursa_history[i : i+26]) / 26 for i in range(52)]
        sos = ma26_list[0] - min(ma26_list)

        # ==========================================
        # 3. 自家製 AT50 ($SPXA50R)
        # ==========================================
        at50_value = calculate_at50()

        # ==========================================
        # 4. 整合並輸出 JSON
        # ==========================================
        live_data = {
            "sp500": round(sp500_current, 2),
            "ma200": round(ma200, 2),
            "vix": round(vix, 2),
            "spread": int(spread_bp),
            "sos": round(sos, 3),
            "at50": at50_value,
            "stable_days": stable_days,
            "last_updated": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        }

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
