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

def find_div(price, ind, lookback=60, strict=False):
    if len(price) < 30: return None
    p = price.iloc[-lookback:].copy()
    i = ind.iloc[-lookback:].copy()
    curr_p = float(p.iloc[-1]); curr_i = float(i.iloc[-1])
    if pd.isna(curr_p) or pd.isna(curr_i): return None
    search = p.iloc[:-5].iloc[-20:]
    if len(search) < 5: return None
    peak_idx = search.idxmax(); trough_idx = search.idxmin()
    peak_p = float(p.loc[peak_idx]); peak_i = float(i.loc[peak_idx])
    trough_p = float(p.loc[trough_idx]); trough_i = float(i.loc[trough_idx])
    # 月週線鬆0.97，4H嚴0.80
    thresh = 0.80 if strict else 0.97
    if curr_p >= peak_p * 0.98 and curr_i < peak_i * thresh:
        return f"頂背離({curr_p:.2f}vs前高{peak_p:.2f},指標{curr_i:.1f}<{peak_i:.1f})"
    if curr_p <= trough_p * 1.02 and curr_i > trough_i * (2-thresh if thresh<1 else 1.03):
        return f"底背離({curr_p:.2f}vs前低{trough_p:.2f},指標{curr_i:.1f}>{trough_i:.1f})"
    return None

signals=[]; alerts=[]

for etf, name_cn in ETFS.items():
    try:
        t = yf.Ticker(etf)
        df_d = t.history(period="6mo", interval="1d", auto_adjust=True)
        df_w = t.history(period="2y", interval="1wk", auto_adjust=True)
        df_m = t.history(period="10y", interval="1mo", auto_adjust=True)
        df_60m = t.history(period="3mo", interval="60m", auto_adjust=True)
        if len(df_d) < 30: continue
        macd_msgs=[]; kdj_msgs=[]
        
        # 換手率
        vol_today = float(df_d['Volume'].iloc[-1])
        vol_yest = float(df_d['Volume'].iloc[-2]) if len(df_d)>=2 else vol_today
        vol_ratio = vol_today / vol_yest if vol_yest else 0
        turnover = 0; shares = None
        try:
            info = t.get_info()
            shares = info.get('sharesOutstanding') or info.get('impliedSharesOutstanding')
        except: pass
        if shares and shares > 0:
            turnover = vol_today / shares * 100
        else:
            turnover = vol_today / 900_000_000 * 100

        if vol_ratio >= 1.5:
            alerts.append(f"🔥 {etf} 爆量{vol_ratio:.1f}倍 換手{turnover:.2f}%")

        # MACD - 週線鬆，4H嚴
        if len(df_w) >= 60:
            dif_w = get_dif(df_w['Close'])
            div = find_div(df_w['Close'], dif_w, strict=False)
            if div:
                macd_msgs.append(f"週線{div}")
                alerts.append(f"⚠️ {etf} MACD週線{div}")

        if len(df_60m) >= 60:
            df_4h = df_60m.resample("4h").agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
            if len(df_4h) >= 60:
                dif_4h = get_dif(df_4h['Close'])
                div = find_div(df_4h['Close'], dif_4h, strict=True)
                # 4H要有量或者好弱先叫
                if div and (vol_ratio >= 1.3 or "0." in div or "<" in div):
                    # 簡化：有div就當過濾咗
                    macd_msgs.append(f"4H{div}")
                    alerts.append(f"⚠️ {etf} MACD-4H{div}")

        # KDJ - 月/週/日
        for df_k, label, icon in [(df_d, "日線", "📌"), (df_w, "週線", "📅"), (df_m, "月線", "🗓️")]:
            if len(df_k) < 30: continue
            j = get_kdj(df_k).dropna()
            if len(j) < 5: continue
            close_k = df_k['Close'].loc[j.index]
            is_strict = (label!="月線" and label!="週線") # 日線同4H用嚴啲其實月週先重要
            div_j = find_div(close_k, j, strict=False)
            if len(j) < 2: continue
            j_now = float(j.iloc[-1]); j_prev = float(j.iloc[-2])
            turning = "J拐頭向下" if j_now < j_prev else "J拐頭向上" if j_now > j_prev else ""
            if div_j and turning:
                valid = ("頂背離" in div_j and "向下" in turning) or ("底背離" in div_j and "向上" in turning)
                if not valid: continue
                # 月週線一定要叫，日線要有少力度
                if label in ["月線","週線"] or abs(j_now-j_prev)>2:
                    kdj_msgs.append(f"{label}{turning}{div_j}")
                    alerts.append(f"{icon} {etf} KDJ-{label}{turning}{div_j} J={j_now:.1f}")

        signals.append({
            "date": datetime.now().strftime('%Y-%m-%d'), "etf": etf, "name_cn": name_cn, "type": "輪動",
            "level": ";".join(macd_msgs) if macd_msgs else "正常",
            "price": float(df_d['Close'].iloc[-1]), "strength": vol_ratio,
            "k": round(turnover,2), "d":0,"j":0,
            "kdj": ";".join(kdj_msgs) if kdj_msgs else "無",
            "turnover": turnover,
            "extra": f"VOL:{vol_ratio:.1f}x / {turnover:.2f}%"
        })
    except Exception as e:
        print(f"skip {etf} {e}")
        continue

