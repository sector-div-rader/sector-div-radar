import os
import json
import datetime
import time
import pandas as pd
from longbridge.openapi import QuoteContext, Config, OAuthBuilder

SECTOR_ETFS = {
    "XLK": "科技", "XLF": "金融", "XLE": "能源", "XLV": "醫療保健",
    "XLY": "非必需消費", "XLP": "必需消費", "XLU": "公用事業",
    "XLI": "工業", "XLB": "原材料", "XLRE": "房地產", "XLC": "通訊服務",
}

def init_longbridge():
    print("正在初始化長橋認證...", flush=True)
    client_id = os.getenv("LONGBRIDGE_OAUTH_CLIENT_ID")
    if not client_id:
        raise ValueError("❌ 找不到 LONGBRIDGE_OAUTH_CLIENT_ID！")
        
    # 強制打印出嚟，確保 GitHub Actions 見到
    print(f"獲取到 Client ID: {client_id[:5]}...", flush=True)
    
    # 呢句可能會卡死，如果我哋見到呢句但冇下一步，就代表 Token 錯咗
    print("正在讀取 Token Cache...", flush=True)
    oauth = OAuthBuilder(client_id).build(lambda url: print(f"⚠️ 需要授權，請訪問: {url}", flush=True))
    
    config = Config.from_oauth(oauth)
    print("✅ 長橋認證成功！正在建立連線...", flush=True)
    return QuoteContext(config)

def fetch_intraday_flow(ctx, symbol):
    """
    使用長橋 API 獲取當日分鐘級資金流，並按時段切分
    """
    try:
        # 長橋美股代碼需要加 .US
        lb_symbol = f"{symbol}.US"
        resp = ctx.capital_flow(lb_symbol)
        
        # 1. 如果回傳係空，直接返回
        if not resp:
            return None

        # 2. 直接遍歷 resp 列表
        df = pd.DataFrame([
            {"timestamp": line.timestamp, "net_inflow": float(line.inflow)} 
            for line in resp
        ])

        if df.empty:
            return None

        # 將 Timestamp 轉換為美東時間 (New York)
        df['time'] = pd.to_datetime(df['timestamp'], unit='s', utc=True).dt.tz_convert('America/New_York')
        
        # 獲取最新嘅時間字串 (顯示喺前端)
        latest_time_str = df['time'].iloc[-1].strftime('%H:%M')

        # 定義美東時間嘅時段邊界
        t_open = datetime.time(9, 30)
        t_1030 = datetime.time(10, 30)
        t_1500 = datetime.time(15, 0)
        t_close = datetime.time(16, 0)

        # 1. 開盤頭一個鐘 (09:30 - 10:30)
        df_open = df[(df['time'].dt.time >= t_open) & (df['time'].dt.time < t_1030)]
        net_open_1h = df_open['net_inflow'].sum()

        # 2. 盤中 (10:30 - 15:00)
        df_mid = df[(df['time'].dt.time >= t_1030) & (df['time'].dt.time < t_1500)]
        net_mid = df_mid['net_inflow'].sum()

        # 3. 收市前一個鐘 (15:00 - 16:00)
        df_close = df[(df['time'].dt.time >= t_1500) & (df['time'].dt.time <= t_close)]
        net_close_1h = df_close['net_inflow'].sum()

        # 全日總計
        net_total = df['net_inflow'].sum()

        return {
            "time": latest_time_str,
            "main_net_inflow": float(net_total),
            "net_inflow_open_1h": float(net_open_1h),
            "net_inflow_mid": float(net_mid),
            "net_inflow_close_1h": float(net_close_1h)
        }
    except Exception as e:
        print(f"  [Longbridge] {symbol} 失敗: {e}")
        return None

def main():
    print("正在啟動程序...", flush=True)
    try:
        ctx = init_longbridge()
    except Exception as e:
        print(f"❌ 長橋初始化失敗: {e}", flush=True)
        return



    rows = []
    for symbol, name in SECTOR_ETFS.items():
        print(f"處理 {symbol} ({name})...", end=" ", flush=True)
        flow = fetch_intraday_flow(ctx, symbol)
        
        if flow:
            print(f"成功 (總流: ${flow['main_net_inflow']:,.0f} | 開盤: ${flow['net_inflow_open_1h']:,.0f})")
            rows.append({
                "symbol": symbol,
                "name": name,
                "time": flow["time"],
                "main_net_inflow": flow["main_net_inflow"],
                "net_inflow_open_1h": flow["net_inflow_open_1h"],
                "net_inflow_mid": flow["net_inflow_mid"],
                "net_inflow_close_1h": flow["net_inflow_close_1h"]
            })
        else:
            print("失敗或無數據")
            rows.append({
                "symbol": symbol, 
                "name": name, 
                "main_net_inflow": 0.0,
                "net_inflow_open_1h": 0.0,
                "net_inflow_mid": 0.0,
                "net_inflow_close_1h": 0.0,
                "time": "—"
            })
            
        # 防止觸發長橋 API 限流 (每秒不超過 10 次)
        time.sleep(0.2)

    output = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "note": "盤中即時真實資金流（長橋 API，基於逐筆成交）",
        "sectors": rows,
    }

    os.makedirs("data/flow", exist_ok=True)
    with open("data/flow/intraday.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n完成，已寫入 data/flow/intraday.json（{len(rows)} 個板塊）")

if __name__ == "__main__":
    main()
