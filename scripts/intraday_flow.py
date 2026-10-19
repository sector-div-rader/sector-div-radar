import requests
import json
import datetime
import os
import time

# 11 隻 SPDR 板塊 ETF 嘅美股代碼（東財格式）
SECTOR_SYMBOLS = [
    "XLK.US", "XLF.US", "XLE.US", "XLV.US", "XLY.US",
    "XLP.US", "XLU.US", "XLI.US", "XLB.US", "XLRE.US", "XLC.US",
]

# 東財分鐘級資金流端點
MINUTE_URL = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"

# 分鐘線字段：f51..f56（時間 + 主力/小/中/大/超大單淨流入）
MINUTE_FIELDS = "f51,f52,f53,f54,f55,f56"


def resolve_secid(symbol: str) -> str | None:
    """
    用東財 suggest 端點將美股代碼（如 XLK.US）解析成 secid（如 106.XLK）。
    呢個方法可以避免手動猜測 market code（105/106/107）。
    """
    url = f"https://searchapi.eastmoney.com/api/suggest/get?input={symbol.split('.')[0]}&type=14"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        items = data.get("QuotationCodeTable", {}).get("Data", [])
        for item in items:
            if item.get("Code") == symbol.split(".")[0]:
                return item.get("QuoteID")  # QuoteID 就係 secid
    except Exception as e:
        print(f"[Intraday] secid 解析失敗 {symbol}: {e}")
    return None


def fetch_intraday_flow(secid: str) -> dict | None:
    """
    調用東財分鐘級資金流端點，返回最新一根 Bar 嘅主力淨流入。
    注意：東財按源 IP 限流，請求之間必須加入延遲。
    """
    params = {
        "secid": secid,
        "klt": "1",              # 1 分鐘
        "lmt": "0",              # 不限條數
        "fields1": "f1,f2,f3,f7",
        "fields2": MINUTE_FIELDS,
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(MINUTE_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        klines = data.get("data", {}).get("klines", [])
        if not klines:
            return None
        latest = klines[-1].split(",")
        # 格式：timestamp, main, small, medium, large, super_large
        return {
            "time": latest[0],
            "main_net_inflow": float(latest[1]),
        }
    except Exception as e:
        print(f"[Intraday] {secid} 失敗: {e}")
        return None


def main():
    rows = []
    for symbol in SECTOR_SYMBOLS:
        print(f"處理 {symbol}...")
        secid = resolve_secid(symbol)
        if not secid:
            rows.append({"symbol": symbol.split(".")[0], "name": symbol.split(".")[0], "error": "secid 解析失敗"})
            continue

        flow = fetch_intraday_flow(secid)
        name = symbol.split(".")[0]
        if flow:
            rows.append({
                "symbol": name,
                "name": name,
                "secid": secid,
                "time": flow["time"],
                "main_net_inflow": flow["main_net_inflow"],
            })
        else:
            rows.append({"symbol": name, "name": name, "secid": secid, "error": "數據獲取失敗"})

        # ⚠️ 關鍵：東財按 IP 限流，每次請求之間必須延遲（預設 1 秒）
        time.sleep(1.5)

    output = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "note": "東方財富盤中分鐘級資金流（主力淨流入，單位：人民幣元）",
        "sectors": rows,
    }

    os.makedirs("data/flow", exist_ok=True)
    with open("data/flow/intraday.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"完成，已寫入 data/flow/intraday.json（{len(rows)} 個板塊）")


if __name__ == "__main__":
    main()
