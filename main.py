import yfinance as yf, os, pandas as pd, requests
from datetime import datetime

ETFS = {'XLE':'能源','XLF':'金融','XLK':'科技','XLV':'醫療','XLI':'工業','XLP':'必需消費','XLY':'可選消費','XLB':'原材料','XLU':'公用','XLRE':'地產','XLC':'通訊'}

def get_dif(close, fast=5, slow=26): # 同富途一致 5,26
    return close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()

def get_kdj(df, n=9):
    low = df['Low'].rolling(n).min()
    high = df['High'].rolling(n).max()
    rsv = (df['Close'] - low) / (high - low) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    return 3*k - 2*d

def find_div(price, ind, lookback=60):
    # FIX: 搵最近20日嘅局部高低點，唔係成60日最高
    if len(price) < 30: return None
    p = price.iloc[-lookback:].copy()
    i = ind.iloc[-lookback:].copy()
    curr_p = float(p.iloc[-1])
    curr_i = float(i.iloc[-1])
    if pd.isna(curr_p) or pd.isna(curr_i): return None
    
    # 排除最近5根，喺最近20根入面搵
    search = p.iloc[:-5].iloc[-20:]
    if len(search) < 5: return None
    peak_idx = search.idxmax()
    trough_idx = search.idxmin()
    peak_p = float(p.loc[peak_idx]); peak_i = float(i.loc[peak_idx])
    trough_p = float(p.loc[trough_idx]); trough_i = float(i.loc[trough_idx])

    if curr_p >= peak_p * 0.98 and curr_i < peak_i * 0.97:
        return f"頂背離({curr_p:.2f}vs前高{peak_p:.2f},指標{curr_i:.1f}<{peak_i:.1f})"
    if curr_p <= trough_p * 1.02 and curr_i > trough_i * 1.03:
        return f"底背離({curr_p:.2f}vs前低{trough_p:.2f},指標{curr_i:.1f}>{trough_i:.1f})"
    return None

signals=[]; alerts=[]

for etf, name_cn in ETFS.items():
    try:
        # FIX: 一次過下載，唔好下載4次
        df_d = yf.Ticker(etf).history(period="6mo", interval="1d", auto_adjust=True)
        df_w = yf.Ticker(etf).history(period="2y", interval="1wk", auto_adjust=True)
        df_60m = yf.Ticker(etf).history(period="3mo", interval="60m", auto_adjust=True)
        if len(df_d) < 30: continue

        macd_msgs=[]; kdj_msgs=[]
        
        # 週線MACD
        if len(df_w) >= 60:
            dif_w = get_dif(df_w['Close'])
            div = find_div(df_w['Close'], dif_w)
            if div:
                macd_msgs.append(f"週線{div}")
                alerts.append(f"⚠️ {etf} MACD週線{div}")

        # FIX Bug1: 4H線 volume要用sum，4h小寫
        if len(df_60m) >= 60:
            df_4h = df_60m.resample("4h").agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
            if len(df_4h) >= 60:
                dif_4h = get_dif(df_4h['Close'])
                div = find_div(df_4h['Close'], dif_4h)
                if div:
                    macd_msgs.append(f"4H線{div}")
                    alerts.append(f"⚠️ {etf} MACD-4H{div}")

        # FIX Bug4: 爆量門檻放寬 1.5倍 + 2%
        vol_today = float(df_d['Volume'].iloc[-1])
        vol_yest = float(df_d['Volume'].iloc[-2])
        vol_ratio = vol_today / vol_yest if vol_yest else 0
        turnover = 0
        try:
            shares = yf.Ticker(etf).fast_info.shares
            if shares: turnover = vol_today / shares * 100
        except: pass
        if vol_ratio >= 1.5: # 唔再卡死5%
            alerts.append(f"🔥 {etf} 爆量{vol_ratio:.1f}倍 換手{turnover:.1f}%")
        
        # KDJ 日/週
        for df_k, label, icon in [(df_d, "日線", "📌"), (df_w, "週線", "📅")]:
            if len(df_k) < 30: continue
            j = get_kdj(df_k).dropna()
            if len(j) < 5: continue
            close_k = df_k['Close'].loc[j.index]
            div_j = find_div(close_k, j)
            j_now = float(j.iloc[-1]); j_prev = float(j.iloc[-2])
            turning = "J拐頭向下" if j_now < j_prev else "J拐頭向上" if j_now > j_prev else ""
            if div_j and turning:
                valid = ("頂背離" in div_j and "向下" in turning) or ("底背離" in div_j and "向上" in turning)
                if not valid: continue
                kdj_msgs.append(f"{label}{turning}{div_j}")
                alerts.append(f"{icon} {etf} KDJ-{label}{turning}{div_j} J={j_now:.1f}")

        signals.append({
            "date": datetime.now().strftime('%Y-%m-%d'), "etf": etf, "name_cn": name_cn, "type": "輪動",
            "level": ";".join(macd_msgs) if macd_msgs else "正常",
            "price": float(df_d['Close'].iloc[-1]), "strength": vol_ratio,
            "k": round(turnover,2), "d":0,"j":0,
            "kdj": ";".join(kdj_msgs) if kdj_msgs else "無",
            "turnover": turnover,
            "extra": f"MACD:{'|'.join(macd_msgs) if macd_msgs else '無'}; VOL:{vol_ratio:.1f}x"
        })
    except Exception as e:
        print(f"skip {etf} {e}")
        continue

# FIX Bug5: Supabase delete改用gte，唔會被RLS卡死
try:
    from supabase import create_client
    SUPABASE_URL=os.environ.get('SUPABASE_URL','').strip()
    SUPABASE_KEY=os.environ.get('SUPABASE_KEY','').strip()
    if SUPABASE_URL and SUPABASE_KEY:
        sb=create_client(SUPABASE_URL, SUPABASE_KEY)
        try: sb.table("signals").delete().gte("id",0).execute()
        except Exception as e: print(f"delete skip {e}")
        sb.table("signals").insert(signals).execute()
        print(f"Supabase OK {len(signals)}")
    else:
        print("Supabase secrets missing")
except Exception as e:
    print(f"Supabase error {e}")

html=f"<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>V9</title><style>body{{font-family:sans-serif;padding:10px;font-size:12px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:5px}}</style></head><body><h3>V9 BugFix全修版 {datetime.now().strftime('%Y-%m-%d')}</h3><table><tr><th>ETF</th><th>MACD背離</th><th>爆量</th><th>KDJ背離</th></tr>"
for s in signals:
    html+=f"<tr><td>{s['etf']}{s['name_cn']}</td><td>{s['level']}</td><td>{s['strength']:.1f}x / {s['turnover']:.1f}%</td><td>{s['kdj']}</td></tr>"
html+="</table><p>"+ "<br>".join(alerts) +"</p></body></html>"
open("index.html","w",encoding="utf-8").write(html)

if alerts:
    try:
        message = f"雷達 V9 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n" + "\n".join(alerts)
        requests.post(f"https://ntfy.sh/sector-radar-ivan117", data=message.encode('utf-8'), headers={"Title":"Sector Radar V9","Priority":"high","Tags":"rotating_light"}, timeout=10)
        print("ntfy Sent!")
    except Exception as e: print(f"ntfy Failed {e}")
else: print("今日無觸發")