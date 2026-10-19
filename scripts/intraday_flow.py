import requests
import json
import datetime
import os

SECTOR_ETFS = {
    "XLK": "105.XLK", "XLF": "105.XLF", "XLE": "105.XLE",
    "XLV": "105.XLV", "XLY": "105.XLY", "XLP": "105.XLP",
    "XLU": "105.XLU", "XLI": "105.XLI", "XLB": "105.XLB",
    "XLRE": "105.XLRE", "XLC": "105.XLC",
}

def fetch_intraday_flow(secid):
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
    params = {
        "secid": secid,
        "klt": "1",          # 1 分鐘
        "lmt": "0",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56",
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        klines = data.get("data", {}).get("klines", [])
        if not klines:
            return None
        latest = klines[-1].split(",")
        # 格式: timestamp, main, small, medium, large, super_large
        return {
            "time": latest[0],
            "main_net_inflow": float(latest[1]),
        }
    except Exception as e:
        print(f"[Intraday] {secid} 失敗: {e}")
        return None

def main():
    rows = []
    for symbol, secid in SECTOR_ETFS.items():
        flow = fetch_intraday_flow(secid)
        rows.append({"symbol": symbol, "name": symbol, **(flow or {})})
    output = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "note": "東方財富盤中分鐘級資金流（主力淨流入）",
        "sectors": rows,
    }
    os.makedirs("data/flow", exist_ok=True)
    with open("data/flow/intraday.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
