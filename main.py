# main.py - V14.6 (保留V14.5邏輯，只換send_email+main)
import yfinance as yf
import os, csv, smtplib, traceback
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

# === EMAIL 設定 ===
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com', 'smtp_port': 587,
    'sender_email': os.environ.get('EMAIL_USER'),
    'sender_password': os.environ.get('EMAIL_PASS'),
    'receiver_email': os.environ.get('EMAIL_TO', os.environ.get('EMAIL_USER'))
}

# === 資產清單 (V14.5原裝) ===
INDICES = {'ES=F':{'name':'標普500期貨','weight':5,'index':'SPX','etf':'SPY'},'NQ=F':{'name':'納指100期貨','weight':5,'index':'NDX','etf':'QQQ'},'YM=F':{'name':'道指期貨','weight':3,'index':'DJI','etf':'DIA'}}
SECTORS = {'XLE':{'name':'美股石油天然氣','weight':2,'index':'SPX'},'KBE':{'name':'美股銀行','weight':2,'index':'SPX'},'SMH':{'name':'美股半導體','weight':3,'index':'NDX'},'IGV':{'name':'美股軟件服務','weight':3,'index':'NDX'},'IBB':{'name':'美股生物技術','weight':1,'index':'SPX'},'ITA':{'name':'美股航太國防','weight':1,'index':'SPX'},'XLP':{'name':'美股必需消費','weight':1,'index':'SPX'},'CARZ':{'name':'美股汽車','weight':2,'index':'SPX'},'XLB':{'name':'美股原材料','weight':2,'index':'SPX'},'XLU':{'name':'美股公用事業','weight':1,'index':'SPX'},'XLRE':{'name':'美股地產','weight':2,'index':'SPX'},'XLC':{'name':'美股通訊服務','weight':2,'index':'NDX'},'BOTZ':{'name':'美股AI人工智能','weight':3,'index':'NDX'},'WCLD':{'name':'美股雲計算','weight':3,'index':'NDX'},'HACK':{'name':'美股網絡安全','weight':2,'index':'NDX'}}
FUTURES = {'GC=F':{'name':'黃金期貨','index':'GOLD'},'SI=F':{'name':'白銀期貨','index':'SILVER'},'CL=F':{'name':'原油期貨','index':'OIL'},'DX-Y.NYB':{'name':'美元指數','index':'DXY'},'ZN=F':{'name':'十年國債','index':'BOND'},'^VIX':{'name':'恐慌指數','index':'VIX'}}
ALL = {**INDICES, **SECTORS, **FUTURES}

# === V14.5 原裝 function (保留) ===
def get_dif(df): return df['Close'].ewm(span=12,adjust=False).mean() - df['Close'].ewm(span=26,adjust=False).mean()
def get_j(df):
    low9=df['Low'].rolling(9).min(); high9=df['High'].rolling(9).max()
    rsv=(df['Close']-low9)/(high9-low9)*100; k=rsv.ewm(com=2,adjust=False).mean(); d=k.ewm(com=2,adjust=False).mean(); return 3*k-2*d
def find_div(p,i):
    p,i=p.dropna(),i.dropna(); idx=p.index.intersection(i.index); p,i=p.loc[idx],i.loc[idx]
    if len(p)<10: return None
    highs=p[(p.shift(1)<p)&(p.shift(-1)<p)]
    if len(highs)>=2 and highs.index[-1]>highs.index[-2] and p.iloc[-1]>p.iloc[-2] and i.iloc[-1]<i.iloc[-2]: return '頂'
    lows=p[(p.shift(1)>p)&(p.shift(-1)>p)]
    if len(lows)>=2 and lows.index[-1]>lows.index[-2] and p.iloc[-1]<p.iloc[-2] and i.iloc[-1]>i.iloc[-2]: return '底'
    return None
def scan_asset(t,info):
    sigs=[]; etf=info.get('etf',t)
    for lv,(itv,per) in [('M',('1mo','5y')),('W',('1wk','2y')),('D',('1d','1y')),('4H',('1h','3mo'))]:
        try:
            df=yf.Ticker(etf).history(period=per,interval=itv)
            if len(df)<50: continue
            for n,f in [('DIF',get_dif),('J',get_j)]:
                d=find_div(df['Close'],f(df))
                if d: sigs.append({**info,'ticker':t,'level':lv,'dir':d,'ind':n})
        except: pass
    return sigs
