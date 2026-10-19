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
    用 yfinance 拉取當日 1 分鐘 K 線，計算「今日至今」嘅累計估算資金流。
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1d", interval="1m", prepost=False)
        
        if df is None or df.empty or len(df) < 2:
            return None
            
        # 過濾掉成交量為 0 嘅 Bar（避免除數為零或數值失真）
        df = df[df['Volume'] > 0]
        if len(df) < 2:
            return None
            
        # 取今日開盤價同最新價
        today_open = float(df.iloc[0]['Open'])
        latest_close = float(df.iloc[-1]['Close'])
        total_volume = float(df['Volume'].sum())
        
        if today_open == 0:
            return None
            
        # 計算今日至今嘅價格變化百分比
        pct_change = (latest_close - today_open) / today_open
        
        # 估算今日至今嘅總成交額 (最新價 * 總成交量)
        dollar_volume = latest_close * total_volume
        
        # 計算今日至今嘅累計估算資金流
        flow = pct_change * dollar_volume
        
        # 將時間轉做 HKT (UTC+8)
        time_str = df.index[-1].tz_convert('Asia/Hong_Kong').strftime('%H:%M')
        
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
        print(f"處理 {symbol} ({name})...")
        flow = fetch_intraday_flow(symbol)
        
        if flow:
            rows.append({
                "symbol": symbol,
                "name": name,
                "time": flow["time"],
                "main_net_inflow": flow["main_net_inflow"]
            })
        else:
            rows.append({
                "symbol": symbol, 
                "name": name, 
                "main_net_inflow": None,
                "time": "—"
            })

    output = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "note": "盤中即時估算（yfinance 1分鐘線）",
        "sectors": rows,
    }

    os.makedirs("data/flow", exist_ok=True)
    with open("data/flow/intraday.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"完成，已寫入 data/flow/intraday.json（{len(rows)} 個板塊）")

if __name__ == "__main__":
    main()
