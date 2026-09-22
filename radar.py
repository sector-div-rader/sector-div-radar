import yfinance as yf, requests, os
TICKERS = ["XLK","XLF","XLE","XLV","XLI","XLP","XLY","XLB","XLU","XLRE","XLC","SMH","QQQ","SPY"]

def check(ticker, period, interval, label):
    df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
    if len(df) < 60: return None
    dif = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    recent = df.tail(40)
    lows = recent.nsmallest(2, 'Close')
    if len(lows)==2:
        p1_idx, p2_idx = lows.index[0], lows.index[1]
        if p1_idx < p2_idx: p1_idx, p2_idx = p2_idx, p1_idx
        if df.loc[p1_idx, 'Close'] < df.loc[p2_idx, 'Close'] and dif.loc[p1_idx] > dif.loc[p2_idx] and dif.loc[p1_idx] < 0:
            return f"{ticker} {label} 底背離"
    highs = recent.nlargest(2, 'Close')
    if len(highs)==2:
        h1_idx, h2_idx = highs.index[0], highs.index[1]
        if h1_idx < h2_idx: h1_idx, h2_idx = h2_idx, h1_idx
        if df.loc[h1_idx, 'Close'] > df.loc[h2_idx, 'Close'] and dif.loc[h1_idx] < dif.loc[h2_idx] and dif.loc[h1_idx] > 0:
            return f"{ticker} {label} 頂背離"
    return None

msgs=[]
for tk in TICKERS:
    r1 = check(tk, "1y", "1wk", "週線")
    if r1: msgs.append(r1)
    r2 = check(tk, "60d", "4h", "4小時")
    if r2: msgs.append(r2)

if msgs:
    text = "美股板塊DIF背離:\n" + "\n".join(msgs)
    phone = os.getenv("PHONE")
    apikey = os.getenv("APIKEY")
    url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={requests.utils.quote(text)}&apikey={apikey}"
    requests.get(url)