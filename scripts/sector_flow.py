import os
import json
import datetime
import traceback

import eulerpool
import yfinance as yf
import pandas as pd  # 解決 name 'pd' is not defined 嘅關鍵

# ── 11 隻 SPDR 板塊 ETF ──
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
BENCH = "SPY"

def fetch_eulerpool_flow(client, symbol):
    """嘗試從 Eulerpool 拉真實 ETF 資金流。"""
    try:
        result = client.etf.flows(symbol)
        
        if isinstance(result, list) and len(result) > 0:
            # API 回傳係由新到舊，所以 [0] 係最新一日嘅數據
            latest = result[0] 
            
            # 根據 Log，真實嘅 Key 係 'estimated_flow'
            if 'estimated_flow' in latest and latest['estimated_flow'] is not None:
                return float(latest['estimated_flow'])
                
            # 保險起見，保留其他可能嘅 Key 名
            for key in ("net_flow", "netFlow", "flow"):
                if key in latest and latest[key] is not None:
                    return float(latest[key])
                    
        if isinstance(result, dict):
            for key in ("estimated_flow", "net_flow", "netFlow", "flow"):
                if key in result and result[key] is not None:
                    return float(result[key])
                    
    except Exception as e:
        print(f"  [Eulerpool] {symbol} 失敗: {e}")
    return None

def fetch_proxy_flow(symbol, window=1):
    """
    Volume-price proxy: pct_change × avg dollar_volume。
    改用 yf.Ticker().history() 避免 yfinance 多層索引 (MultiIndex) 問題。
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=f"{window + 10}d", auto_adjust=True)
        
        if df is None or len(df) < window + 1:
            return None

        closes = df["Close"].iloc[-(window + 1):]
        start_price = float(closes.iloc[0])
        end_price = float(closes.iloc[-1])
        
        if start_price == 0 or pd.isna(start_price) or pd.isna(end_price):
            return None
            
        pct = (end_price / start_price) - 1.0

        vols = df["Volume"].iloc[-window:]
        dollar_vols = df["Close"].iloc[-window:] * vols
        dvol = float(dollar_vols.mean())

        if dvol == 0 or pd.isna(dvol):
            return None
            
        return pct * dvol
    except Exception as e:
        print(f"  [Proxy] {symbol} 失敗: {e}")
        return None

def main():
    api_key = os.environ.get("EULERPOOL_KEY", "").strip()
    if not api_key:
        raise RuntimeError("EULERPOOL_KEY 環境變量未設置")

    client = eulerpool.Eulerpool(api_key)

    rows = []
    for symbol, name in SECTOR_ETFS.items():
        print(f"處理 {symbol} ({name})...")

        euler_flow = fetch_eulerpool_flow(client, symbol)
        if euler_flow is not None:
            source = "eulerpool"
            net_1d = euler_flow
        else:
            source = "proxy"
            net_1d = fetch_proxy_flow(symbol, 1)

        net_5d = fetch_proxy_flow(symbol, 5)
        net_20d = fetch_proxy_flow(symbol, 20)

        rows.append(
            {
                "symbol": symbol,
                "name": name,
                "net_flow_1d": net_1d,
                "net_flow_5d": net_5d,
                "net_flow_20d": net_20d,
                "source": source,
            }
        )

    # 相對 SPY 資金流
    spy_proxy_1d = fetch_proxy_flow(BENCH, 1)
    for r in rows:
        if r["net_flow_1d"] is not None and spy_proxy_1d is not None:
            r["rs_vs_spy"] = r["net_flow_1d"] - spy_proxy_1d
        else:
            r["rs_vs_spy"] = None

    output = {
        "as_of": datetime.date.today().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "source_note": "Eulerpool creation/redemption flows; volume-price proxy fallback",
        "sectors": rows,
    }

    os.makedirs("data/flow/history", exist_ok=True)
    with open("data/flow/latest.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    with open(f"data/flow/history/{output['as_of']}.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    client.close()
    print(f"完成，已寫入 data/flow/latest.json（{len(rows)} 個板塊）")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
