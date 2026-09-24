# radar_v15.23.py - 靈敏雙軌背離+即時偵測版，參數4H=6, D=5, W=3, M=2
import yfinance as yf
import os, csv, smtplib, traceback
import pandas as pd
import numpy as np
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

def get_dif(df):
    ema5 = df['Close'].ewm(span=5, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    return ema5 - ema26

def get_j(df):
    low9 = df['Low'].rolling(9).min()
    high9 = df['High'].rolling(9).max()
    rsv = (df['Close'] - low9) / (high9 - low9) * 100
    rsv = rsv.fillna(50)  # 防止除以 0 產生 NaN
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    return 3 * k - 2 * d

def pivothigh(series, n):
    highs = []
    vals = series.values
    for i in range(n, len(vals) - n):
        if all(vals[i] > vals[i-n:i]) and all(vals[i] > vals[i+1:i+n+1]):
            highs.append(i)
    return np.array(highs)

def pivotlow(series, n):
    lows = []
    vals = series.values
    for i in range(n, len(vals) - n):
        if all(vals[i] < vals[i-n:i]) and all(vals[i] < vals[i+1:i+n+1]):
            lows.append(i)
    return np.array(lows)

def find_div_advanced(p, i, lookback=100, n=5):
    """
    升級版雙軌背離偵測：
    1. 修正數據對齊問題
    2. 支援「即時價格 vs 上一個 Pivot」零延遲偵測
    3. 支援「結構性 Pivot vs Pivot」背離比對
    """
    df = pd.DataFrame({'price': p, 'ind': i}).dropna().tail(lookback)
    if len(df) < n * 2 + 5:
        return None

    p_s = df['price']
    i_s = df['ind']

    highs = pivothigh(p_s, n=n)
    lows = pivotlow(p_s, n=n)

    curr_p = p_s.iloc[-1]
    curr_i = i_s.iloc[-1]

    # ---------------- 頂背離檢測 (Bearish) ----------------
    # 模式 A：最新現價即時突破上一頂，但指標跟唔上 (零延遲)
    if len(highs) >= 1:
        last_h = highs[-1]
        if curr_p >= p_s.iloc[last_h] * 0.995 and curr_i < i_s.iloc[last_h]:
            return '頂'

    # 模式 B：最後兩個已確認的 Pivot 形成背離 (結構性)
    if len(highs) >= 2:
        h1, h2 = highs[-2], highs[-1]
        if p_s.iloc[h2] >= p_s.iloc[h1] * 0.98 and i_s.iloc[h2] < i_s.iloc[h1]:
            return '頂'

    # ---------------- 底背離檢測 (Bullish) ----------------
    # 模式 A：最新現價即時跌穿上一底，但指標底比底高 (零延遲)
    if len(lows) >= 1:
        last_l = lows[-1]
        if curr_p <= p_s.iloc[last_l] * 1.005 and curr_i > i_s.iloc[last_l]:
            return '底'

    # 模式 B：最後兩個已確認的 Pivot 形成背離
    if len(lows) >= 2:
        l1, l2 = lows[-2], lows[-1]
        if p_s.iloc[l2] <= p_s.iloc[l1] * 1.02 and i_s.iloc[l2] > i_s.iloc[l1]:
            return '底'

    return None

def scan_asset(t, info):
    sigs = []
    etf = info.get('etf', t)
    
    # 靈敏型時框配置 (縮小 n 值以提升捕捉效率)
    config = [
        ('M',  ('1mo', '5y',  60), 2),  # 月K: 左右2個月
        ('W',  ('1wk', '3y', 100), 3),  # 週K: 左右3週 (~半個月)
        ('D',  ('1d',  '6mo', 30), 5),  # 日K: 左右5日 (~1星期)
        ('4H', ('1h',  '60d', 60), 6)   # 4H:  左右6根 (1日)
    ]
    
    for lv, (itv, per, lb), n in config:
        try:
            df = yf.Ticker(etf).history(period=per, interval=itv)
            if len(df) < 40:
                continue
            
            # 1. 檢測 DIF (MACD) 背離
            dif_series = get_dif(df)
            d_dif = find_div_advanced(df['Close'], dif_series, lookback=lb, n=n)
            if d_dif:
                sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_dif, 'ind': 'DIF'})

            # 2. 檢測 J 值背離 (加入超買超賣過濾，排除中軸無效訊號)
            j_series = get_j(df)
            curr_j = j_series.iloc[-1]
            d_j = find_div_advanced(df['Close'], j_series, lookback=lb, n=n)
            
            if d_j:
                if '頂' in d_j and curr_j > 60:
                    sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_j, 'ind': 'J'})
                elif '底' in d_j and curr_j < 40:
                    sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_j, 'ind': 'J'})

        except Exception as e:
            print(f"{t}-{lv}出錯: {e}")
            pass
            
    return sigs

