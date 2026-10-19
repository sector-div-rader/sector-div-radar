import os
import json
import datetime
import base64
import time  # 👈 加入 time
from longbridge.openapi import QuoteContext, Config, OAuthBuilder

SECTOR_ETFS = {
    "XLK": "科技", "XLF": "金融", "XLE": "能源", "XLV": "醫療保健",
    "XLY": "非必需消費", "XLP": "必需消費", "XLU": "公用事業",
    "XLI": "工業", "XLB": "原材料", "XLRE": "房地產", "XLC": "通訊服務",
}

def get_quote_context():
    # ... (保持不變) ...
    client_id = os.environ.get("LONGBRIDGE_CLIENT_ID")
    token_cache_b64 = os.environ.get("LONGBRIDGE_OAUTH_TOKEN_CACHE_B64")
    
    if not client_id or not token_cache_b64:
        raise RuntimeError("缺少環境變數")

    cache_dir = os.path.expanduser("~/.longbridge/openapi/tokens/")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, client_id)
    
    with open(cache_path, "wb") as f:
        f.write(base64.b64decode(token_cache_b64))

    oauth = OAuthBuilder(client_id).build(lambda url: None) # 避免印出長 URL 塞爆 Log
    config = Config.from_oauth(oauth)
    return QuoteContext(config)

def fetch_active_flow(ctx, symbol):
    try:
        # 💡 優化：只攞最近 100 筆成交，已經足夠反映當下幾分鐘嘅主動買賣方向，大幅加快速度
        trades = ctx.trades(f"{symbol}.US", 100)
        
        if not trades:
            return None

        active_buy_amount = 0.0
        active_sell_amount = 0.0
        
        for t in trades:
            price = float(t.price)
            volume = t.volume
            amount = price * volume
            
            if t.direction == 2:
                active_buy_amount += amount
            elif t.direction == 1:
                active_sell_amount += amount

        net_flow_usd = active_buy_amount - active_sell_amount
        time_str = datetime.datetime.fromtimestamp(trades[0].timestamp).strftime('%H:%M')
        
        return {"time": time_str, "main_net_inflow": float(net_flow_usd)}
    except Exception as e:
        print(f"  [Longbridge] {symbol} 失敗: {e}")
        return None

def main():
    print("🔐 正在建立連線...")
    ctx = get_quote_context()
    print("✅ 連線成功，開始拉取數據...\n")
    rows = []
    
    for symbol, name in SECTOR_ETFS.items():
        print(f"處理 {symbol} ({name})...", end=" ", flush=True) # 👈 印出進度
        flow = fetch_active_flow(ctx, symbol)
        
        if flow:
            print(f"成功 (時間: {flow['time']}, 淨流: ${flow['main_net_inflow']:.2f})")
            rows.append({
                "symbol": symbol, "name": name,
                "time": flow["time"], "main_net_inflow": flow["main_net_inflow"],
            })
        else:
            print("失敗")
            rows.append({"symbol": symbol, "name": name, "main_net_inflow": None, "time": "—"})
        
        time.sleep(0.5) # 👈 每隻 ETF 之間強制休息 0.5 秒，避免觸發長橋限流

    output = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "note": "盤中即時主動買賣盤估算（Longbridge OpenAPI Tick Data）",
        "sectors": rows,
    }

    os.makedirs("data/flow", exist_ok=True)
    with open("data/flow/intraday.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n完成，已寫入 data/flow/intraday.json（{len(rows)} 個板塊）")

if __name__ == "__main__":
    main()
