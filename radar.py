import yfinance as yf
import pandas as pd
import os, requests, urllib.parse, time
from datetime import datetime

SECTOR_CN = {
    "XLB":"原材料","XLC":"通訊服務","XLE":"能源","XLF":"金融","XLI":"工業",
    "XLK":"科技","XLP":"必需消費","XLRE":"房地產","XLU":"公用事業",
    "XLV":"醫療保健","XLY":"非必需消費","XLG":"大型增長"
}
ETFS = list(SECTOR_CN.keys())
PHONE = "85263306575"
APIKEY = os.getenv("CALLMEBOT_APIKEY")

def send(msg):
    if not APIKEY: print(msg); return
    url = f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={urllib.parse.quote(msg)}&apikey={APIKEY}"
    requests.get(url, timeout=20)
    time.sleep(3) # 分開發，唔好被ban

def get_df(etf, period, interval):
    df = yf.download(etf, period=period, interval=interval, progress=False, auto_adjust=True)
    if df.empty: return None
    # 兼容處理
    def col(name):
        c = df[name]
        return c.iloc[:,0] if isinstance(c, pd.DataFrame) else c
    return pd.DataFrame({"close":col('Close'),"vol":col('Volume'),"high":col('High'),"low":col('Low')})

def macd_dif(close): return close.ewm(span=12).mean() - close.ewm(span=26).mean()

def kdj_j(df):
    low_n = df['low'].rolling(9, min_periods=9).min()
    high_n = df['high'].rolling(9, min_periods=9).max()
    rsv = (df['close'] - low_n) / (high_n - low_n) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    return 3*k - 2*d

def check_div(close, ind, look=10):
    if len(close) <= look: return None
    if close.iloc[-1] > close.iloc[-look] and ind.iloc[-1] < ind.iloc[-look]: return "頂背離"
    if close.iloc[-1] < close.iloc[-look] and ind.iloc[-1] > ind.iloc[-look]: return "底背離"
    return None

today = datetime.now().strftime("%Y-%m-%d")
daily_row, report_lines = {"日期":today}, []
turnover_alerts, macd_alerts, kdj_alerts = [], [], []

for etf in ETFS:
    cn = SECTOR_CN[etf]
    try:
        d_df = get_df(etf, "6mo", "1d")
        if d_df is None: continue
        pct = float(d_df['close'].iloc[-1]/d_df['close'].iloc[-2]-1)*100 if len(d_df)>=2 else 0
        daily_row[etf]=round(pct,2)
        report_lines.append(f"{etf}({cn}): {pct:+.2f}%")

        # 1️⃣ 換手率
        try:
            shares = yf.Ticker(etf).info.get("sharesOutstanding",0)
            if shares:
                t = float(d_df['vol'].iloc[-1]/shares*100)
                if t>5: turnover_alerts.append(f"🔥 {etf}({cn}) 日K換手 {t:.2f}%")
        except: pass

        # 2️⃣ MACD DIF 多週期
        dv = check_div(d_df['close'], macd_dif(d_df['close']), 10)
        if dv: macd_alerts.append(f"⚠️ {etf}({cn}) 日線{dv}")

        w_df = get_df(etf, "2y", "1wk")
        if w_df is not None and len(w_df)>10:
            dv = check_div(w_df['close'], macd_dif(w_df['close']), 10)
            if dv: macd_alerts.append(f"⚠️ {etf}({cn}) 週線{dv}")

        h_df = get_df(etf, "1mo", "60m")
        if h_df is not None and len(h_df)>30:
            h4 = h_df.resample("4h").agg({"close":"last","vol":"sum","high":"max","low":"min"}).dropna()
            if len(h4)>10:
                dv = check_div(h4['close'], macd_dif(h4['close']), 10)
                if dv: macd_alerts.append(f"⚠️ {etf}({cn}) 4小時{dv}")

        # 3️⃣ KDJ J 月K
        m_df = get_df(etf, "10y", "1mo")
        if m_df is not None and len(m_df)>15:
            j = kdj_j(m_df)
            dv = check_div(m_df['close'], j, 10)
            if dv: kdj_alerts.append(f"💎 {etf}({cn}) 月K J線{dv}")

    except Exception as e:
        print(f"{etf} err {e}")

# 存CSV
try:
    nd=pd.DataFrame([daily_row])
    hist=pd.read_csv("history.csv") if os.path.exists("history.csv") else pd.DataFrame()
    hist=pd.concat([hist, nd], ignore_index=True).drop_duplicates(subset=['日期'], keep='last') if not hist.empty else nd
    hist.to_csv("history.csv", index=False)
except: pass

# 每日大盤一條
base = f"📊 板塊雷達 {today}\n" + "\n".join(report_lines)
send(base)

# 獨立3條 - 有先發，無唔發
if turnover_alerts:
    send(f"1️⃣ 換手率>5% (日K)\n{today}\n" + "\n".join(turnover_alerts))

if macd_alerts:
    send(f"2️⃣ MACD DIF背離\n{today}\n" + "\n".join(macd_alerts))
else:
    send(f"2️⃣ MACD DIF背離\n{today}\n無背離")

if kdj_alerts:
    send(f"3️⃣ KDJ J線背離 (月K)\n{today}\n" + "\n".join(kdj_alerts))
else:
    send(f"3️⃣ KDJ J線背離 (月K)\n{today}\n無背離")