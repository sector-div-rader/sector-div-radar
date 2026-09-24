# radar_v14.3.py - 最終版：前高前底 + 純文字Email + CSV
import yfinance as yf
import os
import pandas as pd
import smtplib
import csv
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

# ========== 設定 ==========
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
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

def get_dif(df):
    return df['Close'].ewm(span=12, adjust=False).mean() - df['Close'].ewm(span=26, adjust=False).mean()

def get_j(df):
    low9 = df['Low'].rolling(9).min()
    high9 = df['High'].rolling(9).max()
    rsv = (df['Close'] - low9) / (high9 - low9) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    return 3 * k - 2 * d

def find_div(price, ind):
    p = price.dropna()
    i = ind.dropna()
    idx = p.index.intersection(i.index)
    p, i = p.loc[idx], i.loc[idx]
    if len(p) < 10:
        return None
    # 前高
    highs = p[(p.shift(1) < p) & (p.shift(-1) < p)]
    if len(highs) >= 2:
        h1, h2 = highs.index[-2], highs.index[-1]
        if p[h2] > p[h1] and i[h2] < i[h1]:
            return '頂'
    # 前低
    lows = p[(p.shift(1) > p) & (p.shift(-1) > p)]
    if len(lows) >= 2:
        l1, l2 = lows.index[-2], lows.index[-1]
        if p[l2] < p[l1] and i[l2] > i[l1]:
            return '底'
    return None

def scan_asset(ticker, info):
    sigs = []
    etf = info.get('etf', ticker)
    for level, (interval, period) in [('M', ('1mo', '5y')), ('W', ('1wk', '2y')), ('D', ('1d', '1y')), ('4H', ('1h', '3mo'))]:
        try:
            df = yf.Ticker(etf).history(period=period, interval=interval)
            if len(df) < 50:
                continue
            for name, func in [('DIF', get_dif), ('J', get_j)]:
                div = find_div(df['Close'], func(df))
                if div:
                    sigs.append({**info, 'ticker': ticker, 'level': level, 'dir': div, 'ind': name})
        except Exception:
            continue
    return sigs

def merge_signals(sigs):
    grouped = {}
    for s in sigs:
        key = (s['ticker'], s['dir'])
        grouped.setdefault(key, []).append(s)

    merged = []
    for (t, d), items in grouped.items():
        info = items[0]
        levels_by_ind = {}
        for it in items:
            levels_by_ind.setdefault(it['ind'], []).append(it['level'])
        for ind in levels_by_ind:
            levels_by_ind[ind] = '+'.join(sorted(levels_by_ind[ind], key=lambda x: {'4H':1,'D':2,'W':3,'M':4}[x]))
        all_lv = sorted(set(sum([v.split('+') for v in levels_by_ind.values()], [])), key=lambda x: {'4H':1,'D':2,'W':3,'M':4}[x])
        lv_str = '+'.join(all_lv)
        ind_str = '+'.join(sorted(levels_by_ind.keys()))
        emoji = '🗓️' if 'M' in lv_str else '📅' if 'W' in lv_str else '⚠️' if 'D' in lv_str else '💾'
        category = '科技' if info['index']=='NDX' else '週期' if info['index']=='SPX' else '指數'
        merged.append({
            'ticker': t, 'name': info['name'], 'levels': lv_str, 'dir': d,
            'inds': ind_str, 'weight': info.get('weight',1), 'category': category,
            'display': f"{emoji} {t} | {lv_str} {d}背離 [{ind_str}] | {info['name']}"
        })
    return merged

