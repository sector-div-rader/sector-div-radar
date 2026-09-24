# radar_v14.2.py - 前高前底 + 分數建議 + 日線虛線
import yfinance as yf
import os
import pandas as pd
import requests
import smtplib
import time
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from supabase import create_client

EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com', 'smtp_port': 587,
    'sender_email': os.environ.get('EMAIL_USER'),
    'sender_password': os.environ.get('EMAIL_PASS'),
    'receiver_email': os.environ.get('EMAIL_TO', os.environ.get('EMAIL_USER'))
}

INDICES = {
    'ES=F': {'name':'標普500期貨', 'sticker':'📈', 'weight':5, 'index':'SPX', 'etf':'SPY'},
    'NQ=F': {'name':'納指100期貨', 'sticker':'📱', 'weight':5, 'index':'NDX', 'etf':'QQQ'},
    'YM=F': {'name':'道指期貨', 'sticker':'🏛️', 'weight':3, 'index':'DJI', 'etf':'DIA'},
}
SECTORS = {
    'XLE': {'name':'美股石油天然氣', 'sticker':'🛢️', 'weight':2, 'index':'SPX'},
    'KBE': {'name':'美股銀行', 'sticker':'🏦', 'weight':2, 'index':'SPX'},
    'SMH': {'name':'美股半導體', 'sticker':'💾', 'weight':3, 'index':'NDX'},
    'IGV': {'name':'美股軟件服務', 'sticker':'💿', 'weight':3, 'index':'NDX'},
    'IBB': {'name':'美股生物技術', 'sticker':'🧬', 'weight':1, 'index':'SPX'},
    'ITA': {'name':'美股航太國防', 'sticker':'✈️', 'weight':1, 'index':'SPX'},
    'XLP': {'name':'美股必需消費', 'sticker':'🛒', 'weight':1, 'index':'SPX'},
    'CARZ': {'name':'美股汽車', 'sticker':'🚗', 'weight':2, 'index':'SPX'},
    'XLB': {'name':'美股原材料', 'sticker':'🧪', 'weight':2, 'index':'SPX'},
    'XLU': {'name':'美股公用事業', 'sticker':'💡', 'weight':1, 'index':'SPX'},
    'XLRE': {'name':'美股地產', 'sticker':'🏠', 'weight':2, 'index':'SPX'},
    'XLC': {'name':'美股通訊服務', 'sticker':'📡', 'weight':2, 'index':'NDX'},
    'BOTZ': {'name':'美股AI人工智能', 'sticker':'🤖', 'weight':3, 'index':'NDX'},
    'WCLD': {'name':'美股雲計算', 'sticker':'☁️', 'weight':3, 'index':'NDX'},
    'HACK': {'name':'美股網絡安全', 'sticker':'🔒', 'weight':2, 'index':'NDX'},
}
FUTURES = {
    'GC=F': {'name':'黃金期貨', 'sticker':'🥇', 'index':'GOLD'},
    'SI=F': {'name':'白銀期貨', 'sticker':'🥈', 'index':'SILVER'},
    'CL=F': {'name':'原油期貨', 'sticker':'⛽', 'index':'OIL'},
    'DX-Y.NYB': {'name':'美元指數', 'sticker':'💵', 'index':'DXY'},
    'ZN=F': {'name':'十年國債', 'sticker':'📜', 'index':'BOND'},
    '^VIX': {'name':'恐慌指數', 'sticker':'😱', 'index':'VIX'},
}
ALL = {**INDICES, **SECTORS, **FUTURES}

def get_dif(df): return df['Close'].ewm(12).mean() - df['Close'].ewm(26).mean()
def get_j(df):
    rsv = (df['Close']-df['Low'].rolling(9).min())/(df['High'].rolling(9).max()-df['Low'].rolling(9).min())*100
    k = rsv.ewm(com=2).mean(); d = k.ewm(com=2).mean()
    return 3*k-2*d

def find_div(price, ind):
    p, i = price.dropna(), ind.dropna()
    idx = p.index.intersection(i.index)
    p, i = p.loc[idx], i.loc[idx]
    if len(p) < 10: return None
    # 前高
    highs = p[(p.shift(1)<p)&(p.shift(-1)<p)]
    if len(highs)>=2:
        h1,h2 = highs.index[-2], highs.index[-1]
        if p[h2]>p[h1] and i[h2]<i[h1]: return '頂'
    lows = p[(p.shift(1)>p)&(p.shift(-1)>p)]
    if len(lows)>=2:
        l1,l2 = lows.index[-2], lows.index[-1]
        if p[l2]<p[l1] and i[l2]>i[l1]: return '底'
    return None

