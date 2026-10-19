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
    用 yfinance 拉取當日 1 分鐘 K 線，計算最新一根 K 線嘅估算資金流。
    """
    try:
        ticker = yf.Ticker(symbol)
        # 拉取今日嘅 1 分鐘數據，prepost=False 代表只計常規交易時段
        df = ticker.history(period="1d", interval="1m", prepost=False)
        
        if df is None or df.empty or len(df) < 2:
            return None
            
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 計算呢一分鐘嘅價格變化
        pct_change = (latest['Close'] - prev['Close']) / prev['Close']
        
        # 計算呢一分鐘嘅成交額 (價格 * 成交量)
        dollar_volume = latest['Close'] * latest['Volume']
        
        # 盤中估算資金流
        flow = pct_change * dollar_volume
        
        # 將時間轉做 HKT (UTC+8)
        time_str = latest.name.tz_convert('Asia/Hong_Kong').strftime('%H:%M')
        
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
