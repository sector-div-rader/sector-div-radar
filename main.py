# radar_v14.8.py - 只計最長週期 + 只計DIF分數，J僅顯示
import yfinance as yf
import os, csv, smtplib, traceback
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': os.environ.get('EMAIL_USER'),
    'sender_password': os.environ.get('EMAIL_PASS'),
    'receiver_email': os.environ.get('EMAIL_TO', os.environ.get('EMAIL_USER'))
}

INDICES = {
    'ES=F': {'name':'標普500期貨','sticker':'📈','weight':5,'index':'SPX','etf':'SPY'},
    'NQ=F': {'name':'納指100期貨','sticker':'📱','weight':5,'index':'NDX','etf':'QQQ'},
    'YM=F': {'name':'道指期貨','sticker':'🏛️','weight':3,'index':'DJI','etf':'DIA'},
}
SECTORS = {
    'XLE':{'name':'美股石油天然氣','sticker':'🛢️','weight':2,'index':'SPX'},
    'KBE':{'name':'美股銀行','sticker':'🏦','weight':2,'index':'SPX'},
    'SMH':{'name':'美股半導體','sticker':'💾','weight':3,'index':'NDX'},
    'IGV':{'name':'美股軟件服務','sticker':'💿','weight':3,'index':'NDX'},
    'IBB':{'name':'美股生物技術','sticker':'🧬','weight':1,'index':'SPX'},
    'ITA':{'name':'美股航太國防','sticker':'✈️','weight':1,'index':'SPX'},
    'XLP':{'name':'美股必需消費','sticker':'🛒','weight':1,'index':'SPX'},
    'CARZ':{'name':'美股汽車','sticker':'🚗','weight':2,'index':'SPX'},
    'XLB':{'name':'美股原材料','sticker':'🧪','weight':2,'index':'SPX'},
    'XLU':{'name':'美股公用事業','sticker':'💡','weight':1,'index':'SPX'},
    'XLRE':{'name':'美股地產','sticker':'🏠','weight':2,'index':'SPX'},
    'XLC':{'name':'美股通訊服務','sticker':'📡','weight':2,'index':'NDX'},
    'BOTZ':{'name':'美股AI人工智能','sticker':'🤖','weight':3,'index':'NDX'},
    'WCLD':{'name':'美股雲計算','sticker':'☁️','weight':3,'index':'NDX'},
    'HACK':{'name':'美股網絡安全','sticker':'🔒','weight':2,'index':'NDX'},
}
FUTURES = {
    'GC=F':{'name':'黃金期貨','sticker':'🥇','index':'GOLD'},
    'SI=F':{'name':'白銀期貨','sticker':'🥈','index':'SILVER'},
    'CL=F':{'name':'原油期貨','sticker':'⛽','index':'OIL'},
    'DX-Y.NYB':{'name':'美元指數','sticker':'💵','index':'DXY'},
    'ZN=F':{'name':'十年國債','sticker':'📜','index':'BOND'},
    '^VIX':{'name':'恐慌指數','sticker':'😱','index':'VIX'},
}
ALL = {**INDICES, **SECTORS, **FUTURES}

def get_dif(df): return df['Close'].ewm(span=12,adjust=False).mean() - df['Close'].ewm(span=26,adjust=False).mean()
def get_j(df):
    low9=df['Low'].rolling(9).min(); high9=df['High'].rolling(9).max()
    rsv=(df['Close']-low9)/(high9-low9)*100; k=rsv.ewm(com=2,adjust=False).mean(); d=k.ewm(com=2,adjust=False).mean()
    return 3*k-2*d

