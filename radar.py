import yfinance as yf
import pandas as pd
import os
import requests
import urllib.parse
from datetime import datetime

ETFS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
PHONE = "85263306575"
CALLMEBOT_APIKEY = os.getenv("CALLMEBOT_APIKEY")

if CALLMEBOT_APIKEY:
    print(f"CALLMEBOT_APIKEY: 已設定 {CALLMEBOT_APIKEY[:2]}***")
else:
    print("CALLMEBOT_APIKEY: 未設定")

report_lines = []
alerts = []
daily_row = {}
today_str = datetime.now().strftime("%Y-%m-%d")
daily_row['日期'] = today_str

for etf in ETFS:
    try:
        df = yf.download(etf, period="6mo", interval="1d", progress=False, auto_adjust=True)
        if df.empty:
            print(f"{etf} 無數據")
            continue

        # 兼容新版yfinance會返回DataFrame
        if isinstance(df['Close'], pd.DataFrame):
            close = df['Close'].iloc[:,0]
        else:
            close = df['Close']

        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        dif = ema12 - ema26

        # 計漲跌
        if len(close) >= 2:
            pct = float((close.iloc[-1] / close.iloc[-2] - 1) * 100)
        else:
            pct = 0.0

        daily_row[etf] = round(pct, 2)

        # 背離
        if len(close) > 10:
            price_up = close.iloc[-1] > close.iloc[-10]
            dif_down = dif.iloc[-1] < dif.iloc[-10]
            price_down = close.iloc[-1] < close.iloc[-10]
            dif_up = dif.iloc[-1] > dif.iloc[-10]

            if price_up and dif_down:
                alerts.append(f"{etf} D 頂背離")
            if price_down and dif_up:
                alerts.append(f"{etf} D 底背離")

        line = f"{etf}: {pct:+.2f}% | DIF {float(dif.iloc[-1]):.3f}"
        report_lines.append(line)
        print(line)

    except Exception as e:
        print(f"{etf} error {e}")
        daily_row[etf] = 0

# 存 history.csv
csv_path = "history.csv"
try:
    new_df = pd.DataFrame([daily_row])
    if os.path.exists(csv_path):
        hist = pd.read_csv(csv_path)
        hist = pd.concat([hist, new_df], ignore_index=True).drop_duplicates(subset=['日期'], keep='last')
    else:
        hist = new_df
    hist = hist[["日期"] + [c for c in ETFS if c in hist.columns or c in daily_row]]
    hist.to_csv(csv_path, index=False)
    print(f"history.csv 已更新 共{len(hist)}日")
except Exception as e:
    print(f"CSV error {e}")

final_report = f"📊 板塊雷達 {today_str}\n" + "\n".join(report_lines)
final_report += "\n\n" + ("🔔 信號:\n" + "\n".join(alerts) if alerts else "今日無背離/高換手信號")

print(final_report)

if CALLMEBOT_APIKEY:
    url = f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={urllib.parse.quote(final_report)}&apikey={CALLMEBOT_APIKEY}"
    try:
        r = requests.get(url, timeout=20)
        print(f"WhatsApp API回應: {r.text} 狀態: {r.status_code}")
    except Exception as e:
        print(f"WhatsApp失敗: {e}")
else:
    print("未設定 CALLMEBOT_APIKEY")