import os
import json
import requests
import datetime
import time  # 確保有 import time
from zoneinfo import ZoneInfo

SECTOR_ETFS = {
    "XLK": "科技", "XLF": "金融", "XLE": "能源", "XLV": "醫療保健",
    "XLY": "非必需消費", "XLP": "必需消費", "XLU": "公用事業",
    "XLI": "工業", "XLB": "原材料", "XLRE": "房地產", "XLC": "通訊服務",
}

ITICK_TOKEN = os.environ.get("ITICK_TOKEN")
if not ITICK_TOKEN:
    raise RuntimeError("缺少 ITICK_TOKEN 環境變數")

def fetch_intraday_flow(symbol):
    url = "https://api.itick.io/stock/kline"
    headers = {"accept": "application/json", "token": ITICK_TOKEN}
    params = {
        "region": "US",
        "code": symbol,
        "kType": 1,       # 1 分鐘 K 線
        "limit": 100,     # 👈 由 1000 降到 100，降低 API 負載
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        
        # 👈 如果遇到 429，直接印出錯誤並返回 None
        if res.status_code == 429:
            return "429"
            
        res.raise_for_status()
        payload = res.json()

        if payload.get("code") != 0:
            print(f"API 錯誤: {payload.get('msg')}")
            return None

        klines = payload.get("data", [])
        if not klines or len(klines) < 2:
            return None

        ny_tz = ZoneInfo("America/New_York")
        today_ny = datetime.datetime.now(ny_tz).date()

        today_klines = []
        prev_day_close = None

        for k in klines:
            dt_utc = datetime.datetime.fromtimestamp(k["t"] / 1000, tz=datetime.timezone.utc)
            dt_ny = dt_utc.astimezone(ny_tz)

            if dt_ny.date() == today_ny:
                today_klines.append(k)
            elif dt_ny.date() < today_ny:
                prev_day_close = float(k["c"])

        if not today_klines or prev_day_close is None or prev_day_close == 0:
            return None

        latest_close = float(today_klines[-1]["c"])
        total_volume = sum(float(k["v"]) for k in today_klines)

        pct_change = (latest_close - prev_day_close) / prev_day_close
        dollar_volume = latest_close * total_volume
        net_flow_usd = pct_change * dollar_volume

        latest_time_utc = datetime.datetime.fromtimestamp(
            today_klines[-1]["t"] / 1000, tz=datetime.timezone.utc
        )
        time_str = latest_time_utc.astimezone(ZoneInfo("Asia/Hong_Kong")).strftime("%H:%M")

        return {
            "time": time_str,
            "main_net_inflow": float(net_flow_usd),
        }

    except Exception as e:
        print(f"[iTick] {symbol} 異常: {e}")
        return None

def main():
    rows = []
    # 因為免費版限每分鐘 5 次，我哋將請求分批處理
    for i, (symbol, name) in enumerate(SECTOR_ETFS.items()):
        print(f"處理 {symbol} ({name})...", end=" ", flush=True)
        flow = fetch_intraday_flow(symbol)

        # 👈 如果遇到 429，強制休息 15 秒再試下一隻（避開每分鐘限制）
        if flow == "429":
            print("觸發限流 (429)，等待 15 秒...")
            time.sleep(15)
            # 重新試一次
            flow = fetch_intraday_flow(symbol)

        if flow and flow != "429":
            print(f"成功 (淨流: ${flow['main_net_inflow']:,.0f})")
            rows.append({
                "symbol": symbol, "name": name,
                "time": flow["time"], "main_net_inflow": flow["main_net_inflow"],
            })
        else:
            print("失敗或無數據")
            rows.append({
                "symbol": symbol, "name": name,
                "main_net_inflow": None, "time": "—",
            })

        # 👈 每隻之間休息 2 秒，總共 11 隻約需 22 秒，完美避開 5次/分鐘 限制
        time.sleep(2)

    output = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "note": "盤中即時估算（iTick 1分鐘K線，對比昨收）",
        "sectors": rows,
    }

    os.makedirs("data/flow", exist_ok=True)
    with open("data/flow/intraday.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n完成，已寫入 data/flow/intraday.json（{len(rows)} 個板塊）")

if __name__ == "__main__":
    main()