def scan(ticker, info):
    sigs=[]; etf=info.get('etf',ticker)
    for lv,(itv,per) in [('M',('1mo','5y')),('W',('1wk','2y')),('D',('1d','1y')),('4H',('1h','3mo'))]:
        df = yf.Ticker(etf).history(period=per, interval=itv)
        if len(df)<50: continue
        for name,fn in [('DIF',get_dif),('J',get_j)]:
            div = find_div(df['Close'], fn(df))
            if div: sigs.append({**info,'ticker':ticker,'level':lv,'dir':div,'ind':name})
    return sigs

def merge(sigs):
    grouped={}
    for s in sigs: grouped.setdefault((s['ticker'],s['dir']), []).append(s)
    msgs=[]
    for (t,d), items in grouped.items():
        info=items[0]
        levels={}
        for it in items: levels.setdefault(it['ind'],[]).append(it['level'])
        for k in levels: levels[k]='+'.join(sorted(levels[k], key=lambda x:{'4H':1,'D':2,'W':3,'M':4}[x]))
        all_lv = sorted(set(sum([v.split('+') for v in levels.values()],[])), key=lambda x:{'4H':1,'D':2,'W':3,'M':4}[x])
        lv_str = '+'.join(all_lv)
        ind_str = '+'.join(sorted(levels.keys()))
        emoji = '🗓️' if 'M' in lv_str else '📅' if 'W' in lv_str else '⚠️' if 'D' in lv_str else '💾'
        # 日線加虛線
        prefix = '--- ' if 'D' in lv_str and 'W' not in lv_str and 'M' not in lv_str else ''
        msgs.append(f"{prefix}{emoji} {info['sticker']} {t} {lv_str}{d}背離[{ind_str}] - {info['name']}")
    return sorted(msgs, key=lambda x: ('🗓️' in x, '📅' in x, '⚠️' in x, '💾' in x), reverse=True)

def analyze(sigs):
    tech=cycle=index=0
    t_tickers=set(); c_tickers=set(); i_tickers=set()
    for s in sigs:
        w = {'M':s.get('weight',1), 'W':2, 'D':1, '4H':0.5}[s['level']]
        if s['index']=='NDX': tech+=w; t_tickers.add(s['ticker'])
        elif s['index']=='SPX': cycle+=w; c_tickers.add(s['ticker'])
        if s['index'] in ['SPX','NDX','DJI']: index+=w; i_tickers.add(s['ticker'])
    risk=int(tech+cycle+index)
    advice=[]
    if risk>=13:
        advice=[f"💀 末日級別 總分{risk} 科技{int(tech)} 週期{int(cycle)} 指數{int(index)}",
                "操作：清倉、做空ES/NQ、買國債黃金",
                f"觸發：{', '.join([ALL[t]['name'] for t in i_tickers])}"]
    elif risk>=8:
        advice=[f"🚨 系統風險 總分{risk} 科技{int(tech)} 週期{int(cycle)}",
                "操作：科技股減倉、SMH止損"]
    elif risk>=5:
        advice=[f"⚠️ 高風險 總分{risk}", "操作：控制倉位"]
    else: advice=[f"📊 風險分數 總分{risk}", "震盪市"]
    return risk, int(tech), int(cycle), int(index), advice

def main():
    all_sigs=[]
    for t,i in ALL.items(): all_sigs+=scan(t,i)
    msgs = merge(all_sigs)
    risk,tech,cyc,idx,advice = analyze(all_sigs)
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%m-%d %H:%M')

    # ntfy 第一條：總結
    summary = f"Radar V14.2 {now}\n\n" + "\n".join(advice)
    requests.post("https://ntfy.sh/sector-radar-ivan117", data=summary.encode('utf-8'),
        headers={"Title": f"💀 Risk{risk}".encode('utf-8'), "Priority": "high"}, timeout=10)
    time.sleep(1)
    # ntfy 第二條：明細（日線有虛線）
    detail = "信號明細\n\n" + "\n".join(msgs)
    requests.post("https://ntfy.sh/sector-radar-ivan117", data=detail.encode('utf-8'),
        headers={"Title": "📊 明細".encode('utf-8')}, timeout=10)

    # Email
    if EMAIL_CONFIG['sender_email']:
        html = "<br>".join(advice + ["<hr>"] + msgs).replace('--- ','<hr style="border:1px dashed #ccc">')
        m = MIMEMultipart(); m['Subject']=f"V14.2 Risk{risk} - {now}"; m['From']=EMAIL_CONFIG['sender_email']; m['To']=EMAIL_CONFIG['receiver_email']
        m.attach(MIMEText(html,'html','utf-8'))
        try:
            s=smtplib.SMTP(EMAIL_CONFIG['smtp_server'],587); s.starttls()
            s.login(EMAIL_CONFIG['sender_email'],EMAIL_CONFIG['sender_password']); s.send_message(m); s.quit()
        except Exception as e: print(e)
    print(summary+"\n\n"+detail)

if __name__=='__main__': main()