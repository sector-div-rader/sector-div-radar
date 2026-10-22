import os
import json
import datetime
import time
import pandas as pd
import yfinance as yf
from longbridge.openapi import QuoteContext, Config, OAuthBuilder

SECTOR_ETFS = {
    "XLK": "科技", "XLF": "金融", "XLE": "能源", "XLV": "醫療保健",
    "XLY": "非必需消費", "XLP": "必需消費", "XLU": "公用事業",
    "XLI": "工業", "XLB": "原材料", "XLRE": "房地產", "XLC": "通訊服務",
}

def init_longbridge():
    """初始化長橋 API"""
    client_id = os.getenv("LONGBRIDGE_OAUTH_CLIENT_ID")
    if not client_id:
        raise ValueError("❌ 找不到 LONGBRIDGE_OAUTH_CLIENT_ID！請檢查 Secrets 名稱是否正確。")
        
    oauth = OAuthBuilder(client_id).build(lambda url: print("請訪問:", url, flush=True))
    config = Config.from_oauth(oauth)
    return QuoteContext(config)

def fetch_intraday_flow(ctx, symbol):
    """使用長橋 API 獲取當日分鐘級資金流，按時段切分"""
    try:
        lb_symbol = f"{symbol}.US"
        resp = ctx.capital_flow(lb_symbol)
        
        if not resp:
            return None

        df = pd.DataFrame([
            {"timestamp": line.timestamp, "net_inflow": float(line.inflow)} 
            for line in resp
        ])

        if df.empty:
            return None

        df['time'] = pd.to_datetime(df['timestamp'], unit='s', utc=True).dt.tz_convert('America/New_York')
        latest_time_str = df['time'].iloc[-1].strftime('%H:%M')

        t_open = datetime.time(9, 30)
        t_1030 = datetime.time(10, 30)
        t_1500 = datetime.time(15, 0)
        t_close = datetime.time(16, 0)

        df_open = df[(df['time'].dt.time >= t_open) & (df['time'].dt.time < t_1030)]
        df_mid = df[(df['time'].dt.time >= t_1030) & (df['time'].dt.time < t_1500)]
        df_close = df[(df['time'].dt.time >= t_1500) & (df['time'].dt.time <= t_close)]

        return {
            "time": latest_time_str,
            "main_net_inflow": float(df['net_inflow'].sum()),
            "net_inflow_open_1h": float(df_open['net_inflow'].sum()),
            "net_inflow_mid": float(df_mid['net_inflow'].sum()),
            "net_inflow_close_1h": float(df_close['net_inflow'].sum())
        }
    except Exception as e:
        print(f"  [Longbridge] {symbol} 失敗: {e}", flush=True)
        return None

def generate_latest_flow():
    """用 yfinance 抓取前一日及歷史累計數據，寫入 latest.json"""
    print("正在生成前一個交易日數據 (latest.json)...", flush=True)
    rows = []
    today_date = datetime.datetime.now().date()
    target_date = "—"

    for symbol, name in SECTOR_ETFS.items():
        try:
            ticker = yf.Ticker(symbol)
            # 抓取最近一個月嘅日線數據，用嚟計 5日同 20日累計
            df = ticker.history(period="1mo", interval="1d")
            
            if len(df) >= 2:
                # 判斷最後一行係咪今日（如果係，前一日就係倒數第二行）
                if df.index[-1].date() == today_date:
                    target_row = df.iloc[-2]
                    target_date = df.index[-2].strftime('%Y-%m-%d')
                    calc_df = df.iloc[:-1]
                else:
                    target_row = df.iloc[-1]
                    target_date = df.index[-1].strftime('%Y-%m-%d')
                    calc_df = df

                # 估算當日資金流：(收盤 - 開盤) * 成交量
                net_flow_1d = float((target_row['Close'] - target_row['Open']) * target_row['Volume'])
                
                # 計算 5日 及 20日累計
                calc_df = calc_df.copy() # 避免 SettingWithCopyWarning
                calc_df['flow'] = (calc_df['Close'] - calc_df['Open']) * calc_df['Volume']
                net_flow_5d = float(calc_df['flow'].tail(5).sum())
                net_flow_20d = float(calc_df['flow'].tail(20).sum())
                rs_vs_spy = float(net_flow_1d / 1e8) # 模擬相對強弱

                rows.append({
                    "symbol": symbol,
                    "name": name,
                    "net_flow_1d": net_flow_1d,
                    "net_flow_5d": net_flow_5d,
                    "net_flow_20d": net_flow_20d,
                    "rs_vs_spy": rs_vs_spy
                })
                print(f"  ✅ {symbol} 歷史數據成功", flush=True)
            else:
                print(f"  ⚠️ {symbol} 數據不足", flush=True)
        except Exception as e:
            print(f"  ❌ [Latest] {symbol} 失敗: {e}", flush=True)
            
        time.sleep(0.5) # 避免 yfinance 限流

    output = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "as_of": target_date,
        "source_note": "前一日日線估算數據 (yfinance)",
        "sectors": rows
    }

    os.makedirs("data/flow", exist_ok=True)
    with open("data/flow/latest.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("✅ 已生成 data/flow/latest.json\n", flush=True)

def main():
    print("正在啟動程序...", flush=True)
    
    # 1. 生成歷史數據 (latest.json)
    generate_latest_flow()

    # 2. 生成即時數據 (intraday.json)
    print("正在連接長橋 API...", flush=True)
    try:
        ctx = init_longbridge()
        print("✅ 長橋認證成功！正在建立連線...", flush=True)
    except Exception as e:
        print(f"❌ 長橋初始化失敗: {e}", flush=True)
        return

    rows = []
    for symbol, name in SECTOR_ETFS.items():
        print(f"處理 {symbol} ({name})...", end=" ", flush=True)
        flow = fetch_intraday_flow(ctx, symbol)
        
        if flow:
            print(f"成功 (總流: ${flow['main_net_inflow']:,.0f} | 開盤: ${flow['net_inflow_open_1h']:,.0f})", flush=True)
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
            print("失敗或無數據", flush=True)
            rows.append({
                "symbol": symbol, 
                "name": name, 
                "main_net_inflow": 0.0,
                "net_inflow_open_1h": 0.0,
                "net_inflow_mid": 0.0,
                "net_inflow_close_1h": 0.0,
                "time": "—"
            })
        time.sleep(0.2)

    output = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "note": "盤中即時真實資金流（長橋 API，基於逐筆成交）",
        "sectors": rows,
    }

    with open("data/flow/intraday.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n完成，已寫入 data/flow/intraday.json（{len(rows)} 個板塊）", flush=True)

if __name__ == "__main__":
    main()