def find_div(p,i):
    p=p.dropna(); i=i.dropna(); idx=p.index.intersection(i.index); p,i=p.loc[idx],i.loc[idx]
    if len(p)<10: return None
    highs=p[(p.shift(1)<p)&(p.shift(-1)<p)]
    if len(highs)>=2:
        h1,h2=highs.index[-2],highs.index[-1]
        if p[h2]>p[h1] and i[h2]<i[h1]: return '頂'
    lows=p[(p.shift(1)>p)&(p.shift(-1)>p)]
    if len(lows)>=2:
        l1,l2=lows.index[-2],lows.index[-1]
        if p[l2]<p[l1] and i[l2]>i[l1]: return '底'
    return None

# J照掃，但後面唔計分
def scan_asset(t,info):
    sigs=[]; etf=info.get('etf',t)
    for lv,(itv,per) in [('M',('1mo','5y')),('W',('1wk','2y')),('D',('1d','1y')),('4H',('1h','3mo'))]:
        try:
            df=yf.Ticker(etf).history(period=per,interval=itv)
            if len(df)<50: continue
            for n,f in [('DIF',get_dif),('J',get_j)]: # J照留
                d=find_div(df['Close'],f(df))
                if d: sigs.append({**info,'ticker':t,'level':lv,'dir':d,'ind':n})
        except: pass
    return sigs

# 方案1：只保留最長週期 M>W>D>4H
def merge_signals(sigs):
    g={}
    for s in sigs: g.setdefault((s['ticker'],s['dir']),[]).append(s)
    m=[]
    for (t,d),its in g.items():
        info=its[0]
        # 只取最高級別時段
        best=max(its,key=lambda x:{'M':4,'W':3,'D':2,'4H':1}[x['level']])
        lv_str=best['level'];
        # 合併指標名稱，方便對比DIF同J
        ind='+'.join(sorted(set([i['ind'] for i in its if i['level']==lv_str])))
        emoji='🗓️' if lv_str=='M' else '📅' if lv_str=='W' else '⚠️' if lv_str=='D' else '💾'
        cat='科技' if info['index']=='NDX' else '週期' if info['index']=='SPX' else '指數'
        m.append({'ticker':t,'name':info['name'],'levels':lv_str,'dir':d,'inds':ind,'weight':info.get('weight',1),'category':cat,'display':f"{emoji} {t} | {lv_str} {d}背離 [{ind}] | {info['name']}"})
    return m

def detect_conflicts(sigs):
    b={}
    for s in sigs: b.setdefault(s['ticker'],[]).append(s)
    c=[]
    for t,its in b.items():
        lt=[i for i in its if i['level'] in ('M','W','D') and i['dir']=='頂']; lb=[i for i in its if i['level'] in ('M','W','D') and i['dir']=='底']
        ht=[i for i in its if i['level']=='4H' and i['dir']=='頂']; hb=[i for i in its if i['level']=='4H' and i['dir']=='底']
        if lt and hb: lv=lt[0]['level']; c.append(f"⚠️ {t} | {lv}頂背離 但 4H底背離 | {ALL[t]['name']} – 長空短多")
        if lb and ht: lv=lb[0]['level']; c.append(f"⚠️ {t} | {lv}底背離 但 4H頂背離 | {ALL[t]['name']} – 長多短空")
    return c

# 方案2：只計DIF分數，J完全不計分
def analyze(mg):
    tech=cycle=index=0
    for s in mg:
        if 'DIF' not in s['inds']: continue # 冇DIF就唔計分，J不算
        w={'M':s.get('weight',1),'W':2,'D':1,'4H':0.5}[s['levels']]
        if s['category']=='科技': tech+=w
        elif s['category']=='週期': cycle+=w
        if s['category']=='指數': index+=w
    risk=int(tech+cycle+index)
    if risk>=13: rating='末日級別'; ops=['清倉','做空 ES/NQ','買入國債、黃金']
    elif risk>=8: rating='系統風險'; ops=['科技股減倉','SMH止損']
    elif risk>=5: rating='高風險'; ops=['控制倉位']
    else: rating='震盪市'; ops=['維持現有倉位']
    trig=[s['name'] for s in mg if s['category']=='指數' and 'DIF' in s['inds']][:9]
    return risk,int(tech),int(cycle),int(index),rating,ops,trig

