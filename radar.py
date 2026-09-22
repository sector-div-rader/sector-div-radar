import yfinance as yf
import pandas as pd
import os
import requests
import urllib.parse
from datetime import datetime

ETFS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]

CALLMEBOT_APIKEY = os.getenv("CALLMEBOT_APIKEY")
PHONE = os.getenv("PHONE")

report_lines = []
alerts = []
daily_row = {}
today_str = datetime.now().strftime("%Y-%m-%d")
daily_row['日期'] = today_str

# --- 1. 拉數據同計分 ---
for etf in ETFS:
    try:
        df = yf.download(etf, period="6mo", interval="1d", progress=False)
        if df.empty:
            continue
        close = df['Close']
        # 簡單MACD DIF
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9).mean()

        # 近5日漲跌
        pct = (close.iloc[-1] / close.iloc[-2] - 1) * 100 if len(close) > 1 else 0
        pct = float(pct.iloc[0]) if hasattr(pct, 'iloc') else float(pct)
        daily_row[etf] = round(pct, 2)

        # 背離判斷 (簡版)
        price_trend = close.iloc[-1] > close.iloc[-10] if len(close) > 10 else False
        dif_trend = dif.iloc[-1] < dif.iloc[-10] if len(dif) > 10 else False

        line = f"{etf}: {pct:+.2f}% | DIF {float(dif.iloc[-1]):.3f}"

        # 加埋 4h/日/週 標記 (你之前要嘅格式)
        # 日線頂背離
        if price_trend and dif_trend:
            alerts.append(f"{etf} D 頂背離 (價升DIF跌)")
            line += " [D頂]"
        if not price_trend and not dif_trend and dif_trend == False:
            # 底背離
            if close.iloc[-1] < close.iloc[-10] and dif.iloc[-1] > dif.iloc[-10]:
                alerts.append(f"{etf} D 底背離 (價跌DIF升)")
                line += " [D底]"

        report_lines.append(line)
        print(line)

    except Exception as e:
        print(f"{etf} error {e}")
        daily_row[etf] = 0

# --- 2. 更新 history.csv (同一張表) ---
csv_path = "history.csv"
try:
    new_df = pd.DataFrame([daily_row])
    if os.path.exists(csv_path):
        hist = pd.read_csv(csv_path)
        hist = pd.concat([hist, new_df], ignore_index=True)
        # 去重同排返11個板塊次序
        hist = hist.drop_duplicates(subset=['日期'], keep='last')
    else:
        hist = new_df

    cols = ["日期"] + ETFS
    hist = hist[[c for c in cols if c in hist.columns]]
    hist.to_csv(csv_path, index=False)
    print("history.csv 已更新")
except Exception as e:
    print(f"CSV error {e}")

# --- 3. WhatsApp 戰報 ---
final_report = f"📊 板塊雷達 {daily_row['日期']}\n" + "\n".join(report_lines)
final_report += "\n\n" + ("--- 信號 ---\n" + "\n".join(alerts) if alerts else "今日無背離/高換手信號")

print(final_report)

if CALLMEBOT_APIKEY and PHONE:
    url = f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={urllib.parse.quote(final_report)}&apikey={CALLMEBOT_APIKEY}"
    try:
        r = requests.get(url, timeout=15)
        print(f"WhatsApp API回應: {r.text}")
    except Exception as e:
        print(f"WhatsApp發送失敗: {e}")
else:
    print("未設定 CALLMEBOT_APIKEY / PHONE")