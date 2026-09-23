import yfinance as yf, os, pandas as pd, requests, feedparser
from datetime import datetime

ETFS = {'XLE':'能源','XLF':'金融','XLK':'科技','XLV':'醫療','XLI':'工業','XLP':'必需消費','XLY':'可選消費','XLB':'原材料','XLU':'公用','XLRE':'地產','XLC':'通訊'}

def get_news(etf):
    try:
        url = f"https://news.google.com/rss/search?q={etf}+ETF&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        if feed.entries: return feed.entries[0].title[:100], feed.entries[0].link
    except: pass
    return "", ""

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

signals=[]; major=[]; minor=[]
for etf, name_cn in ETFS.items():
    try:
        t=yf.Ticker(etf)
        df_d=t.history(period="1y", interval="1d", auto_adjust=True)
        df_w=t.history(period="2y", interval="1wk", auto_adjust=True)
        df_m=t.history(period="10y", interval="1mo", auto_adjust=True)
        df_60m=t.history(period="3mo", interval="60m", auto_adjust=True)
        if len(df_d)<210: continue

        high_50=round(float(df_d['High'].iloc[-50:].max()),2)
        high_200=round(float(df_d['High'].iloc[-200:].max()),2)
        close=float(df_d['Close'].iloc[-1])
        dist_50=round((close/high_50-1)*100,2)
        dist_200=round((close/high_200-1)*100,2)

        # 爆量
        vol_today=float(df_d['Volume'].iloc[-1]); vol_yest=float(df_d['Volume'].iloc[-2])
        if vol_today/vol_yest >= 2.0:
            major.append(f"🔥 {etf} 爆量派貨 - {name_cn} {dist_50}%離50日高")

        sig="正常"
        if len(df_m)>=30:
            j=get_kdj(df_m).dropna()
            if len(j)>=5:
                div=find_div(df_m['Close'].loc[j.index], j)
                if div:
                    j_now=float(j.iloc[-1]); j_prev=float(j.iloc[-2])
                    if ("頂" in div and j_now<j_prev) or ("底" in div and j_now>j_prev):
                        sig=f"月線{div}"
                        major.append(f"🗓️ {etf} {sig} - {name_cn}見大{'頂' if '頂' in div else '底'} {dist_200}%離200日高")

        if len(df_w)>=60:
            div=find_div(df_w['Close'], get_dif(df_w['Close']))
            if div:
                sig=f"週線{div}" if sig=="正常" else sig
                major.append(f"⚠️ {etf} 週線{div} - {name_cn}見{'頂' if '頂' in div else '底'} {dist_50}%離50日高")

        if len(df_60m)>=60:
            df_4h=df_60m.resample("4h").agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
            if len(df_4h)>=60:
                div=find_div(df_4h['Close'], get_dif(df_4h['Close']))
                if div:
                    minor.append(f"{etf} 4H{div} - {name_cn} {dist_50}%離高")

        title, link = get_news(etf)
        signals.append({
            "etf":etf, "name_cn":name_cn,
            "high_50d":high_50, "high_200d":high_200,
            "dist_50d":dist_50, "dist_200d":dist_200,
            "signal":sig, "news_title":title, "news_url":link
        })
    except Exception as e:
        print(f"skip {etf} {e}")

# Supabase
try:
    from supabase import create_client
    sb=create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
    sb.table("signals").delete().neq("etf","XXX").execute()
    sb.table("signals").insert(signals).execute()
    print(f"Supabase OK {len(signals)}")
except Exception as e: print(e)

# ntfy - 返返V9.7格式：大級別 + (4H) 括號，有距離，冇現價
all_msgs = major + [f"({m})" for m in minor]
if all_msgs:
    message = f"雷達 V10.3 {datetime.now().strftime('%m-%d %H:%M')}\n\n" + "\n\n".join(all_msgs)
    requests.post("https://ntfy.sh/sector-radar-ivan117", data=message.encode('utf-8'), headers={"Title":"Sector Radar V10.3","Priority":"high"}, timeout=10)
    print("ntfy sent")