def merge_signals(sigs):
    g={};
    for s in sigs: g.setdefault((s['ticker'],s['dir']),[]).append(s)
    m=[]
    for (t,d),its in g.items():
        info=its[0]; lv=set([x['level'] for x in its]); ind=set([x['ind'] for x in its])
        m.append({'ticker':t,'name':info['name'],'levels':'+'.join(sorted(lv,key=lambda x:{'4H':1,'D':2,'W':3,'M':4}[x])),'dir':d,'inds':'+'.join(sorted(ind)),'weight':info.get('weight',1),'category':'科技' if info['index']=='NDX' else '週期' if info['index']=='SPX' else '商品'})
    return m
def detect_conflicts(sigs): return [] # V14.5 原裝簡化
def analyze(sigs):
    mg=merge_signals(sigs); r=len(mg); te=len([x for x in mg if x['category']=='科技']); cy=len([x for x in mg if x['category']=='週期']); ix=len([x for x in mg if '期貨' in x['name']]); ra='偏多' if sum(1 for x in mg if x['dir']=='底')>sum(1 for x in mg if x['dir']=='頂') else '偏空'; return r,te,cy,ix,ra,'-','-'
def build_text(r,te,cy,ix,ra,op,tr,mg,cf):
    now=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    lines=[f"Radar V14.6 | {now} HKT",f"風險總分: {r} | 科技:{te} 週期:{cy} 指數:{ix} | 方向:{ra}",""]
    for m in sorted(mg,key=lambda x:x['weight'],reverse=True): lines.append(f"{m['ticker']} | {m['levels']} {m['dir']}背離 [{m['inds']}] | {m['name']}")
    return "\n".join(lines)
def save_csv(mg,ns):
    p=f"/tmp/radar_{ns}.csv"
    with open(p,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f); w.writerow(['Ticker','名稱','時段','方向','指標','類別'])
        for m in mg: w.writerow([m['ticker'],m['name'],m['levels'],m['dir'],m['inds'],m['category']])
    return p

# === 新 send_email (置中+HTML表) ===
def send_email(sub, body, csv, merged):
    text_html = f'<div style="text-align:center;font-family:Consolas,monospace;white-space:pre-wrap;line-height:1.6;">{body}</div>'
    rows = ''.join([f"<tr><td>{m['ticker']}</td><td>{m['name']}</td><td>{m['levels']}</td><td>{m['dir']}</td><td>{m['inds']}</td><td>{m['category']}</td></tr>" for m in merged])
    table_html = f"""<div style="text-align:center;margin-top:30px;"><table style="margin:auto;border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px;"><tr style="background:#2c3e50;color:white;"><th>Ticker</th><th>名稱</th><th>時段</th><th>方向</th><th>指標</th><th>類別</th></tr>{rows}</table></div>"""
    msg = MIMEMultipart('mixed'); msg['Subject']=sub; msg['From']=EMAIL_CONFIG['sender_email']; msg['To']=EMAIL_CONFIG['receiver_email']
    msg.attach(MIMEText(text_html+table_html,'html','utf-8'))
    with open(csv,'rb') as f: att=MIMEApplication(f.read(),_subtype='csv'); att.add_header('Content-Disposition','attachment',filename=os.path.basename(csv)); msg.attach(att)
    s=smtplib.SMTP(EMAIL_CONFIG['smtp_server'],EMAIL_CONFIG['smtp_port']); s.starttls(); s.login(EMAIL_CONFIG['sender_email'],EMAIL_CONFIG['sender_password']); s.send_message(msg); s.quit()

# === 新 main (有錯誤捕捉) ===
def main():
    try:
        sigs=[];
        for t,i in ALL.items(): sigs+=scan_asset(t,i)
        mg=merge_signals(sigs); cf=detect_conflicts(sigs)
        r,te,cy,ix,ra,op,tr=analyze(sigs)
        body=build_text(r,te,cy,ix,ra,op,tr,mg,cf)
        ns=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M')
        csv=save_csv(mg,ns)
        send_email(f"[Radar V14.6] Risk{r} {ra} - {ns[:8]}",body,csv,mg)
        print("✅ Email已發送")
    except Exception as e:
        print(f"❌ 錯誤: {e}"); traceback.print_exc()
        try: send_email("[Radar] 執行失敗",str(e),__file__,[])
        except: pass

if __name__=='__main__': main()