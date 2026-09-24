# radar_v15.9.py - 統一3根間隔版
import yfinance as yf
import os, csv, smtplib, traceback
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from scipy.signal import find_peaks

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

def get_dif(df):
    ema5 = df['Close'].ewm(span=5,adjust=False).mean()
    ema26 = df['Close'].ewm(span=26,adjust=False).mean()
    return ema5 - ema26

def get_j(df):
    low9=df['Low'].rolling(9).min(); high9=df['High'].rolling(9).max()
    rsv=(df['Close']-low9)/(high9-low9)*100; k=rsv.ewm(com=2,adjust=False).mean(); d=k.ewm(com=2,adjust=False).mean()
    return 3*k-2*d

def find_div(p, i, lookback=100, distance=3):
    p = p.dropna().iloc[-lookback:].copy()
    i = i.dropna().iloc[-lookback:].copy()
    idx = p.index.intersection(i.index)
    p, i = p.loc[idx], i.loc[idx]
    if len(p) < 20: return None

    peaks, _ = find_peaks(p.values, distance=distance)
    troughs, _ = find_peaks(-p.values, distance=distance)

    if len(peaks) >= 2:
        h1, h2 = peaks[-2], peaks[-1]
        if p.iloc[h2] > p.iloc[h1] and i.iloc[h2] < i.iloc[h1]:
            return '頂'

    if len(troughs) >= 2:
        l1, l2 = troughs[-2], troughs[-1]
        if p.iloc[l2] < p.iloc[l1] and i.iloc[l2] > i.iloc[l1]:
            return '底'
    return None

# 全部統一distance=3
def scan_asset(t,info):
    sigs=[]; etf=info.get('etf',t)
    config = [
        ('M', ('1mo','5y',60), 3), # 月K：3個月=1浪
        ('W', ('1wk','3y',100), 3), # 週K：3週=1浪
        ('D', ('1d','6mo',30), 3), # 日K：3日=1浪，改咗
        ('4H',('1h','60d',60), 3) # 4H：3根=12小時=1浪，改咗
    ]
    for lv,(itv,per,lb),dist in config:
        try:
            df=yf.Ticker(etf).history(period=per,interval=itv)
            if len(df)<50: continue
            for n,f in [('DIF',get_dif),('J',get_j)]:
                d=find_div(df['Close'],f(df),lookback=lb,distance=dist)
                if d: sigs.append({**info,'ticker':t,'level':lv,'dir':d,'ind':n})
        except Exception as e:
            print(f"{t}-{lv}出錯: {e}")
            pass
    return sigs

def merge_signals(sigs):
    g={}
    for s in sigs: g.setdefault((s['ticker'],s['dir']),[]).append(s)
    m=[]
    for (t,d),its in g.items():
        info=its[0]; lv={}
        for it in its: lv.setdefault(it['ind'],[]).append(it['level'])
        for k in lv: lv[k]='+'.join(sorted(lv[k],key=lambda x:{'4H':1,'D':2,'W':3,'M':4}[x],reverse=True))
        all_lv=sorted(set(sum([v.split('+') for v in lv.values()],[])),key=lambda x:{'4H':1,'D':2,'W':3,'M':4}[x],reverse=True)
        lv_str='+'.join(all_lv); ind='+'.join(sorted(lv.keys()))
        emoji='🗓️' if 'M' in lv_str else '📅' if 'W' in lv_str else '⚠️' if 'D' in lv_str else '💾'
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
        if lt and hb: lv='+'.join(sorted(set([i['level'] for i in lt]),key=lambda x:{'M':1,'W':2,'D':3}[x],reverse=True)); c.append(f"⚠️ {t} | {lv}頂背離 但 4H底背離 | {ALL[t]['name']} – 長空短多")
        if lb and ht: lv='+'.join(sorted(set([i['level'] for i in lb]),key=lambda x:{'M':1,'W':2,'D':3}[x],reverse=True)); c.append(f"⚠️ {t} | {lv}底背離 但 4H頂背離 | {ALL[t]['name']} – 長多短空")
    return c

def analyze(sigs):
    tech=cycle=index=0
    g={}
    for s in sigs:
        if s['ind']!='DIF': continue
        g.setdefault((s['ticker'],s['dir']),[]).append(s)
    for (t,d),its in g.items():
        best=max(its,key=lambda x:{'M':4,'W':3,'D':2,'4H':1}[x['level']])
        w={'M':best.get('weight',1),'W':2,'D':1,'4H':0.5}[best['level']]
        if best['index']=='NDX': tech+=w
        elif best['index']=='SPX': cycle+=w
        if best['index'] in ['SPX','NDX','DJI']: index+=w
    risk=int(tech+cycle+index)
    if risk>=13: rating='末日級別'; ops=['清倉','做空 ES/NQ','買入國債、黃金']
    elif risk>=8: rating='系統風險'; ops=['科技股減倉','SMH止損']
    elif risk>=5: rating='高風險'; ops=['控制倉位']
    else: rating='震盪市'; ops=['維持現有倉位']
    trig=[s['ticker'] for s in sigs if s['ind']=='DIF' and s['index'] in ['SPX','NDX','DJI']]
    trig=[ALL[t]['name'] for t in list(dict.fromkeys(trig))[:9]]
    return risk,int(tech),int(cycle),int(index),rating,ops,trig

def build_text(r,te,cy,ix,ra,op,tr,mg,cf):
    now=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    L=[f"Radar V15.9 背離雷達 | {now} HKT","="*50,f"風險評級 : {ra}",f"總分 : {r} (科技{te} / 週期{cy} / 指數{ix})","",""]
    for o in op: L.append(f"- {o}")
    L.append(""); L.append(f"({len(tr)}個)"); L.append(", ".join(tr))
    if cf: L.append(""); L.append("長短週期打架"); L+=cf
    L.append("="*50)
    mw=[m for m in mg if 'M' in m['levels'] or 'W' in m['levels']]
    d=[m for m in mg if 'D' in m['levels'] and 'M' not in m['levels'] and 'W' not in m['levels']]
    h=[m for m in mg if '4H' in m['levels'] and 'D' not in m['levels'] and 'M' not in m['levels'] and 'W' not in m['levels']]
    for m in sorted(mw,key=lambda x:x['weight'],reverse=True): L.append(m['display'])
    if d: L+=["","-"*50,""]+[m['display'] for m in sorted(d,key=lambda x:x['weight'],reverse=True)]
    if