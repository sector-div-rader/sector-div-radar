# radar_v14.1.py - 前高前底背離，DIF+J，合併顯示
import yfinance as yf
import os
import pandas as pd
import requests
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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

def get_dif(df):
    return df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()

def get_j(df):
    low = df['Low'].rolling(9).min()
    high = df['High'].rolling(9).max()
    rsv = (df['Close']-low)/(high-low)*100
    k = rsv.ewm(com=2).mean()
    d = k.ewm(com=2).mean()
    return 3*k - 2*d

def find_div(price, ind):
    """
    前高前底背離：搵最近2個高點/低點
    """
    p = price.dropna()
    i = ind.dropna()
    if len(p) < 10: return None

    # 搵高點
    highs = p[(p.shift(1) < p) & (p.shift(-1) < p)]
    if len(highs) >= 2:
        h1, h2 = highs.index[-2], highs.index[-1]
        if p.loc[h2] > p.loc[h1] and i.loc[h2] < i.loc[h1]:
            return '頂'
    # 搵低點
    lows = p[(p.shift(1) > p) & (p.shift(-1) > p)]
    if len(lows) >= 2:
        l1, l2 = lows.index[-2], lows.index[-1]
        if p.loc[l2] < p.loc[l1] and i.loc[l2] > i.loc[l1]:
            return '底'
    return None

def scan(ticker, info):
    sigs = []
    etf = info.get('etf', ticker)
    for lv, (itv, per) in [('M',('1mo','5y')), ('W',('1wk','2y')), ('D',('1d','1y')), ('4H',('1h','3mo'))]:
        df = yf.Ticker(etf).history(period=per, interval=itv)
        if len(df) < 50: continue
        for name, func in [('DIF', get_dif), ('J', get_j)]:
            ind = func(df)
            div = find_div(df['Close'], ind)
            if div:
                sigs.append({'ticker':ticker, **info, 'level':lv, 'dir':div, 'ind':name})
    return sigs

def merge(sigs):
    out = {}
    for s in sigs:
        key = (s['ticker'], s['dir'])
        out.setdefault(key, []).append(s)

    msgs = []
    for (t, d), items in out.items():
        info = items[0]
        # 按時段排序
        levels = {}
        for it in items:
            levels.setdefault(it['ind'], []).append(it['level'])
        for ind in levels:
            levels[ind] = '+'.join(sorted(levels[ind], key=lambda x: {'4H':1,'D':2,'W':3,'M':4}[x]))

        level_str = '+'.join(sorted(set(sum([v.split('+') for v in levels.values()], [])), key=lambda x: {'4H':1,'D':2,'W':3,'M':4}[x]))
        ind_str = '+'.join(sorted(levels.keys()))
        emoji = '🗓️' if 'M' in level_str else '📅' if 'W' in level_str else '⚠️' if 'D' in level_str else '💾'
        msgs.append(f"{emoji} {info['sticker']} {t} {level_str}{d}背離[{ind_str}] - {info['name']}")
    return msgs

def main():
    all_sigs = []
    for t,i in {**INDICES, **SECTORS, **FUTURES}.items():
        all_sigs += scan(t,i)

    msgs = merge(all_sigs)
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%m-%d %H:%M')
    body = f"Radar V14.1 {now}\n\n" + "\n".join(msgs) if msgs else "無背離"

    # ntfy
    requests.post("https://ntfy.sh/sector-radar-ivan117", data=body.encode('utf-8'),
        headers={"Title": "V14.1 背離".encode('utf-8')}, timeout=10)

    # email
    if EMAIL_CONFIG['sender_email']:
        m = MIMEMultipart()
        m['Subject'] = f"V14.1 {now}"; m['From']=EMAIL_CONFIG['sender_email']; m['To']=EMAIL_CONFIG['receiver_email']
        m.attach(MIMEText(body.replace('\n','<br>'),'html','utf-8'))
        try:
            s=smtplib.SMTP(EMAIL_CONFIG['smtp_server'],587); s.starttls()
            s.login(EMAIL_CONFIG['sender_email'],EMAIL_CONFIG['sender_password']); s.send_message(m); s.quit()
        except: pass

    print(body)

if __name__ == '__main__':
    main()