# Supabase 修復版
try:
    from supabase import create_client
    SUPABASE_URL=os.environ.get('SUPABASE_URL','').strip()
    SUPABASE_KEY=os.environ.get('SUPABASE_KEY','').strip()
    print(f"SUPABASE_URL set: {bool(SUPABASE_URL)} KEY set: {bool(SUPABASE_KEY)}")
    if SUPABASE_URL and SUPABASE_KEY:
        sb=create_client(SUPABASE_URL, SUPABASE_KEY)
        # 先試下delete全部，唔用neq
        try:
            sb.table("signals").delete().gte("id",0).execute()
        except:
            sb.table("signals").delete().neq("etf","XXX_NOT_EXIST").execute()
        to_insert = []
        for s in signals:
            to_insert.append({
                "date": s["date"], "etf": s["etf"], "name_en": s["name_cn"],
                "type": s["type"], "level": s["level"], "price": s["price"],
                "strength": s["strength"], "k": s["k"], "d": s["d"], "j": s["j"],
                "kdj": s["kdj"], "turnover": s["turnover"], "extra": s["extra"]
            })
        res = sb.table("signals").insert(to_insert).execute()
        print(f"Supabase OK inserted {len(to_insert)} res={res}")
    else:
        print("Supabase ENV missing")
except Exception as e:
    print(f"Supabase error {e}")

html=f"<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>V9.4</title><style>body{{font-family:sans-serif;padding:10px;font-size:12px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:5px}}</style></head><body><h3>V9.4 隔行+4H過濾 {datetime.now().strftime('%Y-%m-%d %H:%M')}</h3><table><tr><th>ETF</th><th>MACD-DIF</th><th>量/換手</th><th>KDJ-J</th></tr>"
for s in signals:
    html+=f"<tr><td>{s['etf']}{s['name_cn']}</td><td>{s['level']}</td><td>{s['strength']:.1f}x / {s['turnover']:.2f}%</td><td>{s['kdj']}</td></tr>"
html+="</table><p>"+ "<br><br>".join(alerts) +"</p></body></html>"
open("index.html","w",encoding="utf-8").write(html)

if alerts:
    try:
        message = f"雷達 V9.4 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n" + "\n\n".join(alerts)
        requests.post(f"https://ntfy.sh/sector-radar-ivan117", data=message.encode('utf-8'), headers={"Title":"Sector Radar V9.4","Priority":"high"}, timeout=10)
        print("ntfy Sent!")
    except Exception as e: print(f"ntfy Failed {e}")
else: print("今日無觸發")
