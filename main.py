import yfinance as yf, os, pandas as pd, requests
from datetime import datetime

# ===== V10.4 LIST版 (FIXED) =====
SECTORS = {
    'LIST2025':  {'name':'石油天然氣', 'vol_etf':'XLE',  'sticker':'🛢️'},
    'LIST2008':  {'name':'銀行',       'vol_etf':'XLF',  'sticker':'🏦'},
    'LIST2016':  {'name':'半導體設備', 'vol_etf':'SMH',  'sticker':'💾'},
    'LIST2110':  {'name':'生物技術',   'vol_etf':'XLV',  'sticker':'🧬'},
    'LIST2089':  {'name':'航太國防',   'vol_etf':'XLI',  'sticker':'✈️'},
    'LIST2145':  {'name':'必需消費',   'vol_etf':'XLP',  'sticker':'🛒'},
    'LIST2080':  {'name':'汽車及零件', 'vol_etf':'XLY',  'sticker':'🚗'},
    'LIST2035':  {'name':'化工',       'vol_etf':'XLB',  'sticker':'🧪'},
    'LIST2260':  {'name':'公用事業',   'vol_etf':'XLU',  'sticker':'💡'},
    'LIST2250':  {'name':'地產信託',   'vol_etf':'XLRE', 'sticker':'🏠'},
    'LIST2065':  {'name':'電信服務',   'vol_etf':'XLC',  'sticker':'📡'},
    'LIST23925': {'name':'存儲概念',   'vol_etf':'XLK',  'sticker':'💿'},
}

FUTURES = {
    'GC=F':     {'name':'黃金期貨', 'sticker':'🥇'},
    'DX-Y.NYB': {'name':'美元指數', 'sticker':'💵'},
    'CL=F':     {'name':'石油期貨', 'sticker':'⛽'},
}

def get_dif(c): return c.ewm(span=5, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
def get_kdj(df):
    low=df['Low'].rolling(9).min(); high=df['High'].rolling(9).max()
    rsv=(df['Close']-low)/(high-low)*100
    k=rsv.ewm(com=2, adjust=False).mean(); d=k.ewm(com=2, adjust=False).mean()
    return 3*k-2*d

def find_div(p,i):
    if len(p)<30: return None
    p=p.iloc[-60:]; i=i.iloc[-60:]
    s=p.iloc[:-5].iloc[-20:]
    if len(s)<5: return None
    curr_p=float(p.iloc[-1]); curr_i=float(i.iloc[-1])
    peak_p=float(p.loc[s.idxmax()]); trough_p=float(p.loc[s.idxmin()])
    peak_i=float(i.loc[s.idxmax()]); trough_i=float(i.loc[s.idxmin()])
    if curr_p>=peak_p*0.98 and curr_i<peak_i*0.97: return "頂背離"
    if curr_p<=trough_p*1.02 and curr_i>trough_i*1.03: return "底背離"
    return None

def get_hist(ticker, period, interval):
    try:
        t_str = ticker if "." in ticker or "=" in ticker or "-" in ticker else f"{ticker}.US"
        return yf.Ticker(t_str).history(period=period, interval=interval, auto_adjust=True)
    except: return pd.DataFrame()

signals=[]; major=[]; minor=[]

# 1. 板塊 LIST - 背離睇LIST，爆量睇ETF
for list_code, info in SECTORS.items():
    try:
        df_d_p = get_hist(list_code, "1y", "1d")
        df_w_p = get_hist(list_code, "2y", "1wk")
        df_m_p = get_hist(list_code, "10y", "1mo")
        df_60m_p = get_hist(list_code, "3mo", "60m")
        df_d_v = get_hist(info['vol_etf'], "1y", "1d")
        if len(df_d_p)<210 or len(df_d_v)<2: continue

        high_50=round(float(df_d_p['High'].iloc[-50:].max()),2)
        high_200=round(float(df_d_p['High'].iloc[-200:].max()),2)
        close=float(df_d_p['Close'].iloc[-1])
        dist_50=round((close/high_50-1)*100,2)
        dist_200=round((close/high_200-1)*100,2)

        vol_today=float(df_d_v['Volume'].iloc[-1]); vol_yest=float(df_d_v['Volume'].iloc[-2])
        if vol_today/vol_yest >= 2.0:
            major.append(f"🔥 {info['sticker']} {list_code} 爆量 - {info['name']} ({info['vol_etf']}放量) {dist_50}%離50日高")

        sig="正常"
        if len(df_m_p)>=30:
            j=get_kdj(df_m_p).dropna()
            if len(j)>=5:
                div=find_div(df_m_p['Close'].loc[j.index], j)
                if div:
                    j_now=float(j.iloc[-1]); j_prev=float(j.iloc[-2])
                    if ("頂" in div and j_now<j_prev) or ("底" in div and j_now>j_prev):
                        sig=f"月線{div}"
                        major.append(f"🗓️ {info['sticker']} {list_code} {sig} - {info['name']}見大{'頂' if '頂' in div else '底'} {dist_200}%離200日高")

        if len(df_w_p)>=60:
            div=find_div(df_w_p['Close'], get_dif(df_w_p['Close']))
            if div:
                if sig=="正常": sig=f"週線{div}"
                major.append(f"⚠️ {info['sticker']} {list_code} 週線{div} - {info['name']}見{'頂' if '頂' in div else '底'} {dist_50}%離50日高")

        if len(df_60m_p)>=60:
            df_4h=df_60m_p.resample("4h").agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
            if len(df_4h)>=60:
                div=find_div(df_4h['Close'], get_dif(df_4h['Close']))
                if div:
                    minor.append(f"{info['sticker']} {list_code} 4H{div} - {info['name']} {dist_50}%離高")

        signals.append({"etf":list_code, "name_cn":info['name'], "high_50d":high_50, "high_200d":high_200, "dist_50d":dist_50, "dist_200d":dist_200, "signal":sig})
    except Exception as e:
        print(f"skip {list_code} {e}")

# 2. 期貨/美元指數
for fut_code, info in FUTURES.items():
    try:
        df_w = get_hist(fut_code, "2y", "1wk")
        df_m = get_hist(fut_code, "10y", "1mo")
        if len(df_m)>=30:
            j=get_kdj(df_m).dropna()
            if len(j)>=5:
                div=find_div(df_m['Close'].loc[j.index], j)
                if div: major.append(f"🗓️ {info['sticker']} {fut_code} 月線{div} - {info['name']}")
        if len(df_w)>=60:
            div=find_div(df_w['Close'], get_dif(df_w['Close']))
            if div: major.append(f"⚠️ {info['sticker']} {fut_code} 週線{div} - {info['name']}")
    except Exception as e:
        print(f"skip {fut_code} {e}")

# Supabase
try:
    from supabase import create_client
    sb=create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
    sb.table("signals").delete().neq("etf","XXX").execute()
    sb.table("signals").insert(signals).execute()
    print(f"Supabase OK {len(signals)}")
except Exception as e: print(e)

# ntfy - Title唔可以有中文，已經FIX
all_msgs = major + [f"({m})" for m in minor]
if all_msgs:
    message = f"雷達 V10.4 {datetime.now().strftime('%m-%d %H:%M')}\n\n" + "\n\n".join(all_msgs)
    requests.post(
        "https://ntfy.sh/sector-radar-ivan117", 
        data=message.encode('utf-8'), 
        headers={"Title": "Sector Radar V10.4", "Priority":"high"},
        timeout=10
    )
    print("ntfy sent")