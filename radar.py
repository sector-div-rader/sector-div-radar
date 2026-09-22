import yfinance as yf, pandas as pd, numpy as np, requests, os, json, matplotlib.pyplot as plt
from datetime import datetime

ETFS = ["XLB","XLE","XLF","XLI","XLK","XLP","XLU","XLV","XLY","XLG","XLC"]
TEST_MODE = False

# Google Sheet 設定 (第4步教你開)
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

def get_dif(close, f=12, s=26):
    ema_f = close.ewm(span=f, adjust=False).mean()
    ema_s = close.ewm(span=s, adjust=False).mean()
    return ema_f - ema_s

def check_divergence(symbol, interval, period):
    try:
        df = yf.Ticker(symbol).history(period=period, interval=interval).dropna()
        if len(df) < 60: return None
        close = df['Close']
        dif = get_dif(close)
        # 簡化背離判斷: 價格新低但DIF抬高 = 底背離
        price_low_now = close.iloc[-5:].min()
        price_low_prev = close.iloc[-30:-5].min()
        dif_low_now = dif.iloc[-5:].min()
        dif_low_prev = dif.iloc[-30:-5].min()
        
        msg = None
        if price_low_now < price_low_prev and dif_low_now > dif_low_prev:
            msg = f"【底背離】{symbol} {interval}K線 價格新低但DIF抬頭 (看漲)"
        elif close.iloc[-5:].max() > close.iloc[-30:-5].max() and dif.iloc[-5:].max() < dif.iloc[-30:-5].max():
            msg = f"【頂背離】{symbol} {interval}K線 價格新高但DIF走弱 (看跌)"
        
        if msg:
            # 畫圖
            plt.figure()
            plt.plot(close[-50:]); plt.plot(dif[-50:])
            plt.title(f"{symbol} {interval} Divergence")
            plt.savefig(f"{symbol}_{interval}.png")
        return msg
    except: return None

alerts = []
for sym in ETFS:
    for itv, per in [("1wk","1y"), ("4h","3mo")]: # 周線同4H
        r = check_divergence(sym, itv, per)
        if r: alerts.append(r)

# KDJ J線 月K背離
def calc_kdj(close, n=9):
    low = close.rolling(n).min(); high = close.rolling(n).max()
    rsv = (close - low)/(high-low)*100
    k = rsv.ewm(com=2).mean(); d = k.ewm(com=2).mean(); j = 3*k - 2*d
    return j

for sym in ETFS:
    try:
        df = yf.Ticker(sym).history(period="5y", interval="1mo")
        j = calc_kdj(df['Close'])
        # J線背離判斷同上
        if j.iloc[-1] < 20 and j.iloc[-1] > j.iloc[-6:-1].min() and df['Close'].iloc[-1] < df['Close'].iloc[-6:-1].min():
            alerts.append(f"【月K KDJ-J底背離】{sym} 月線 J線低位抬頭")
        if j.iloc[-1] > 80 and j.iloc[-1] < j.iloc[-6:-1].max() and df['Close'].iloc[-1] > df['Close'].iloc[-6:-1].max():
            alerts.append(f"【月K KDJ-J頂背離】{sym} 月線 J線高位回落")
    except: pass

# 每日戰報
report = f"📊 每日戰報 {datetime.now().strftime('%Y-%m-%d')}\n"
for sym in ETFS:
    chg = yf.Ticker(sym).history(period="2d")['Close'].pct_change().iloc[-1]*100
    report += f"{sym}: {chg:.2f}%\n"

# 發送
apikey = os.getenv("CALLMEBOT_APIKEY")
phone = "85263306575"
all_msg = report + "\n" + ("\n".join(alerts) if alerts else "今日無背離")
if not TEST_MODE:
    requests.get(f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={requests.utils.quote(all_msg)}&apikey={apikey}")

print(all_msg)