def analyze_risk(sigs):
    tech = cycle = index = 0
    t_set = set(); c_set = set(); i_set = set()
    for s in sigs:
        w = {'M': s.get('weight',1), 'W':2, 'D':1, '4H':0.5}[s['level']]
        if s['index'] == 'NDX':
            tech += w; t_set.add(s['ticker'])
        elif s['index'] == 'SPX':
            cycle += w; c_set.add(s['ticker'])
        if s['index'] in ['SPX','NDX','DJI']:
            index += w; i_set.add(s['ticker'])
    risk = int(tech + cycle + index)
    if risk >= 13:
        rating = '末日級別'; ops = ['清倉', '做空 ES/NQ', '買入國債、黃金']
    elif risk >= 8:
        rating = '系統風險'; ops = ['科技股減倉', 'SMH止損']
    elif risk >= 5:
        rating = '高風險'; ops = ['控制倉位']
    else:
        rating = '震盪市'; ops = ['維持現有倉位']
    triggers = [ALL[t]['name'] for t in list(i_set)[:9]]
    return risk, int(tech), int(cycle), int(index), rating, ops, triggers

def build_text(risk, tech, cyc, idx, rating, ops, triggers, merged):
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    lines = []
    lines.append(f"Radar V14.3 背離雷達 | {now} HKT")
    lines.append("="*50)
    lines.append(f"風險評級 : {rating}")
    lines.append(f"總分 : {risk} (科技{tech} / 週期{cyc} / 指數{idx})")
    lines.append("")
    lines.append("【操作建議】")
    for o in ops:
        lines.append(f"- {o}")
    lines.append("")
    lines.append(f"【觸發資產】({len(triggers)}個)")
    lines.append(", ".join(triggers))
    lines.append("="*50)

    m_w = [m for m in merged if 'M' in m['levels'] or 'W' in m['levels']]
    d_only = [m for m in merged if 'D' in m['levels'] and 'M' not in m['levels'] and 'W' not in m['levels']]
    h4_only = [m for m in merged if '4H' in m['levels'] and 'D' not in m['levels'] and 'M' not in m['levels'] and 'W' not in m['levels']]

    for m in sorted(m_w, key=lambda x: x['weight'], reverse=True):
        lines.append(m['display'])
    if d_only:
        lines.append("")
        lines.append("-"*50)
        lines.append("")
        for m in sorted(d_only, key=lambda x: x['weight'], reverse=True):
            lines.append(m['display'])
    if h4_only:
        lines.append("")
        lines.append("-"*50)
        lines.append("")
        for m in sorted(h4_only, key=lambda x: x['weight'], reverse=True):
            lines.append(m['display'])
    lines.append("")
    lines.append("="*50)
    return "\n".join(lines)

def save_csv(merged, now_str):
    path = f"/tmp/radar_{now_str.replace('-','').replace(' ','_').replace(':','')}.csv"
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['Ticker','名稱','時段','方向','指標','權重','類別'])
        for m in merged:
            w.writerow([m['ticker'], m['name'], m['levels'], m['dir']+'背離', m['inds'], m['weight'], m['category']])
    return path

def send_email(subject, body, csv_path):
    if not EMAIL_CONFIG['sender_email']:
        print("Email未設定"); return
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = EMAIL_CONFIG['sender_email']
    msg['To'] = EMAIL_CONFIG['receiver_email']
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    with open(csv_path, 'rb') as f:
        part = MIMEApplication(f.read(), _subtype='csv')
        part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(csv_path))
        msg.attach(part)
    s = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
    s.starttls()
    s.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
    s.send_message(msg)
    s.quit()

def main():
    all_sigs = []
    for t, i in ALL.items():
        all_sigs += scan_asset(t, i)

    merged = merge_signals(all_sigs)
    risk, tech, cyc, idx, rating, ops, triggers = analyze_risk(all_sigs)
    body = build_text(risk, tech, cyc, idx, rating, ops, triggers, merged)

    now_str = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d_%H%M')
    csv_path = save_csv(merged, now_str)

    subject = f"[Radar V14.3] Risk{risk} {rating} - {now_str[:10]}"
    send_email(subject, body, csv_path)
    print(body)
    print(f"\nCSV已儲存: {csv_path}")

if __name__ == '__main__':
    main()