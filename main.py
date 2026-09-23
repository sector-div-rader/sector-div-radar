import yfinance as yf, os, pandas as pd, requests
from datetime import datetime

ETFS = {'XLE':'能源','XLF':'金融','XLK':'科技','XLV':'醫療','XLI':'工業','XLP':'必需消費','XLY':'可選消費','XLB':'原材料','XLU':'公用','XLRE':'地產','XLC':'通訊'}

def get_dif(close, fast=5, slow=26):
    return close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()

def get_kdj(df, n=9):
    low = df['Low'].rolling(n).min(); high = df['High'].rolling(n).max()
    rsv = (df['Close'] - low) / (high - low) * 100
    k = rsv.ewm(com=2, adjust=False).mean(); d = k.ewm(com=2, adjust=False).mean()
    return 3*k - 2*d

def find_div(price, ind):
    if len(price) < 30: return None
    p = price.iloc[-60:]; i = ind.iloc[-60:]
    search = p.iloc[:-5].iloc[-20:]
    if len(search) < 5: return None
    peak_p = float(p.loc[search.idxmax()]); trough_p = float(p.loc[search.idxmin()])
    peak_i = float(i.loc[search.idxmax()]); trough_i = float(i.loc[search.idxmin()])
    curr_p = float(p.iloc[-1]); curr_i = float(i.iloc[-1])
    if curr_p >= peak_p * 0.98 and curr_i < peak_i * 0.97: return "頂背離"
    if curr_p <= trough_p * 1.02 and curr_i > trough_i * 1.03: return "底背離"
    return None

signals=[]; major=[]; minor=[]

for etf, name_cn in ETFS.items():
    try:
        t = yf.Ticker(etf)
        df_d = t.history(period="1y", interval="1d", auto_adjust=True) # 要1年計200日
        df_w = t.history(period="2y", interval="1wk", auto_adjust=True)
        df_m = t.history(period="10y", interval="1mo", auto_adjust=True)
        df_60m = t.history(period="3mo", interval="60m", auto_adjust=True)
        if len(df_d) < 200: continue

        close = float(df_d['Close'].iloc[-1])
        high_50 = float(df_d['High'].iloc[-50:].max())
        high_200 = float(df_d['High'].iloc[-200:].max())
        dist_50 = (close/high_50 - 1)*100
        dist_200 = (close/high_200 - 1)*100

        # 新聞 - 取yfinance自帶
        news_title=""; news_url=""
        try:
            news = t.news[:1]
            if news:
                news_title = news[0].get('title','')[:100]
                news_url = news[0].get('link','')
        except: pass

        sig_text = "正常"
        # 月週背離
        if len(df_w) >= 60:
            div = find_div(df_w['Close'], get_dif(df_w['Close']))
            if div:
                sig_text = f"週線{div}"
                major.append(f"⚠️ {etf} 週線{div} - {name_cn} {dist_50:.1f}%離50日高")
        if len(df_m) >= 30:
            j = get_kdj(df_m).dropna()
            if len(j)>=5 and find_div(df_m['Close'].loc[j.index], j):
                sig_text = f"月線{find_div(df_m['Close'].loc[j.index], j)}"
                major.append(f"🗓️ {etf} {sig_text} - {name_cn}見大頂底，現價{close:.2f} 距200日高{dist_200:.1f}%")

        # 4H放minor
        if len(df_60m) >= 60:
            df_4h = df_60m.resample("4h").agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
            if len(df_4h) >= 60:
                div = find_div(df_4h['Close'], get_dif(df_4h['Close']))
                if div: minor.append(f"{etf} 4H{div} - {name_cn}")

        signals.append({
            "etf":etf, "name_cn":name_cn, "price":close,
            "high_50d":high_50, "high_200d":high_200,
            "dist_50d":round(dist_50,2), "dist_200d":round(dist_200,2),
            "news_title":news_title, "news_url":news_url,
            "signal":sig_text
        })
    except Exception as e:
        print(f"skip {etf} {e}"); continue

# Supabase
try:
    from supabase import create_client
    sb=create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
    sb.table("signals").delete().neq("etf","XXX").execute()
    # 唔再入date，每日更新覆蓋
    res = sb.table("signals").insert(signals).execute()
    print(f"Supabase OK {len(res.data)}")
except Exception as e:
    print(f"Supabase error {e}")

# 網頁同ntfy - 清爽版無數
html=f"<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><style>body{{font-family:sans-serif;padding:15px;font-size:14px}} td{{border:1px solid #ddd;padding:6px}}.neg{{color:red}}.pos{{color:green}}</style></head><body><h3>V10 收市價+高位+新聞 {datetime.now().strftime('%m-%d %H:%M')}</h3><table><tr><th>ETF</th><th>收市</th><th>50日高</th><th>200日高</th><th>距高%</th><th>信號</th><th>新聞</th></tr>"
for s in signals:
    html+=f"<tr><td>{s['etf']}{s['name_cn']}</td><td>{s['price']:.2f}</td><td>{s['high_50d']:.2f}</td><td>{s['high_200d']:.2f}</td><td class='neg'>{s['dist_50d']}% / {s['dist_200d']}%</td><td>{s['signal']}</td><td><a href='{s['news_url']}' target=_blank>{s['news_title'][:30]}</a></td></tr>"
html+="</table></body></html>"
open("index.html","w",encoding="utf-8").write(html)

if major:
    message = f"雷達 V10 {datetime.now().strftime('%m-%d')}\n\n" + "\n\n".join(major)
    requests.post("https://ntfy.sh/sector-radar-ivan117", data=message.encode('utf-8'), headers={"Title":"Sector Radar V10","Priority":"high"}, timeout=10)
