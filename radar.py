import os, requests, yfinance as yf
import pandas as pd

ETFS = ["XLB","XLE","XLF","XLI","XLK","XLP","XLU","XLV","XLY","XLC","XLRE"]
PHONE = os.getenv("PHONE")
APIKEY = os.getenv("APIKEY")

def get_dif(df):
    close = df['Close']
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    return ema12 - ema26

def check_divergence(symbol):
    msgs=[]
    for tf, interval in [("W","1wk"),("4H","1h")]:
        try:
            df = yf.download(symbol, period="1y", interval=interval, auto_adjust=True, progress=False)
            if len(df) < 60: continue
            if tf=="4H":
                df = df.resample("4H").last().dropna()
                if len(df) < 60: continue
            price = df['Close']
            dif = get_dif(df)
            # 簡單背離：近20根，價格新低但DIF冇新低 = 底背離，新高但DIF冇新高 = 頂背離
            recent = 20
            p_low = price[-recent:].min()
            p_high = price[-recent:].max()
            d_low = dif[-recent:].min()
            d_high = dif[-recent:].max()
            
            if price.iloc[-1] <= p_low*1.01 and dif.iloc[-1] > d_low*1.05:
                msgs.append(f"{symbol} {tf} 底背離")
            if price.iloc[-1] >= p_high*0.99 and dif.iloc[-1] < d_high*0.95:
                msgs.append(f"{symbol} {tf} 頂背離")
        except Exception as e:
            continue
    return msgs

all_msgs=[]
for etf in ETFS:
    all_msgs.extend(check_divergence(etf))

if all_msgs and PHONE and APIKEY:
    text = "美股板塊DIF背離:\n" + "\n".join(all_msgs)
    requests.post("https://textbelt.com/text", data={"phone":PHONE,"message":text,"key":APIKEY})
    print(text)
else:
    print("No divergence: " + ",".join(all_msgs))
