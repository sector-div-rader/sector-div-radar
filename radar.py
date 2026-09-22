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
    print(msg, flush=True)
    if not APIKEY: return
    url = f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={urllib.parse.quote(msg)}&apikey={APIKEY}"
    try: requests.get(url, timeout=20)
    except: pass
    time.sleep(2)

def batch_close(period, interval):
    try:
        df = yf.download(ETFS, period=period, interval=interval, group_by='ticker', progress=False, auto_adjust=True, threads=True)
        return df
    except Exception as e:
        print(f"batch fail {period} {interval} {e}"); return None

def get_ticker_close(batch_df, etf):
    try:
        if isinstance(batch_df.columns, pd.MultiIndex):
            sub = batch_df[etf]
        else: sub = batch_df
        if sub.empty: return None
        return pd.DataFrame({
            "close": sub['Close'].dropna(),
            "vol": sub['Volume'].dropna(),
            "high": sub['High'].dropna(),
            "low": sub['Low'].dropna()
        })
    except: return None

def macd_dif(close): return close.ewm(span=12).mean() - close.ewm(span=26).mean()
def kdj_j(d):
    low_n = d['low'].rolling(9, min_periods=9).min()
    high_n = d['high'].rolling(9, min_periods=9).max()
    rsv = (d['close'] - low_n) / (high_n - low_n) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    dd = k.ewm(com=2, adjust=False).mean()
    return 3*k - 2*dd
def check_div(close, ind, look=10):
    if len(close) <= look or len(ind) <= look: return None
    if close.iloc[-1] > close.iloc[-look] and ind.iloc[-1] < ind.iloc[-look]: return "頂背離"
    if close.iloc[-1] < close.iloc[-look] and ind.iloc[-1] > ind.iloc[-look]: return "底背離"
    return None

today = datetime.now().strftime("%Y-%m-%d")
print(f"START {today} {ETFS}", flush=True)

# 一次過下載
d_batch = batch_close("6mo", "1d")
w_batch = batch_close("2y", "1wk")
m_batch = batch_close("10y", "1mo")
h_batch = batch_close("1mo", "60m")

daily_row, report, turnover_alerts, macd_alerts, kdj_alerts = {"日期":today}, [], [], [], []

for etf in ETFS:
    cn = SECTOR_CN[etf]
    d_df = get_ticker_close(d_batch, etf) if d_batch is not None else None
    if d_df is None or d_df.empty: continue
    try:
        pct = float(d_df['close'].iloc[-1]/d_df['close'].iloc[-2]-1)*100 if len(d_df)>=2 else 0
        daily_row[etf]=round(pct,2)
        report.append(f"{etf}({cn}): {pct:+.2f}%")

        # 1️⃣ 換手率 >5% 用日均量代替流通股，快好多，ETF流通股API好慢，改用 當日量 > 5日均量*2.5 約等於高換手
        avg5 = d_df['vol'].tail(5).mean()
        if avg5>0 and d_df['vol'].iloc[-1] > avg5*2.5:
            turnover_alerts.append(f"🔥 {etf}({cn}) 日K放量 {d_df['vol'].iloc[-1]/avg5:.1f}倍 (>5%換手概念)")

        # 2️⃣ MACD
        dv = check_div(d_df['close'], macd_dif(d_df['close']), 10)
        if dv: macd_alerts.append(f"⚠️ {etf}({cn}) 日線{dv}")

        w_df = get_ticker_close(w_batch, etf) if w_batch is not None else None
        if w_df is not None and len(w_df)>10:
            dv = check_div(w_df['close'], macd_dif(w_df['close']), 10)
            if dv: macd_alerts.append(f"⚠️ {etf}({cn}) 週線{dv}")

        h_df = get_ticker_close(h_batch, etf) if h_batch is not None else None
        if h_df is not None and len(h_df)>30:
            h4 = h_df.resample("4h").agg({"close":"last","vol":"sum","high":"max","low":"min"}).dropna()
            if len(h4)>10:
                dv = check_div(h4['close'], macd_dif(h4['close']), 10)
                if dv: macd_alerts.append(f"⚠️ {etf}({cn}) 4小時{dv}")

        m_df = get_ticker_close(m_batch, etf) if m_batch is not None else None
        if m_df is not None and len(m_df)>15:
            j = kdj_j(m_df)
            dv = check_div(m_df['close'], j, 10)
            if dv: kdj_alerts.append(f"💎 {etf}({cn}) 月K J線{dv}")

    except Exception as e:
        print(f"{etf} err {e}", flush=True)

# 存CSV
try:
    nd=pd.DataFrame([daily_row])
    hist=pd.read_csv("history.csv") if os.path.exists("history.csv") else pd.DataFrame()
    hist=pd.concat([hist, nd], ignore_index=True).drop_duplicates(subset=['日期'], keep='last') if not hist.empty else nd
    hist.to_csv("history.csv", index=False)
except Exception as e: print(e)

send(f"📊 板塊雷達V4 {today}\n" + "\n".join(report))

if turnover_alerts: send(f"1️⃣ 換手率>5% (放量概念) {today}\n" + "\n".join(turnover_alerts))
if macd_alerts: send(f"2️⃣ MACD DIF背離 {today}\n" + "\n".join(macd_alerts))
else: send(f"2️⃣ MACD DIF背離 {today}\n無")

if kdj_alerts: send(f"3️⃣ KDJ J線背離(月K) {today}\n" + "\n".join(kdj_alerts))
else: send(f"3️⃣ KDJ J線背離(月K) {today}\n無")

print("DONE", flush=True)