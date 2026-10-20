import os
import json
import base64
import requests
import datetime
import time

SECTOR_ETFS = {
    "XLK": "科技", "XLF": "金融", "XLE": "能源", "XLV": "醫療保健",
    "XLY": "非必需消費", "XLP": "必需消費", "XLU": "公用事業",
    "XLI": "工業", "XLB": "原材料", "XLRE": "房地產", "XLC": "通訊服務",
}

def get_access_token():
    """從 GitHub Secrets 的 Base64 中解析出 access_token"""
    b64_str = os.environ.get("LONGBRIDGE_OAUTH_TOKEN_CACHE_B64")
    if not b64_str:
        raise RuntimeError("缺少 LONGBRIDGE_OAUTH_TOKEN_CACHE_B64 環境變數")
    
    try:
        # 解碼 Base64 並轉換為 JSON
        token_info = json.loads(base64.b64decode(b64_str).decode('utf-8'))
        return token_info.get("access_token")
    except Exception as e:
        print(f"❌ 解析 Token 失敗: {e}")
        return None

def fetch_active_flow_http(access_token, symbol):
    """使用 HTTP GET 請求長橋 REST API"""
    url = "https://openapi.longbridge.com/v1/quote/trades"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    params = {
        "symbol": f"{symbol}.US",
        "count": 100
    }
    
    try:
        # ⚠️ 核心：強制設定 timeout=10，如果 10 秒無回應就自動放棄
        res = requests.get(url, headers=headers, params=params, timeout=10)
        
        if res.status_code != 200:
            print(f"[HTTP {res.status_code}]", end=" ")
            return None
            
        data = res.json()
        trades = data.get("data", {}).get("trades", [])
        
        if not trades:
            return None

        active_buy_amount = 0.0
        active_sell_amount = 0.0
        
        for t in trades:
            price = float(t.get("price", 0))
            volume = int(t.get("volume", 0))
            amount = price * volume
            
            direction = t.get("direction")
            if direction == 2:     # 2 = Up (主動買入)
                active_buy_amount += amount
            elif direction == 1:   # 1 = Down (主動賣出)
                active_sell_amount += amount

        net_flow_usd = active_buy_amount - active_sell_amount
        time_str = datetime.datetime.now().strftime('%H:%M')

        return {
            "time": time_str,
            "main_net_inflow": float(net_flow_usd)
        }
        
    except requests.exceptions.RequestException:
        # 捕捉超時或網絡錯誤，靜默跳過
        return None

def main():
    print("🔐 解析 Token...")
    access_token = get_access_token()
    if not access_token:
        print("❌ 無法獲取 access_token，請檢查 Secret")
        return
        
    print("✅ 獲取成功，開始拉取數據...\n")
    rows = []
    
    for symbol, name in SECTOR_ETFS.items():
        print(f"處理 {symbol} ({name})...", end=" ", flush=True)
        flow = fetch_active_flow_http(access_token, symbol)
        
        if flow:
            print(f"成功 (淨流: ${flow['main_net_inflow']:.2f})")
            rows.append({
                "symbol": symbol, "name": name,
                "time": flow["time"], "main_net_inflow": flow["main_net_inflow"],
            })
        else:
            print("失敗或無數據")
            rows.append({"symbol": symbol, "name": name, "main_net_inflow": None, "time": "—"})
        
        # 每隻之間休息 0.5 秒，避免觸發限流
        time.sleep(0.5)

    output = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "note": "盤中即時主動買賣盤（Longbridge HTTP API）",
        "sectors": rows,
    }

    os.makedirs("data/flow", exist_ok=True)
    with open("data/flow/intraday.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n完成，已寫入 data/flow/intraday.json（{len(rows)} 個板塊）")

if __name__ == "__main__":
    main()
