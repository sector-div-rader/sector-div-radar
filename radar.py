import yfinance as yf
import pandas as pd
import os, requests, urllib.parse
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
    try:
        r=requests.get(url, timeout=20)
        print(f"WHATSAPP: {r.text[:300]}", flush=True)
    except Exception as e:
        print(e, flush=True)

def macd_dif(c): return c.ewm(span=12).mean() - c.ewm(span=26).mean()
def kdj_j(d):
    low=d['low'].rolling(9).min(); high=d['high'].rolling(9).max()
    rsv=(d['close']-low)/(high-low)*100
    k=rsv.ewm(com=2, adjust=False).mean(); dd=k.ewm(com=2, adjust=False).mean()
    return 3*k-2*dd
def div(close, ind, look=10):
    if len(close)<=look: return None
    if close.iloc[-1]>close.iloc[-look] and ind.iloc[-1]<ind.iloc[-look]: return "頂背離"
    if close.iloc[-1]<close.iloc[-look] and ind.iloc[-1]>ind.iloc[-look]: return "底背離"
    return None

today=datetime.now().strftime("%Y-%m-%d")
print(f"START {today}", flush=True)

# 批次下載，快10倍
batch_d = yf.download(ETFS, period="6mo", interval="1d", group_by='ticker', progress=False, auto_adjust=True, threads=True)
batch_w = yf.download(ETFS, period="2y", interval="1wk", group_by='ticker', progress=False, auto_adjust=True, threads=True)
batch_m = yf.download(ETFS, period="10y", interval="1mo", group_by='ticker', progress=False, auto_adjust=True, threads=True)
batch_h = yf.download(ETFS, period="1mo", interval="60m", group_by='ticker', progress=False, auto_adjust=True, threads=True)

def get_df(batch, etf):
    try:
        sub=batch[etf] if isinstance(batch.columns, pd.MultiIndex) else batch
        return pd.DataFrame({"close":sub['Close'],"vol":sub['Volume'],"high":sub['High'],"low":sub['Low']}).dropna()
    except: return None

report=[]; t_alert=[]; macd_alert=[]; kdj_alert=[]; daily_row={"日期":today}

for etf in ETFS:
    cn=SECTOR_CN[etf]
    d=get_df(batch_d, etf)
    if d is None or d.empty: continue
    pct=float(d['close'].iloc[-1]/d['close'].iloc[-2]-1)*100 if len(d)>=2 else 0
    daily_row[etf]=round(pct,2)
    report.append(f"{etf}({cn}): {pct:+.2f}%")

    # 1️⃣ 換手率概念：日量>5日均2.5倍
    if d['vol'].iloc[-1] > d['vol'].tail(5).mean()*2.5:
        t_alert.append(f"🔥 {etf}({cn}) 放量 {d['vol'].iloc[-1]/d['vol'].tail(5).mean():.1f}倍")

    # 2️⃣ MACD
    dv=div(d['close'], macd_dif(d['close']), 10)
    if dv: macd_alert.append(f"⚠️ {etf}({cn}) 日線{dv}")
    w=get_df(batch_w, etf)
    if w is not None and len(w)>10:
        dv=div(w['close'], macd_dif(w['close']), 10)
        if dv: macd_alert.append(f"⚠️ {etf}({cn}) 週線{dv}")
    h=get_df(batch_h, etf)
    if h is not None and len(h)>30:
        h4=h.resample("4h").agg({"close":"last","vol":"sum","high":"max","low":"min"}).dropna()
        if len(h4)>10:
            dv=div(h4['close'], macd_dif(h4['close']), 10)
            if dv: macd_alert.append(f"⚠️ {etf}({cn}) 4小時{dv}")
    # 3️⃣ KDJ月K
    m=get_df(batch_m, etf)
    if m is not None and len(m)>15:
        dv=div(m['close'], kdj_j(m), 10)
        if dv: kdj_alert.append(f"💎 {etf}({cn}) 月K J線{dv}")

# 存history
try:
    nd=pd.DataFrame([daily_row])
    hist=pd.read_csv("history.csv") if os.path.exists("history.csv") else pd.DataFrame()
    hist=pd.concat([hist, nd], ignore_index=True).drop_duplicates(subset=['日期'], keep='last') if not hist.empty else nd
    hist.to_csv("history.csv", index=False)
except: pass

# ****** 只發一條 ******
msg = f"📊 板塊雷達 {today}\n" + "\n".join(report)
msg += f"\n\n━━━━━━━━━━━━\n1️⃣ 換手率>5%\n{today}\n"
msg += "\n".join(t_alert) if t_alert else "無"

msg += f"\n\n━━━━━━━━━━━━\n2️⃣ MACD DIF背離\n{today}\n"
msg += "\n".join(macd_alert) if macd_alert else "無背離"

msg += f"\n\n━━━━━━━━━━━━\n3️⃣ KDJ J線背離(月K)\n{today}\n"
msg += "\n".join(kdj_alert) if kdj_alert else "無背離"

send(msg)
print("DONE", flush=True)