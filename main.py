import yfinance as yf, os, pandas as pd, requests
from datetime import datetime
from supabase import create_client

# ========= 設定 =========
ETFS = {
    'XLE':'能源','XLF':'金融','XLK':'科技','XLV':'醫療','XLI':'工業',
    'XLP':'必需消費','XLY':'可選消費','XLB':'原材料','XLU':'公用','XLRE':'地產','XLC':'通訊'
}
SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_KEY']
PHONE = os.environ.get('PHONE','')
APIKEY = os.environ.get('APIKEY','')
CALLMEBOT = os.environ.get('CALLMEBOT_APIKEY','')

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

signals=[]
for etf,name_cn in ETFS.items():
    df = yf.download(etf, period='6mo', progress=False)
    if len(df)<50: continue
    df['MA20']=df['Close'].rolling(20).mean()
    df['MA50']=df['Close'].rolling(50).mean()
    price=float(df['Close'].iloc[-1])
    ma20=float(df['MA20'].iloc[-1])
    ma50=float(df['MA50'].iloc[-1])
    level='強' if price>ma20>ma50 else '弱' if price<ma20<ma50 else '中性'
    strength = round((price/ma50-1)*100,2)
    signals.append({"date":datetime.now().strftime('%Y-%m-%d'),"etf":etf,"name_cn":name_cn,"type":"輪動","level":level,"price":price,"strength":strength})

# 寫入 Supabase
if signals:
    supabase.table("signals").delete().neq("id",0).execute()
    supabase.table("signals").insert(signals).execute()

# 產生網頁
html = f"<html><head><meta charset='utf-8'><title>板塊輪動雷達 V6</title><style>body{{font-family:sans-serif;padding:20px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:8px}} .強{{background:#d4edda}} .弱{{background:#f8d7da}}</style></head><body><h1>板塊輪動雷達 V6 - {datetime.now().strftime('%Y-%m-%d %H:%M')}</h1><table><tr><th>ETF</th><th>中文</th><th>價格</th><th>強度%</th><th>狀態</th></tr>"
for s in sorted(signals,key=lambda x:x['strength'],reverse=True):
    html+=f"<tr class='{s['level']}'><td>{s['etf']}</td><td>{s['name_cn']}</td><td>{s['price']:.2f}</td><td>{s['strength']}</td><td>{s['level']}</td></tr>"
html+="</table></body></html>"
open("index.html","w",encoding="utf-8").write(html)

# WhatsApp
if CALLMEBOT and PHONE:
    top = sorted(signals,key=lambda x:x['strength'],reverse=True)[:3]
    msg = f"V6雷達 {datetime.now().strftime('%m-%d')} 最強: "+",".join([f"{x['etf']}({x['name_cn']}){x['strength']}%" for x in top])
    try:
        requests.get(f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={msg}&apikey={CALLMEBOT}")
    except: pass
