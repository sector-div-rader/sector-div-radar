import os
import sys
import json
import datetime
import time
import pandas as pd
from longbridge.openapi import QuoteContext, Config, OAuthBuilder

QQQ_CORE_TICKERS = {
    "QQQ": "納指100ETF",
    "NVDA": "輝達",
    "AAPL": "蘋果",
    "MSFT": "微軟",
    "AMZN": "亞馬遜",
    "META": "Meta",
    "GOOGL": "Alphabet",
    "TSLA": "特斯拉",
}

SECTOR_ETFS = {
    "XLK": "科技",
    "XLF": "金融",
    "XLE": "能源",
    "XLV": "醫療保健",
    "XLY": "非必需消費",
    "XLP": "必需消費",
    "XLU": "公用事業",
    "XLI": "工業",
    "XLB": "原材料",
    "XLRE": "房地產",
    "XLC": "通訊服務",
}


def init_longbridge():
    """初始化長橋 API（兼容 CI 無人值守環境）"""
    client_id = os.getenv("LONGBRIDGE_OAUTH_CLIENT_ID")
    if not client_id:
        raise ValueError("❌ 找不到 LONGBRIDGE_OAUTH_CLIENT_ID！請檢查 Secrets 名稱是否正確。")

    token_path = os.path.expanduser(f"~/.longbridge/openapi/tokens/{client_id}")
    if os.getenv("GITHUB_ACTIONS") == "true" and not os.path.exists(token_path):
        raise FileNotFoundError(f"❌ CI 環境找不到 Token 快取檔: {token_path}")

    oauth = OAuthBuilder(client_id).build(lambda url: print("請訪問:", url, flush=True))
    config = Config.from_oauth(oauth)
    return QuoteContext(config)


def parse_timestamps(ts_series):
    """兼容 Unix 秒數與 datetime 物件，統一轉為美東時間"""
    first_val = ts_series.iloc[0]
    if isinstance(first_val, (int, float)):
        dt = pd.to_datetime(ts_series, unit="s", utc=True)
    else:
        dt = pd.to_datetime(ts_series, utc=True)
    return dt.dt.tz_convert("America/New_York")


def fetch_intraday_flow(ctx, symbol, retries=2):
    """獲取當日分鐘級累計資金流，並按美股常規時段切分真實增量"""
    lb_symbol = f"{symbol}.US"

    for attempt in range(1, retries + 1):
        try:
            resp = ctx.capital_flow(lb_symbol)
            if not resp:
                return None

            df = pd.DataFrame([
                {"timestamp": line.timestamp, "cum_inflow": float(line.inflow)}
                for line in resp
            ])

            if df.empty:
                return None

            df["time"] = parse_timestamps(df["timestamp"])
            df = df.sort_values("time").reset_index(drop=True)

            latest_dt = df["time"].iloc[-1]
            latest_time_str = latest_dt.strftime("%H:%M")
            trade_date_str = latest_dt.strftime("%Y-%m-%d")

            t_open = datetime.time(9, 30)
            t_1030 = datetime.time(10, 30)
            t_1500 = datetime.time(15, 0)
            t_close = datetime.time(16, 0)
            times = df["time"].dt.time

            pre_df = df[times < t_open]
            base_open = float(pre_df["cum_inflow"].iloc[-1]) if not pre_df.empty else 0.0

            df_before_1030 = df[(times >= t_open) & (times < t_1030)]
            end_open_1h = float(df_before_1030["cum_inflow"].iloc[-1]) if not df_before_1030.empty else base_open

            df_before_1500 = df[(times >= t_1030) & (times < t_1500)]
            end_mid = float(df_before_1500["cum_inflow"].iloc[-1]) if not df_before_1500.empty else end_open_1h

            df_before_close = df[(times >= t_1500) & (times <= t_close)]
            end_close_1h = float(df_before_close["cum_inflow"].iloc[-1]) if not df_before_close.empty else end_mid

            inflow_open_1h = end_open_1h - base_open
            inflow_mid = end_mid - end_open_1h
            inflow_close_1h = end_close_1h - end_mid
            rth_net_inflow = end_close_1h - base_open
            total_net_inflow = float(df["cum_inflow"].iloc[-1])

            return {
                "trade_date": trade_date_str,
                "time": latest_time_str,
                "main_net_inflow": round(rth_net_inflow, 2),
                "total_net_inflow": round(total_net_inflow, 2),
                "pre_market_inflow": round(base_open, 2),
                "net_inflow_open_1h": round(inflow_open_1h, 2),
                "net_inflow_mid": round(inflow_mid, 2),
                "net_inflow_close_1h": round(inflow_close_1h, 2),
            }

        except Exception as e:
            if attempt < retries:
                time.sleep(0.5)
            else:
                print(f"  [Longbridge] {symbol} 失敗: {e}", flush=True)
                return None