def build_text(r,te,cy,ix,ra,op,tr,mg,cf):
    now=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    L=[f"Radar V14.8 背離雷達 | {now} HKT","="*50,f"風險評級 : {ra}",f"總分 : {r} (科技{te} / 週期{cy} / 指數{ix})","",""]
    for o in op: L.append(f"- {o}")
    L.append(""); L.append(f"({len(tr)}個)"); L.append(", ".join(tr))
    if cf: L.append(""); L.append("長短週期打架"); L+=cf
    L.append("="*50)
    mw=[m for m in mg if m['levels']=='M' or m['levels']=='W']; d=[m for m in mg if m['levels']=='D']; h=[m for m in mg if m['levels']=='4H']
    for m in sorted(mw,key=lambda x:x['weight'],reverse=True): L.append(m['display'])
    if d: L+=["","-"*50,""]+[m['display'] for m in sorted(d,key=lambda x:x['weight'],reverse=True)]
    if h: L+=["","-"*50,""]+[m['display'] for m in sorted(h,key=lambda x:x['weight'],reverse=True)]
    L.append(""); L.append("="*50)
    return "\n".join(L)

def save_csv(mg,ns):
    p=f"/tmp/radar_{ns}.csv"
    with open(p,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f); w.writerow(['Ticker','名稱','時段','方向','指標','權重','類別'])
        for m in mg: w.writerow([m['ticker'],m['name'],m['levels'],m['dir']+'背離',m['inds'],m['weight'],m['category']])
    return p

def send_email(sub,body,csv,merged):
    text_html = f'<div style="text-align:center;font-family:Consolas,monospace;white-space:pre-wrap;line-height:1.6;">{body}</div>'
    rows = ''.join([f"<tr><td>{m['ticker']}</td><td>{m['name']}</td><td>{m['levels']}</td><td>{m['dir']}</td><td>{m['inds']}</td><td>{m['category']}</td></tr>" for m in merged])
    table_html = f"""<div style="text-align:center;margin-top:30px;"><table style="margin:auto;border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px;"><tr style="background:#2c3e50;color:white;"><th>Ticker</th><th>名稱</th><th>時段</th><th>方向</th><th>指標</th><th>類別</th></tr>{rows}</table></div>"""
    msg=MIMEMultipart('mixed'); msg['Subject']=sub; msg['From']=EMAIL_CONFIG['sender_email']; msg['To']=EMAIL_CONFIG['receiver_email']
    msg.attach(MIMEText(text_html+table_html,'html','utf-8'))
    with open(csv,'rb') as f: att=MIMEApplication(f.read(),_subtype='csv'); att.add_header('Content-Disposition','attachment',filename=os.path.basename(csv)); msg.attach(att)
    s=smtplib.SMTP(EMAIL_CONFIG['smtp_server'],EMAIL_CONFIG['smtp_port']); s.starttls(); s.login(EMAIL_CONFIG['sender_email'],EMAIL_CONFIG['sender_password']); s.send_message(msg); s.quit()

def main():
    try:
        sigs=[];
        for t,i in ALL.items(): sigs+=scan_asset(t,i)
        mg=merge_signals(sigs); cf=detect_conflicts(sigs); r,te,cy,ix,ra,op,tr=analyze(mg) # 用mg計分
        body=build_text(r,te,cy,ix,ra,op,tr,mg,cf); ns=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M')
        csv=save_csv(mg,ns)
        send_email(f"[Radar V14.8] Risk{r} {ra} - {ns[:8]}",body,csv,mg)
        print("✅ V14.8已發送，只計DIF+最長週期")
    except Exception as e:
        print(f"❌ 錯誤: {e}"); traceback.print_exc()
        try: send_email("[Radar] 執行失敗",str(e),__file__,[])
        except: pass

if __name__=='__main__': main()