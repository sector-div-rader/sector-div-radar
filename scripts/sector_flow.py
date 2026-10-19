# scripts/sector_flow.py
import os
import json
import datetime
import traceback

import eulerpool
import yfinance as yf

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
    """
    嘗試從 Eulerpool 拉真實 ETF 資金流。
    成功返回 float，失敗返回 None。
    """
    try:
        result = client.etf.flows(symbol)
        # SDK 返回結構可能係 list 或 dict，逐一兼容
        if isinstance(result, list) and len(result) > 0:
            latest = result[-1]
            for key in ("net_flow", "netFlow", "flow"):
                if key in latest:
                    return float(latest[key])
        if isinstance(result, dict):
            for key in ("net_flow", "netFlow", "flow"):
                if key in result:
                    return float(result[key])
    except Exception as e:
        print(f"  [Eulerpool] {symbol} 失敗: {e}")
    return None


def fetch_proxy_flow(symbol, window=1):
    """
    Volume-price proxy: pct_change × avg dollar_volume。
    兼容 yfinance 0.2.48+ 返回 MultiIndex 的 DataFrame 格式。
    """
    try:
        df = yf.download(
            symbol,
            period=f"{window + 10}d",
            progress=False,
            auto_adjust=True,
            multi_level_index=False,  # 關鍵：強制單一價格列為一維索引
        )
        if df is None or len(df) < window + 1:
            return None

        # 兼容保護：如果未來結構變化仍出現 MultiIndex，則強行展平
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        closes = df["Close"].iloc[-(window + 1):]
        # 確保為單一 Series，避免後續 float() 遇到 DataFrame/Series
        if isinstance(closes, pd.DataFrame):
            closes = closes.iloc[:, 0]

        # 使用 .item() 或顯式轉換為 float 提取純量
        start_price = float(closes.iloc[0])
        end_price = float(closes.iloc[-1])
        
        if start_price == 0 or pd.isna(start_price) or pd.isna(end_price):
            return None
            
        pct = (end_price / start_price) - 1.0

        vols = df["Volume"].iloc[-window:]
        if isinstance(vols, pd.DataFrame):
            vols = vols.iloc[:, 0]
            
        # 計算平均交易額
        dollar_vols = (df["Close"].iloc[-window:].values.flatten() * vols.values.flatten())
        dvol = float(pd.Series(dollar_vols).mean())

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

    # 相對 SPY 資金流（對沖全市場同升同跌）
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
    with open(
        f"data/flow/history/{output['as_of']}.json", "w", encoding="utf-8"
    ) as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    client.close()
    print(f"完成，已寫入 data/flow/latest.json（{len(rows)} 個板塊）")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