def merge_signals(sigs):
    g = {}
    for s in sigs:
        # 清理方向，統一以 '頂' 或 '底' 歸類
        clean_dir = '頂' if '頂' in s['dir'] else '底'
        g.setdefault((s['ticker'], clean_dir), []).append(s)
        
    m = []
    for (t, d), its in g.items():
        info = its[0]
        lv = {}
        for it in its:
            lv.setdefault(it['ind'], []).append(it['level'])
        for k in lv:
            lv[k] = '+'.join(sorted(set(lv[k]), key=lambda x: {'4H': 1, 'D': 2, 'W': 3, 'M': 4}[x], reverse=True))
        all_lv = sorted(set(sum([v.split('+') for v in lv.values()], [])), key=lambda x: {'4H': 1, 'D': 2, 'W': 3, 'M': 4}[x], reverse=True)
        lv_str = '+'.join(all_lv)
        ind = '+'.join(sorted(lv.keys()))
        emoji = '🗓️' if 'M' in lv_str else '📅' if 'W' in lv_str else '⚠️' if 'D' in lv_str else '💾'
        cat = '科技' if info['index'] == 'NDX' else '週期' if info['index'] == 'SPX' else '指數'
        m.append({
            'ticker': t,
            'name': info['name'],
            'levels': lv_str,
            'dir': d,
            'inds': ind,
            'weight': info.get('weight', 1),
            'category': cat,
            'display': f"{emoji} {t} | {lv_str} {d}背離 [{ind}] | {info['name']}"
        })
    return m

def detect_conflicts(sigs):
    b = {}
    for s in sigs:
        clean_dir = '頂' if '頂' in s['dir'] else '底'
        s_copy = {**s, 'clean_dir': clean_dir}
        b.setdefault(s['ticker'], []).append(s_copy)
        
    c = []
    for t, its in b.items():
        lt = [i for i in its if i['level'] in ('M', 'W', 'D') and i['clean_dir'] == '頂']
        lb = [i for i in its if i['level'] in ('M', 'W', 'D') and i['clean_dir'] == '底']
        ht = [i for i in its if i['level'] == '4H' and i['clean_dir'] == '頂']
        hb = [i for i in its if i['level'] == '4H' and i['clean_dir'] == '底']
        
        if lt and hb:
            lv = '+'.join(sorted(set([i['level'] for i in lt]), key=lambda x: {'M': 1, 'W': 2, 'D': 3}[x], reverse=True))
            c.append(f"⚠️ {t} | {lv}頂背離 但 4H底背離 | {ALL[t]['name']} – 長空短多")
        if lb and ht:
            lv = '+'.join(sorted(set([i['level'] for i in lb]), key=lambda x: {'M': 1, 'W': 2, 'D': 3}[x], reverse=True))
            c.append(f"⚠️ {t} | {lv}底背離 但 4H頂背離 | {ALL[t]['name']} – 長多短空")
    return c

def analyze(sigs):
    tech = cycle = index = 0
    g = {}
    for s in sigs:
        if s['ind'] != 'DIF':
            continue
        clean_dir = '頂' if '頂' in s['dir'] else '底'
        g.setdefault((s['ticker'], clean_dir), []).append(s)
        
    for (t, d), its in g.items():
        best = max(its, key=lambda x: {'M': 4, 'W': 3, 'D': 2, '4H': 1}[x['level']])
        w = {'M': best.get('weight', 1), 'W': 2, 'D': 1, '4H': 0.5}[best['level']]
        if best['index'] == 'NDX':
            tech += w
        elif best['index'] == 'SPX':
            cycle += w
        if best['index'] in ['SPX', 'NDX', 'DJI']:
            index += w
            
    risk = int(tech + cycle + index)
    if risk >= 13:
        rating = '末日級別'
        ops = ['清倉', '做空 ES/NQ', '買入國債、黃金']
    elif risk >= 8:
        rating = '系統風險'
        ops = ['科技股減倉', 'SMH止損']
    elif risk >= 5:
        rating = '高風險'
        ops = ['控制倉位']
    else:
        rating = '震盪市'
        ops = ['維持現有倉位']
        
    trig = [s['ticker'] for s in sigs if s['ind'] == 'DIF' and s['index'] in ['SPX', 'NDX', 'DJI']]
    trig = [ALL[t]['name'] for t in list(dict.fromkeys(trig))[:9]]
    return risk, int(tech), int(cycle), int(index), rating, ops, trig

