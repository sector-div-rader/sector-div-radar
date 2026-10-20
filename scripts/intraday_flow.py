import yfinance as yf
import pandas as pd
import json
import datetime
import os

SECTOR_ETFS = {
    "XLK": "科技", "XLF": "金融", "XLE": "能源", "XLV": "醫療保健",
    "XLY": "非必需消費", "XLP": "必需消費", "XLU": "公用事業",
    "XLI": "工業", "XLB": "原材料", "XLRE": "房地產", "XLC": "通訊服務",
}

def fetch_intraday_flow(symbol):
    """
    對比昨日收盤價，計算今日至今嘅累計估算資金流。
    """
    try:
        ticker = yf.Ticker(symbol)
        # 拉取最近 5 日嘅 1 分鐘數據，確保一定有昨日嘅數據
        df = ticker.history(period="5d", interval="1m", prepost=False)
        
        if df is None or df.empty or len(df) < 2:
            return None
            
        df = df[df['Volume'] > 0]
        if len(df) < 2:
            return None
            
        # 獲取今日嘅數據
        today_str = df.index[-1].strftime('%Y-%m-%d')
        today_df = df[df.index.strftime('%Y-%m-%d') == today_str]
        
        if today_df.empty:
            return None
            
        # 獲取昨日嘅收盤價
        prev_df = df[df.index.strftime('%Y-%m-%d') < today_str]
        if prev_df.empty:
            return None
            
        prev_close = float(prev_df.iloc[-1]['Close'])
        latest_close = float(today_df.iloc[-1]['Close'])
        total_volume = float(today_df['Volume'].sum())
        
        if prev_close == 0:
            return None
            
        # 對比昨日收盤價嘅變化
        pct_change = (latest_close - prev_close) / prev_close
        dollar_volume = latest_close * total_volume
        flow = pct_change * dollar_volume
        
        time_str = today_df.index[-1].tz_convert('Asia/Hong_Kong').strftime('%H:%M')
        
        return {
            "time": time_str,
            "main_net_inflow": float(flow)
        }
    except Exception as e:
        print(f"  [Intraday] {symbol} 失敗: {e}")
        return None

def main():
    rows = []
    for symbol, name in SECTOR_ETFS.items():
        print(f"處理 {symbol} ({name})...", end=" ", flush=True)
        flow = fetch_intraday_flow(symbol)
        
        if flow:
            print(f"成功 (淨流: ${flow['main_net_inflow']:,.0f})")
            rows.append({
                "symbol": symbol,
                "name": name,
                "time": flow["time"],
                "main_net_inflow": flow["main_net_inflow"]
            })
        else:
            print("失敗或無數據")
            rows.append({
                "symbol": symbol, 
                "name": name, 
                "main_net_inflow": None,
                "time": "—"
            })

    output = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "note": "盤中即時估算（yfinance 1分鐘線，對比昨收）",
        "sectors": rows,
    }

    os.makedirs("data/flow", exist_ok=True)
    with open("data/flow/intraday.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n完成，已寫入 data/flow/intraday.json（{len(rows)} 個板塊）")

if __name__ == "__main__":
    main()
