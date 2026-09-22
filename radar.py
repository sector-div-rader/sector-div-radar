import os, requests, yfinance as yf
from urllib.parse import quote

ETFS = ["XLB","XLE","XLF","XLI","XLK","XLP","XLU","XLV","XLY","XLC","XLRE"]
PHONE = os.getenv("PHONE")
APIKEY = os.getenv("APIKEY")

def get_dif(df):
    c = df['Close']
    return c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()

def check_div(symbol):
    msgs=[]
    for label, interval, period in [("W","1wk","1y"), ("4H","1h","3mo")]:
        try:
            df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)
            if len(df) < 50: continue
            if label=="4H":
                df = df.resample("4H").last().dropna()
                if len(df) < 50: continue
            price = df['Close']
            dif = get_dif(df)
            r=20
            p_low = price[-r:].min().item()
            p_high = price[-r:].max().item()
            d_low = dif[-r:].min().item()
            d_high = dif[-r:].max().item()
            last_p = price.iloc[-1].item()
            last_d = dif.iloc[-1].item()
            if last_p <= p_low*1.01 and last_d > d_low*1.05:
                msgs.append(f"{symbol} {label} 底背離")
            if last_p >= p_high*0.99 and last_d < d_high*0.95:
                msgs.append(f"{symbol} {label} 頂背離")
        except: continue
    return msgs

all_msgs=[]
for etf in ETFS:
    all_msgs.extend(check_div(etf))

# 強制測試一次先
test_mode = True
if test_mode:
    text = "測試：雷達上線成功！✅ sector-div-radar Success\n你香港號 6330 6575 收到即係WhatsApp正常"
else:
    if not all_msgs:
        text = ""
    else:
        text = "美股板塊DIF背離:\n" + "\n".join(all_msgs)

print("MSG:", text)
if text and PHONE and APIKEY:
    url = f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={quote(text)}&apikey={APIKEY}"
    r = requests.get(url, timeout=20)
    print("CALLMEBOT:", r.text)