def build_text(r, te, cy, ix, ra, op, tr, mg, cf):
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    L = [f"Radar V15.23 背離雷達 | {now} HKT", "="*50, f"風險評級 : {ra}", f"總分 : {r} (科技{te} / 週期{cy} / 指數{ix})", "", ""]
    for o in op:
        L.append(f"- {o}")
    L.append("")
    L.append(f"({len(tr)}個)")
    L.append(", ".join(tr))
    if cf:
        L.append("")
        L.append("長短週期打架")
        L += cf
    L.append("="*50)
    
    mw = [m for m in mg if 'M' in m['levels'] or 'W' in m['levels']]
    d = [m for m in mg if 'D' in m['levels'] and 'M' not in m['levels'] and 'W' not in m['levels']]
    h = [m for m in mg if '4H' in m['levels'] and 'D' not in m['levels'] and 'M' not in m['levels'] and 'W' not in m['levels']]
    
    for m in sorted(mw, key=lambda x: x['weight'], reverse=True):
        L.append(m['display'])
    if d:
        L += ["", "-"*50, ""] + [m['display'] for m in sorted(d, key=lambda x: x['weight'], reverse=True)]
    if h:
        L += ["", "-"*50, ""] + [m['display'] for m in sorted(h, key=lambda x: x['weight'], reverse=True)]
        
    L.append("")
    L.append("="*50)
    return "\n".join(L)

def save_csv(mg, ns):
    p = f"/tmp/radar_{ns}.csv"
    with open(p, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['Ticker', '名稱', '時段', '方向', '指標', '權重', '類別'])
        for m in mg:
            w.writerow([m['ticker'], m['name'], m['levels'], m['dir']+'背離', m['inds'], m['weight'], m['category']])
    return p

def send_email(sub, body, csv_file=None, merged=[]):
    text_html = f'<div style="text-align:center;font-family:Consolas,monospace;white-space:pre-wrap;line-height:1.6;">{body}</div>'
    rows = ''.join([f"<tr><td>{m['ticker']}</td><td>{m['name']}</td><td>{m['levels']}</td><td>{m['dir']}</td><td>{m['inds']}</td><td>{m['category']}</td></tr>" for m in merged])
    table_html = f"""<div style="text-align:center;margin-top:30px;"><table style="margin:auto;border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px;"><tr style="background:#2c3e50;color:white;"><th>Ticker</th><th>名稱</th><th>時段</th><th>方向</th><th>指標</th><th>類別</th></tr>{rows}</table></div>"""
    
    msg = MIMEMultipart('mixed')
    msg['Subject'] = sub
    msg['From'] = EMAIL_CONFIG['sender_email']
    msg['To'] = EMAIL_CONFIG['receiver_email']
    msg.attach(MIMEText(text_html + table_html, 'html', 'utf-8'))
    
    # 安全附加 CSV，避開以 .py 為附件導至 Gmail 退封
    if csv_file and os.path.exists(csv_file) and csv_file.endswith('.csv'):
        with open(csv_file, 'rb') as f:
            att = MIMEApplication(f.read(), _subtype='csv')
            att.add_header('Content-Disposition', 'attachment', filename=os.path.basename(csv_file))
            msg.attach(att)
            
    s = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
    s.starttls()
    s.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
    s.send_message(msg)
    s.quit()

def main():
    try:
        sigs = []
        for t, i in ALL.items():
            sigs += scan_asset(t, i)
            
        mg = merge_signals(sigs)
        cf = detect_conflicts(sigs)
        r, te, cy, ix, ra, op, tr = analyze(sigs)
        
        body = build_text(r, te, cy, ix, ra, op, tr, mg, cf)
        ns = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M')
        csv_path = save_csv(mg, ns)
        
        send_email(f"[Radar V15.23] Risk{r} {ra} - {ns[:8]}", body, csv_path, mg)
        print("✅ V15.23 已成功執行並發送郵件 (靈敏雙軌背離版)")
    except Exception as e:
        print(f"❌ 執行失敗: {e}")
        traceback.print_exc()
        try:
            send_email("[Radar] 腳本執行失敗報警", f"錯誤原因:\n{e}\n\n{traceback.format_exc()}", None, [])
        except Exception as mail_err:
            print(f"❌ 失敗郵件亦無法發送: {mail_err}")

if __name__ == '__main__':
    main()
