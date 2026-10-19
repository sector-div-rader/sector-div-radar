import os
import json
import datetime
import base64
from longbridge.openapi import QuoteContext, Config, OAuthBuilder

SECTOR_ETFS = {
    "XLK": "科技", "XLF": "金融", "XLE": "能源", "XLV": "醫療保健",
    "XLY": "非必需消費", "XLP": "必需消費", "XLU": "公用事業",
    "XLI": "工業", "XLB": "原材料", "XLRE": "房地產", "XLC": "通訊服務",
}

def get_quote_context():
    client_id = os.environ.get("LONGBRIDGE_CLIENT_ID")
    token_cache_b64 = os.environ.get("LONGBRIDGE_OAUTH_TOKEN_CACHE_B64")
    
    if not client_id or not token_cache_b64:
        raise RuntimeError("缺少 LONGBRIDGE_CLIENT_ID 或 LONGBRIDGE_OAUTH_TOKEN_CACHE_B64 環境變數")

    # 還原 Token 快取檔案
    cache_dir = os.path.expanduser("~/.longbridge/openapi/tokens/")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, client_id)
    
    with open(cache_path, "wb") as f:
        f.write(base64.b64decode(token_cache_b64))

    oauth = OAuthBuilder(client_id).build(
        lambda url: print(f"⚠️ Token 失效: {url}")
    )
    config = Config.from_oauth(oauth)
    return QuoteContext(config)

def fetch_active_flow(ctx, symbol):
    """
    使用長橋 Trades 接口獲取最近約 1000 筆逐筆成交，
    精確計算主動買入 (Up) 與主動賣出 (Down) 的淨成交金額。
    """
    try:
        # 注意：symbol 需要是 "XLK.US" 格式
        trades = ctx.trades(f"{symbol}.US", 1000)
        
        if not trades:
            return None

        active_buy_amount = 0.0
        active_sell_amount = 0.0
        
        for t in trades:
            price = float(t.price)
            volume = t.volume
            amount = price * volume
            
            if t.direction == 2:    # 2 = Up (主動買入)
                active_buy_amount += amount
            elif t.direction == 1:  # 1 = Down (主動賣出)
                active_sell_amount += amount
            # 0 = Neutral，忽略不計

        # 主動淨流入 = 主動買入金額 - 主動賣出金額
        net_flow_usd = active_buy_amount - active_sell_amount
        
        # 獲取最新成交時間
        time_str = datetime.datetime.fromtimestamp(
            trades[0].timestamp
        ).strftime('%H:%M')
        
        return {
            "time": time_str,
            "main_net_inflow": float(net_flow_usd),
        }
    except Exception as e:
        print(f"  [Longbridge] {symbol} 失敗: {e}")
        return None

def main():
    ctx = get_quote_context()
    rows = []
    
    for symbol, name in SECTOR_ETFS.items():
        print(f"處理 {symbol} ({name})...")
        flow = fetch_active_flow(ctx, symbol)
        
        if flow:
            rows.append({
                "symbol": symbol,
                "name": name,
                "time": flow["time"],
                "main_net_inflow": flow["main_net_inflow"],
            })
        else:
            rows.append({
                "symbol": symbol,
                "name": name,
                "main_net_inflow": None,
                "time": "—",
            })

    output = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "note": "盤中即時主動買賣盤估算（Longbridge OpenAPI Tick Data）",
        "sectors": rows,
    }

    os.makedirs("data/flow", exist_ok=True)
    with open("data/flow/intraday.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"完成，已寫入 data/flow/intraday.json（{len(rows)} 個板塊）")

if __name__ == "__main__":
    main()