def collect_group(ctx, ticker_map, group_label):
    rows = []
    success = 0
    latest_date = ""

    print(f"\n--- 抓取 {group_label} ({len(ticker_map)} 隻) ---", flush=True)
    for symbol, name in ticker_map.items():
        print(f"處理 {symbol} ({name})...", end=" ", flush=True)
        flow = fetch_intraday_flow(ctx, symbol)

        if flow:
            success += 1
            if flow["trade_date"] > latest_date:
                latest_date = flow["trade_date"]
            print(
                f"成功 [{flow['trade_date']} {flow['time']}] "
                f"(RTH總流: ${flow['main_net_inflow']:,.0f} | 開盤: ${flow['net_inflow_open_1h']:,.0f})",
                flush=True,
            )
            rows.append({
                "symbol": symbol,
                "name": name,
                "status": "ok",
                "trade_date": flow["trade_date"],
                "time": flow["time"],
                "main_net_inflow": flow["main_net_inflow"],
                "total_net_inflow": flow["total_net_inflow"],
                "pre_market_inflow": flow["pre_market_inflow"],
                "net_inflow_open_1h": flow["net_inflow_open_1h"],
                "net_inflow_mid": flow["net_inflow_mid"],
                "net_inflow_close_1h": flow["net_inflow_close_1h"],
            })
        else:
            print("失敗或無數據", flush=True)
            rows.append({
                "symbol": symbol,
                "name": name,
                "status": "error",
                "trade_date": "—",
                "time": "—",
                "main_net_inflow": 0.0,
                "total_net_inflow": 0.0,
                "pre_market_inflow": 0.0,
                "net_inflow_open_1h": 0.0,
                "net_inflow_mid": 0.0,
                "net_inflow_close_1h": 0.0,
            })

        time.sleep(0.15)

    return rows, success, latest_date


def main():
    print("正在啟動 QQQ 核心 + 板塊盤中資金流抓取程序...", flush=True)

    try:
        ctx = init_longbridge()
        print("✅ 長橋認證成功！正在建立連線...", flush=True)
    except Exception as e:
        print(f"❌ 長橋初始化失敗: {e}", flush=True)
        sys.exit(1)

    qqq_rows, qqq_ok, qqq_date = collect_group(ctx, QQQ_CORE_TICKERS, "QQQ & 七巨頭")
    sector_rows, sector_ok, sector_date = collect_group(ctx, SECTOR_ETFS, "11 大板塊 ETF")

    total_success = qqq_ok + sector_ok
    latest_trade_date = max(qqq_date, sector_date)

    output_path = "data/flow/intraday.json"
    if total_success == 0:
        print("\n⚠️ 所有標的均無有效數據，保留原有 intraday.json 避免清零覆蓋。", flush=True)
        sys.exit(1)

    output = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "trade_date": latest_trade_date,
        "success_count": total_success,
        "note": "QQQ + 七巨頭 & 板塊真實資金流（長橋 API，常規時段增量）",
        "qqq_core": qqq_rows,
        "sectors": sector_rows,
    }

    os.makedirs("data/flow", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(
        f"\n✅ 完成，已寫入 {output_path}（QQQ核心 {qqq_ok}/{len(qqq_rows)} | 板塊 {sector_ok}/{len(sector_rows)}）",
        flush=True,
    )


if __name__ == "__main__":
    main()
