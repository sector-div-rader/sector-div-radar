import yfinance as yf
import requests
import os
import pandas as pd
from datetime import datetime
import urllib.parse

ETFS = ["XLB","XLE","XLF","XLI","XLK","XLP","XLU","XLV","XLY","XLG","XLC"]
CALLMEBOT_APIKEY = os.getenv("CALLMEBOT_APIKEY")
PHONE = "85263306575"

def get_dif(close):
    return close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()

def check_divergence(df, label):
    """回傳 背離字串"""
    if len(df) < 60:
        return None
    close = df['Close']
    dif = get_dif(close)
    recent_low_price = close.iloc[-30:-5].min()
    recent_high_price = close.iloc[-30:-5].max()
    recent_low_dif = dif.iloc[-30:-5].min()
    recent_high_dif = dif.iloc[-30:-5].max()

    curr_price = close.iloc[-1]
    curr_dif = dif.iloc[-1]

    if curr_price < recent_low_price and curr_dif > recent_low_dif:
        return f"{label}底背離"
    if curr_price > recent_high_price and curr_dif < recent_high_dif:
        return f"{label}頂背離"
    return None

alerts = []
daily_row = {"日期": datetime.now().strftime("%Y-%m-%d")}
report_lines = []

for sym in ETFS:
    try:
        # 日線用黎計漲跌同換手
        df_day = yf.Ticker(sym).history(period="6mo", interval="1d")
        if len(df_day) == 0:
            continue

        chg = df_day['Close'].pct_change().iloc[-1] * 100
        daily_row[sym] = f"{chg:.2f}%"
        report_lines.append(f"{sym}: {chg:+.2f}%")

        # 高換手 > 2.5倍
        vol = df_day['Volume'].iloc[-1]
        avg_vol = df_day['Volume'].rolling(20).mean().iloc[-1]
        if avg_vol > 0 and vol > avg_vol * 2.5:
            alerts.append(f"🔥 {sym} 高換手 {vol/avg_vol:.1f}倍 (日線)")

        # 檢查4h線同周線背離
        for interval, period, label in [("1wk", "2y", "周線"), ("4h", "3mo", "4h線")]:
            df = yf.Ticker(sym).history(period=period, interval=interval)
            div = check_divergence(df, label)
            if div:
                alerts.append(f"⚠️ {sym} {div}")

    except Exception as e:
        print(f"{sym} error {e}")
        continue

# --- 1. 更新同一張成績表 history.csv ---
csv_path = "history.csv"
try:
    new_df = pd.DataFrame([daily_row])
    if os.path.exists(csv_path):
        old_df = pd.read_csv(csv_path)
        # 避免同一日重複加
        old_df = old_df[old_df["日期"]!= daily_row["日期"]]
        hist = pd.concat([old_df, new_df], ignore_index=True)
    else:
        hist = new_df
    # 排返11個板塊次序
    cols = ["日期"] + ETFS
    hist = hist[[c for c in cols if c in hist.columns]]
    hist.to_csv(csv_path, index=False)
    print("history.csv 已更新")
except Exception as e:
    print(f"CSV error {e}")

# --- 2. WhatsApp 戰報 ---
final_report = f"📊 板塊雷達 {daily_row['日期']}\n" + "\n".join(report_lines)
final_report += "\n\n" + ("--- 信號 ---\n" + "\n".join(alerts) if alerts else "今日無背離/高換手信號")

print(final_report)

if CALLMEBOT_APIKEY:
    url = f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={urllib.parse.quote(final_report)}&apikey={CALLMEBOT_APIKEY}"
    try:
        requests.get(url, timeout=10)
    except:
        pass