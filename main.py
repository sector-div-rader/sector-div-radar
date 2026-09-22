import yfinance as yf, os, pandas as pd, requests, time
from datetime import datetime

ETFS = {
    'XLE':'能源','XLF':'金融','XLK':'科技','XLV':'醫療','XLI':'工業',
    'XLP':'必需消費','XLY':'可選消費','XLB':'原材料','XLU':'公用','XLRE':'地產','XLC':'通訊'
}

def get_val(series):
    v = series.iloc[-1]
    if isinstance(v, pd.Series):
        v = v.iloc[0]
    return float(v)

signals=[]
for etf,name_cn in ETFS.items():
    try:
        df = yf.download(etf, period='6mo', progress=False, auto_adjust=True)
        if len(df)<50: continue
        close = df['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:,0]
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        price = get_val(close)
        m20 = get_val(ma20)
        m50 = get_val(ma50)
        level='強' if price>m20>m50 else '弱' if price<m20<m50 else '中性'
        strength = round((price/m50-1)*100,2)
        signals.append({"date":datetime.now().strftime('%Y-%m-%d'),"etf":etf,"name_cn":name_cn,"type":"輪動","level":level,"price":price,"strength":strength})
    except Exception as e:
        print(f"skip {etf}: {e}")
        continue

# ---- Supabase (失敗都唔會死) ----
try:
    from supabase import create_client
    SUPABASE_URL = os.environ.get('SUPABASE_URL','').strip()
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY','').strip()
    print(f"Supabase URL: {SUPABASE_URL[:30]}...")
    if SUPABASE_URL and SUPABASE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        try:
            supabase.table("signals").delete().neq("id",0).execute()
        except: pass
        supabase.table("signals").insert(signals).execute()
        print("Supabase OK")
    else:
        print("No Supabase secrets, skip")
except Exception as e:
    print(f"Supabase error but continue: {e}")

# ---- 產生網頁 ----
html = f"<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>板塊輪動雷達 V6.2</title><style>body{{font-family:sans-serif;padding:20px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:8px;text-align:center}}.強{{background:#d4edda}}.弱{{background:#f8d7da}}</style></head><body><h1>板塊輪動雷達 V6.2 - {datetime.now().strftime('%Y-%m-%d %H:%M')}</h1><table><tr><th>ETF</th><th>中文</th><th>價格</th><th>強度%</th><th>狀態</th></tr>"
for s in sorted(signals,key=lambda x:x['strength'],reverse=True):
    html+=f"<tr class='{s['level']}'><td>{s['etf']}</td><td>{s['name_cn']}</td><td>{s['price']:.2f}</td><td>{s['strength']}</td><td>{s['level']}</td></tr>"
html+="</table><p>自動更新每日 06:00 HKT</p></body></html>"
open("index.html","w",encoding="utf-8").write(html)
print("index.html created")

# ---- WhatsApp ----
try:
    CALLMEBOT = os.environ.get('CALLMEBOT_APIKEY','').strip()
    PHONE = os.environ.get('PHONE','').strip()
    if CALLMEBOT and PHONE and signals:
        top = sorted(signals,key=lambda x:x['strength'],reverse=True)[:3]
        msg = f"V6.2雷達 {datetime.now().strftime('%m-%d')} 最強: "+",".join([f"{x['etf']}{x['strength']}%" for x in top])
        requests.get(f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={msg}&apikey={CALLMEBOT}", timeout=10)
except Exception as e:
    print(f"WhatsApp skip: {e}")
