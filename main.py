import yfinance as yf, os, pandas as pd, requests
from datetime import datetime

SECTORS = {
    'LIST2025':  {'name':'石油天然氣', 'price_ticker':'^SP500-10', 'vol_etf':'XLE',  'sticker':'🛢️'},
    'LIST2008':  {'name':'銀行',       'price_ticker':'^SP500-40', 'vol_etf':'XLF',  'sticker':'🏦'},
    'LIST2016':  {'name':'半導體設備', 'price_ticker':'^SOX',       'vol_etf':'SMH',  'sticker':'💾'},
    'LIST2110':  {'name':'生物技術',   'price_ticker':'^SP500-35', 'vol_etf':'XLV',  'sticker':'🧬'},
    'LIST2089':  {'name':'航太國防',   'price_ticker':'^SP500-20', 'vol_etf':'XLI',  'sticker':'✈️'},
    'LIST2145':  {'name':'必需消費',   'price_ticker':'^SP500-30', 'vol_etf':'XLP',  'sticker':'🛒'},
    'LIST2080':  {'name':'汽車及零件', 'price_ticker':'^SP500-25', 'vol_etf':'XLY',  'sticker':'🚗'},
    'LIST2035':  {'name':'化工',       'price_ticker':'^SP500-15', 'vol_etf':'XLB',  'sticker':'🧪'},
    'LIST2260':  {'name':'公用事業',   'price_ticker':'^SP500-55', 'vol_etf':'XLU',  'sticker':'💡'},
    'LIST2250':  {'name':'地產信託',   'price_ticker':'^SP500-60', 'vol_etf':'XLRE', 'sticker':'🏠'},
    'LIST2065':  {'name':'電信服務',   'price_ticker':'^SP500-50', 'vol_etf':'XLC',  'sticker':'📡'},
    'LIST23925': {'name':'存儲概念',   'price_ticker':'^SOX',       'vol_etf':'XLK',  'sticker':'💿'},
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

# V10.5 放寬：0.98->0.95 / 1.02->1.05
def find_div(p,i):
    if len(p)<30: return None
    p=p.iloc[-60:]; i=i.iloc[-60:]
    s=p.iloc[:-5].iloc[-20:]
    if len(s)<5: return None
    curr_p=float(p.iloc[-1]); curr_i=float(i.iloc[-1])
    peak_p=float(p.loc[s.idxmax()]); trough_p=float(p.loc[s.idxmin()])
    peak_i=float(i.loc[s.idxmax()]); trough_i=float(i.loc[s.idxmin()])
    if curr_p>=peak_p*0.95 and curr_i<peak_i*0.97: return "頂背離"
    if curr_p<=trough_p*1.05 and curr_i>trough_i*1.03: return "底背離"
    return None

def get_hist(ticker, period, interval):
    try: return yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
    except: return pd.DataFrame()

signals=[]; major=[]; minor=[]

for list_code, info in SECTORS.items():
    try:
        df_d_p = get_hist(info['price_ticker'], "1y", "1d")
        df_w_p = get_hist(info['price_ticker'], "2y", "1wk")
        df_m_p = get_hist(info['price_ticker'], "10y", "1mo")
        df_60m_p = get_hist(info['price_ticker'], "3mo", "60m")
        df_d_v = get_hist(info['vol_etf'], "1y", "1d")
        if len(df_d_p)<210 or len(df_d_v)<2: continue
        
        high_50=round(float(df_d_p['High'].iloc[-50:].max()),2)
        high_200=round(float(df_d_p['High'].iloc[-200:].max()),2)
        close=float(df_d_p['Close'].iloc[-1])
        dist_50=round((close/high_50-1)*100,2)
        dist_200=round((close/high_200-1)*100,2)

        # V10.5 新增：逼近頂底提示
        if dist_50 >= -2.0:
            major.append(f"🔝 {info['sticker']} {list_code} 逼近50日頂 - {info['name']} 僅{dist_50}%離高")
        if dist_50 <= -15.0:
            major.append(f"🔻 {info['sticker']} {list_code} 遠離高位 - {info['name']} {dist_50}%離50日高 可能超賣")

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
                if div: minor.append(f"{info['sticker']} {list_code} 4H{div} - {info['name']} {dist_50}%離高")

        signals.append({"etf":list_code, "name_cn":info['name'], "price_ticker":info['price_ticker'], "high_50d":high_50, "high_200d":high_200, "dist_50d":dist_50, "dist_200d":dist_200, "signal":sig})
    except Exception as e:
        print(f"skip {list_code} {e}")

for fut_code, info in FUTURES.items():
    try:
        df_w = get_hist(fut_code, "2y", "1wk"); df_m = get_hist(fut_code, "10y", "1mo")
        if len(df_m)>=30:
            j=get_kdj(df_m).dropna()
            if len(j)>=5:
                div=find_div(df_m['Close'].loc[j.index], j)
                if div: major.append(f"🗓️ {info['sticker']} {fut_code} 月線{div} - {info['name']}")
        if len(df_w)>=60:
            div=find_div(df_w['Close'], get_dif(df_w['Close']))
            if div: major.append(f"⚠️ {info['sticker']} {fut_code} 週線{div} - {info['name']}")
    except Exception as e: print(f"skip {fut_code} {e}")

try:
    from supabase import create_client
    sb=create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
    sb.table("signals").delete().neq("etf","XXX").execute()
    sb.table("signals").insert(signals).execute()
    print(f"Supabase OK {len(signals)}")
except Exception as e: print(e)

all_msgs = major + [f"({m})" for m in minor]
if all_msgs:
    message = f"Radar V10.5 {datetime.now().strftime('%m-%d %H:%M')}\n\n" + "\n\n".join(all_msgs)
    requests.post("https://ntfy.sh/sector-radar-ivan117", data=message.encode('utf-8'), headers={"Title": "Sector Radar V10.5", "Priority":"high"}, timeout=10)
    print("ntfy sent")
else:
    # 乜都冇都報一報，等你知佢有跑
    message = f"Radar V10.5 {datetime.now().strftime('%m-%d %H:%M')}\n\n今日無背離，全部板塊正常"
    requests.post("https://ntfy.sh/sector-radar-ivan117", data=message.encode('utf-8'), headers={"Title": "Sector Radar V10.5 - No Signal", "Priority":"low"}, timeout=10)