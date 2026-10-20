import os
import json
import requests
import datetime
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
    """
    使用 iTick 1 分鐘 K 線 API，對比昨日收盤價計算今日至今嘅估算累計資金流。
    """
    url = "https://api.itick.io/stock/kline"
    headers = {"accept": "application/json", "token": ITICK_TOKEN}
    params = {
        "region": "US",
        "code": symbol,
        "kType": 1,       # 1 分鐘 K 線
        "limit": 1000,    # 獲取足夠多嘅 K 線（約覆蓋 2-3 個交易日）
    }

    try:
        # 強制 10 秒超時，防止卡死
        res = requests.get(url, headers=headers, params=params, timeout=10)
        res.raise_for_status()
        payload = res.json()

        if payload.get("code") != 0:
            print(f"API 錯誤: {payload.get('msg')}")
            return None

        klines = payload.get("data", [])
        if not klines or len(klines) < 2:
            return None

        # iTick K 線按時間順序返回，最後一條係最新
        # 將時間戳轉換為美東時間日期，用於區分「今日」和「昨日」
        ny_tz = ZoneInfo("America/New_York")
        today_ny = datetime.datetime.now(ny_tz).date()

        today_klines = []
        prev_day_close = None

        for k in klines:
            # k["t"] 是 UTC 毫秒時間戳
            dt_utc = datetime.datetime.fromtimestamp(k["t"] / 1000, tz=datetime.timezone.utc)
            dt_ny = dt_utc.astimezone(ny_tz)

            if dt_ny.date() == today_ny:
                today_klines.append(k)
            elif dt_ny.date() < today_ny:
                # 記錄最近一個「昨日」的收盤價
                prev_day_close = float(k["c"])

        if not today_klines or prev_day_close is None or prev_day_close == 0:
            return None

        # 今日最新收盤價（最後一條 K 線）
        latest_close = float(today_klines[-1]["c"])
        # 今日總成交量（所有今日 K 線成交量之和）
        total_volume = sum(float(k["v"]) for k in today_klines)

        # 對比昨日收盤價的變化
        pct_change = (latest_close - prev_day_close) / prev_day_close
        # 估算累計資金流 = 價格變化百分比 × 今日總成交額
        dollar_volume = latest_close * total_volume
        net_flow_usd = pct_change * dollar_volume

        # 最後一條 K 線的時間（轉為 HKT 顯示）
        latest_time_utc = datetime.datetime.fromtimestamp(
            today_klines[-1]["t"] / 1000, tz=datetime.timezone.utc
        )
        time_str = latest_time_utc.astimezone(ZoneInfo("Asia/Hong_Kong")).strftime("%H:%M")

        return {
            "time": time_str,
            "main_net_inflow": float(net_flow_usd),
        }

    except requests.exceptions.RequestException as e:
        print(f"[iTick] {symbol} 請求失敗: {e}")
        return None
    except Exception as e:
        print(f"[iTick] {symbol} 解析失敗: {e}")
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
                "main_net_inflow": flow["main_net_inflow"],
            })
        else:
            print("失敗或無數據")
            rows.append({
                "symbol": symbol,
                "name": name,
                "main_net_inflow": None,
                "time": "—",
            })

        # 免費套餐每分鐘限 5 次調用，每次之間休息 1 秒確保安全
        import time
        time.sleep(1)

    output = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "note": "盤中即時估算（iTick 1分鐘K線，對比昨收）",
        "sectors": rows,
    }

    os.makedirs("data/flow", exist_ok=True)
    with open("data/flow/intraday.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n完成，已寫入 data/flow/intraday.json（{len(rows)} 個板塊）")


if __name__ == "__main__":
    main()
