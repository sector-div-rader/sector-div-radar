import yfinance as yf, os, pandas as pd, requests, numpy as np
from datetime import datetime

ETFS = {
    'XLE':'能源','XLF':'金融','XLK':'科技','XLV':'醫療','XLI':'工業',
    'XLP':'必需消費','XLY':'可選消費','XLB':'原材料','XLU':'公用','XLRE':'地產','XLC':'通訊'
}

def get_dif(close):
    return close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()

def get_kdj(df, n=9, m1=3, m2=3):
    low = df['Low'].rolling(n).min()
    high = df['High'].rolling(n).max()
    rsv = (df['Close'] - low) / (high - low) * 100
    k = rsv.ewm(com=m1-1, adjust=False).mean()
    d = k.ewm(com=m2-1, adjust=False).mean()
    j = 3*k - 2*d
    return j

def find_double_divergence(price, ind, lookback=60):
    if len(price) < lookback: return None
    p = price.iloc[-lookback:]
    i = ind.iloc[-lookback:]
    curr_p = float(p.iloc[-1])
    prev_high_idx = p.iloc[:-5].idxmax()
    prev_high = float(p.loc[prev_high_idx])
    prev_high_ind = float(i.loc[prev_high_idx])
    prev_low_idx = p.iloc[:-5].idxmin()
    prev_low = float(p.loc[prev_low_idx])
    prev_low_ind = float(i.loc[prev_low_idx])
    curr_ind = float(i.iloc[-1])
    if curr_p >= prev_high * 0.97 and curr_ind < prev_high_ind * 0.97:
        return f"頂背離({curr_p:.2f}vs前高{prev_high:.2f},指標{curr_ind:.1f}<{prev_high_ind:.1f})"
    if curr_p <= prev_low * 1.03 and curr_ind > prev_low_ind * 1.03:
        return f"底背離({curr_p:.2f}vs前低{prev_low:.2f},指標{curr_ind:.1f}>{prev_low_ind:.1f})"
    return None

signals=[]
alerts=[]

for etf,name_cn in ETFS.items():
    try:
        macd_msgs=[]
        for interval, period, label in [("1wk","2y","週線"), ("60m","3mo","4H線")]:
            try:
                df = yf.Ticker(etf).history(period=period, interval=interval, auto_adjust=True)
                if len(df)<60: continue
                if label=="4H線":
                    df = df.resample("4H").agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'last'}).dropna()
                if len(df)<60: continue
                close = df['Close']
                if isinstance(close, pd.DataFrame): close = close.iloc[:,0]
                dif = get_dif(close)
                div = find_double_divergence(close, dif)
                if div:
                    macd_msgs.append(f"{label}{div}")
                    alerts.append(f"⚠️ {etf} MACD-DIF {label}{div}")
            except: continue

        df_d = yf.Ticker(etf).history(period="3mo", interval="1d", auto_adjust=True)
        if len(df_d)<20: continue
        vol_today = float(df_d['Volume'].iloc[-1])
        vol_yest = float(df_d['Volume'].iloc[-2])
        vol_ratio = vol_today / vol_yest if vol_yest else 0
        turnover_rate = 0
        try:
            shares = yf.Ticker(etf).fast_info.shares
            if shares: turnover_rate = vol_today / shares * 100
        except:
            turnover_rate = vol_ratio * 2.5
        if vol_ratio >= 2.0 and turnover_rate >= 5.0:
            alerts.append(f"🔥 {etf} 爆量 {vol_ratio:.1f}倍 換手{turnover_rate:.1f}% (日線)")

        kdj_msgs=[]
        for k_interval, k_period, k_label in [("1d","6mo","日線"), ("1wk","2y","週線"), ("1mo","5y","月線")]:
            try:
                df_k = yf.Ticker(etf).history(period=k_period, interval=k_interval, auto_adjust=True)
                if len(df_k)<30: continue
                j = get_kdj(df_k)
                close_k = df_k['Close']
                if isinstance(close_k, pd.DataFrame): close_k = close_k.iloc[:,0]
                if isinstance(j, pd.DataFrame): j = j.iloc[:,0]
                j = j.dropna()
                close_k = close_k.loc[j.index]
                if len(j)<5: continue
                j_now = float(j.iloc[-1]); j_prev = float(j.iloc[-2])
                turning = "J拐頭向下" if j_now < j_prev else "J拐頭向上" if j_now > j_prev else ""
                div_j = find_double_divergence(close_k, j, lookback=60)
                if div_j and turning:
                    kdj_msgs.append(f"{k_label}{turning}{div_j}")
                    icon = "🔮" if k_label=="月線" else "📅" if k_label=="週線" else "📌"
                    alerts.append(f"{icon} {etf} KDJ-J {k_label}{turning}{div_j} J={j_now:.1f}")
            except: continue

        price = float(df_d['Close'].iloc[-1])
        signals.append({
            "date": datetime.now().strftime('%Y-%m-%d'),
            "etf": etf, "name_cn": name_cn, "type": "輪動",
            "level": ";".join(macd_msgs) if macd_msgs else "正常",
            "price": price,
            "strength": vol_ratio,
            "k": round(turnover_rate,2),
            "d": 0, "j": 0,
            "kdj": ";".join(kdj_msgs) if kdj_msgs else "無",
            "turnover": turnover_rate,
            "extra": f"MACD:{'|'.join(macd_msgs) if macd_msgs else '無'}; VOL:{vol_ratio:.1f}x; KDJ:{'|'.join(kdj_msgs) if kdj_msgs else '無'}"
        })
    except Exception as e:
        print(f"skip {etf} {e}")
        continue

# Supabase
try:
    from supabase import create_client
    SUPABASE_URL=os.environ.get('SUPABASE_URL','').strip()
    SUPABASE_KEY=os.environ.get('SUPABASE_KEY','').strip()
    if SUPABASE_URL and SUPABASE_KEY:
        supabase=create_client(SUPABASE_URL, SUPABASE_KEY)
        try: supabase.table("signals").delete().neq("id",0).execute()
        except: pass
        supabase.table("signals").insert(signals).execute()
        print(f"Supabase OK {len(signals)}")
except Exception as e:
    print(f"Supabase error {e}")

# 網頁
html=f"<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>V8.1 三級KDJ版</title><style>body{{font-family:sans-serif;padding:10px;font-size:12px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:5px}}</style></head><body><h3>V8.1 日週月KDJ共振版 {datetime.now().strftime('%Y-%m-%d')}</h3><table><tr><th>ETF</th><th>MACD-DIF背離(週/4H)</th><th>爆量(日)</th><th>KDJ-J背離(日/週/月)</th></tr>"
for s in signals:
    html+=f"<tr><td>{s['etf']}{s['name_cn']}</td><td>{s['level']}</td><td>{s['strength']:.1f}x / {s['turnover']:.1f}%</td><td>{s['kdj']}</td></tr>"
html+="</table><p>"+ "<br>".join(alerts) +"</p></body></html>"
open("index.html","w",encoding="utf-8").write(html)

# --- ntfy 推送 ---
if alerts:
    try:
        message = "板塊頂底雷達 V8.1 " + datetime.now().strftime('%Y-%m-%d %H:%M') + "\n" + "\n".join(alerts)
        topic = "sector-radar-ivan117"
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode('utf-8'),
            headers={
                "Title": "Sector Radar Alert V8.1",
                "Priority": "high",
                "Tags": "rotating_light"
            },
            timeout=10
        )
        print("ntfy Sent!")
        print(message)
    except Exception as e:
        print(f"ntfy Failed: {e}")
else:
    print("今日無觸發")