import yfinance as yf
import pandas as pd
import os
import requests
import urllib.parse
from datetime import datetime

SECTOR_CN = {
    "XLB": "原材料",
    "XLC": "通訊服務",
    "XLE": "能源",
    "XLF": "金融",
    "XLI": "工業",
    "XLK": "科技",
    "XLP": "必需消費",
    "XLRE": "房地產",
    "XLU": "公用事業",
    "XLV": "醫療保健",
    "XLY": "非必需消費",
    "XLG": "大型增長"
}

# 12個板塊 (11個SPDR + XLG)
ETFS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY", "XLG"]

PHONE = "85263306575"
CALLMEBOT_APIKEY = os.getenv("CALLMEBOT_APIKEY")

report_lines = []
alerts = []
daily_row = {}
today_str = datetime.now().strftime("%Y-%m-%d")
daily_row['日期'] = today_str

for etf in ETFS:
    try:
        df = yf.download(etf, period="6mo", interval="1d", progress=False, auto_adjust=True)
        if df.empty: continue
        close = df['Close'].iloc[:,0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        dif = ema12 - ema26
        pct = float((close.iloc[-1] / close.iloc[-2] - 1) * 100) if len(close) >= 2 else 0.0
        daily_row[etf] = round(pct, 2)
        cn = SECTOR_CN.get(etf, etf)
        report_lines.append(f"{etf}({cn}): {pct:+.2f}%")

        if len(close) > 10:
            if close.iloc[-1] > close.iloc[-10] and dif.iloc[-1] < dif.iloc[-10]:
                alerts.append(f"⚠️ {etf}({cn}) 頂背離")
            if close.iloc[-1] < close.iloc[-10] and dif.iloc[-1] > dif.iloc[-10]:
                alerts.append(f"⚠️ {etf}({cn}) 底背離")
    except Exception as e:
        print(f"{etf} error {e}")

# history.csv
try:
    new_df = pd.DataFrame([daily_row])
    hist = pd.read_csv("history.csv") if os.path.exists("history.csv") else pd.DataFrame()
    hist = pd.concat([hist, new_df], ignore_index=True).drop_duplicates(subset=['日期'], keep='last') if not hist.empty else new_df
    hist.to_csv("history.csv", index=False)
except Exception as e:
    print(f"CSV error {e}")

final_report = f"📊 板塊雷達 {today_str}\n" + "\n".join(report_lines)
final_report += "\n\n-- 信號 --\n" + ("\n".join(alerts) if alerts else "今日無背離")

print(final_report)

if CALLMEBOT_APIKEY:
    url = f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={urllib.parse.quote(final_report)}&apikey={CALLMEBOT_APIKEY}"
    r = requests.get(url, timeout=20)
    print(f"WhatsApp: {r.text}")