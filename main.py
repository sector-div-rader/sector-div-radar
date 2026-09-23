import yfinance as yf, os, pandas as pd, requests
from datetime import datetime

ETFS = {'XLE':'能源','XLF':'金融','XLK':'科技','XLV':'醫療','XLI':'工業','XLP':'必需消費','XLY':'可選消費','XLB':'原材料','XLU':'公用','XLRE':'地產','XLC':'通訊'}

def get_dif(close, fast=5, slow=26):
    return close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()

def get_kdj(df, n=9):
    low = df['Low'].rolling(n).min()
    high = df['High'].rolling(n).max()
    rsv = (df['Close'] - low) / (high - low) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    return 3*k - 2*d

def find_div(price, ind, lookback=60):
    if len(price) < 30: return None
    p = price.iloc[-lookback:].copy()
    i = ind.iloc[-lookback:].copy()
    curr_p = float(p.iloc[-1]); curr_i = float(i.iloc[-1])
    if pd.isna(curr_p) or pd.isna(curr_i): return None
    search = p.iloc[:-5].iloc[-20:]
    if len(search) < 5: return None
    peak_p = float(p.loc[search.idxmax()]); trough_p = float(p.loc[search.idxmin()])
    peak_i = float(i.loc[search.idxmax()]); trough_i = float(i.loc[search.idxmin()])
    if curr_p >= peak_p * 0.98 and curr_i < peak_i * 0.97:
        return "頂背離"
    if curr_p <= trough_p * 1.02 and curr_i > trough_i * 1.03:
        return "底背離"
    return None

signals=[]; major=[]; minor=[]

for etf, name_cn in ETFS.items():
    try:
        t = yf.Ticker(etf)
        df_d = t.history(period="6mo", interval="1d", auto_adjust=True)
        df_w = t.history(period="2y", interval="1wk", auto_adjust=True)
        df_m = t.history(period="10y", interval="1mo", auto_adjust=True)
        df_60m = t.history(period="3mo", interval="60m", auto_adjust=True)
        if len(df_d) < 30: continue

        vol_today = float(df_d['Volume'].iloc[-1])
        vol_yest = float(df_d['Volume'].iloc[-2]) if len(df_d)>=2 else vol_today
        vol_ratio = vol_today / vol_yest if vol_yest else 0

        if vol_ratio >= 2.0:
            major.append(f"🔥 {etf} 爆量派貨 - {name_cn}")

        if len(df_w) >= 60:
            div = find_div(df_w['Close'], get_dif(df_w['Close']))
            if div:
                major.append(f"⚠️ {etf} 週線{div} - {name_cn}{'見頂' if '頂' in div else '見底'}")

        if len(df_60m) >= 60:
            df_4h = df_60m.resample("4h").agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
            if len(df_4h) >= 60:
                div = find_div(df_4h['Close'], get_dif(df_4h['Close']))
                if div:
                    minor.append(f"{etf} 4H{div} - {name_cn}")

        if len(df_m) >= 30:
            j = get_kdj(df_m).dropna()
            if len(j)>=5:
                div = find_div(df_m['Close'].loc[j.index], j)
                if div:
                    j_now=float(j.iloc[-1]); j_prev=float(j.iloc[-2])
                    if ("頂" in div and j_now<j_prev) or ("底" in div and j_now>j_prev):
                        major.append(f"🗓️ {etf} 月線{div} - {name_cn}見大{'頂' if '頂' in div else '底'}")

        if len(df_w) >= 30:
            j = get_kdj(df_w).dropna()
            if len(j)>=5:
                div = find_div(df_w['Close'].loc[j.index], j)
                if div:
                    j_now=float(j.iloc[-1]); j_prev=float(j.iloc[-2])
                    if ("頂" in div and j_now<j_prev) or ("底" in div and j_now>j_prev):
                        major.append(f"📅 {etf} 週線{div} - {name_cn}")

        if len(df_d) >= 30:
            j = get_kdj(df_d).dropna()
            if len(j)>=5:
                div = find_div(df_d['Close'].loc[j.index], j)
                if div:
                    j_now=float(j.iloc[-1]); j_prev=float(j.iloc[-2])
                    if ("頂" in div and j_now<j_prev) or ("底" in div and j_now>j_prev):
                        minor.append(f"{etf} 日線{div} - {name_cn}")

        signals.append({"date":datetime.now().strftime('%Y-%m-%d'),"etf":etf,"name_cn":name_cn})
    except Exception as e:
        print(f"skip {etf} {e}")
        continue

# Supabase - 修正用 name_cn
try:
    from supabase import create_client
    SUPABASE_URL=os.environ.get('SUPABASE_URL','').strip()
    SUPABASE_KEY=os.environ.get('SUPABASE_KEY','').strip()
    print(f"SUPABASE check URL={bool(SUPABASE_URL)} KEY={bool(SUPABASE_KEY)}")
    if SUPABASE_URL and SUPABASE_KEY:
        sb=create_client(SUPABASE_URL, SUPABASE_KEY)
        sb.table("signals").delete().neq("etf","XXX").execute()
        to_insert = [{"date":s["date"],"etf":s["etf"],"name_cn":s["name_cn"]} for s in signals]
        res = sb.table("signals").insert(to_insert).execute()
        print(f"Supabase OK {len(res.data)}")
except Exception as e:
    print(f"Supabase error {e}")

# 網頁
html=f"<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><style>body{{font-family:sans-serif;padding:15px}} .major{{font-size:16px;margin:12px 0;font-weight:bold}} .minor{{color:#888;font-size:13px;margin:8px 0}}</style></head><body><h3>V9.7 無數+隔行 {datetime.now().strftime('%Y-%m-%d %H:%M')}</h3><h4>🔴 大級別</h4>"
for m in major: html+=f"<div class=major>{m}</div>"
html+="<h4>⚪ 短線</h4>"
for m in minor: html+=f"<div class=minor>{m}</div>"
html+="</body></html>"
open("index.html","w",encoding="utf-8").write(html)

# ntfy 每條隔一行 無數
if major or minor:
    all_msgs = major + [f"({x})" for x in minor]
    message = f"雷達 V9.7 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n" + "\n\n".join(all_msgs)
    try:
        requests.post("https://ntfy.sh/sector-radar-ivan117", data=message.encode('utf-8'), headers={"Title":"Sector Radar V9.7","Priority":"high"}, timeout=10)
        print("ntfy Sent")
    except Exception as e: print(e)
