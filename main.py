# radar_v15.24_0dte.py - QQQ 末日期權 (0DTE) 早上 9 點定時戰術版
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

# 聚焦科技股與核心大盤
INDICES = {
    'NQ=F': {'name':'納指100期貨','sticker':'📱','weight':5,'index':'NDX','etf':'QQQ'},
    'ES=F': {'name':'標普500期貨','sticker':'📈','weight':5,'index':'SPX','etf':'SPY'},
    'YM=F': {'name':'道指期貨','sticker':'🏛️','weight':2,'index':'DJI','etf':'DIA'},
}
SECTORS = {
    'SMH':{'name':'美股半導體(核心)','sticker':'💾','weight':4,'index':'NDX'},
    'IGV':{'name':'美股軟件服務','sticker':'💿','weight':3,'index':'NDX'},
    'BOTZ':{'name':'美股AI概念','sticker':'🤖','weight':3,'index':'NDX'},
    'WCLD':{'name':'美股雲計算','sticker':'☁️','weight':2,'index':'NDX'},
    'HACK':{'name':'美股網絡安全','sticker':'🔒','weight':2,'index':'NDX'},
    'XLC':{'name':'美股通訊服務','sticker':'📡','weight':2,'index':'NDX'},
    'KBE':{'name':'美股銀行','sticker':'🏦','weight':1,'index':'SPX'},
    'XLE':{'name':'美股石油','sticker':'🛢️','weight':1,'index':'SPX'},
}
FUTURES = {
    'DX-Y.NYB':{'name':'美元指數','sticker':'💵','index':'DXY'},
    '^VIX':{'name':'恐慌指數','sticker':'😱','index':'VIX'},
    'ZN=F':{'name':'十年國債','sticker':'📜','index':'BOND'},
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
    rsv = rsv.fillna(50)
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

def find_div_0dte(p, i, lookback=80, n=5):
    """
    0DTE 專用背離邏輯：
    1. 專注已收盤確認的 Pivot，避開盤中未定型雜訊。
    2. 容許微幅破位/假突破 (1.5%)。
    """
    df = pd.DataFrame({'price': p, 'ind': i}).dropna().tail(lookback)
    if len(df) < n * 2 + 5:
        return None

    p_s = df['price']
    i_s = df['ind']

    highs = pivothigh(p_s, n=n)
    lows = pivotlow(p_s, n=n)

    # 頂背離 (Bearish)
    if len(highs) >= 2:
        h1, h2 = highs[-2], highs[-1]
        if p_s.iloc[h2] >= p_s.iloc[h1] * 0.985 and i_s.iloc[h2] < i_s.iloc[h1]:
            return '頂'

    # 底背離 (Bullish)
    if len(lows) >= 2:
        l1, l2 = lows[-2], lows[-1]
        if p_s.iloc[l2] <= p_s.iloc[l1] * 1.015 and i_s.iloc[l2] > i_s.iloc[l1]:
            return '底'

    return None

def scan_asset(t, info):
    sigs = []
    etf = info.get('etf', t)
    
    # 0DTE 時框配置：
    # 4H (n=4): 專攻今晚至明晚戰術轉折 (~2天)
    # 日線 (n=5): 鎖定上一週 Swing (~1星期)
    # 週/月 (n=3,2): 鎖定宏觀大多/大空局勢
    config = [
        ('M',  ('1mo', '5y',  60), 2),
        ('W',  ('1wk', '3y', 100), 3),
        ('D',  ('1d',  '6mo', 30), 5),
        ('4H', ('1h',  '60d', 60), 4)
    ]
    
    for lv, (itv, per, lb), n in config:
        try:
            df = yf.Ticker(etf).history(period=per, interval=itv)
            if len(df) < 40:
                continue
            
            # 1. DIF 背離
            dif_series = get_dif(df)
            d_dif = find_div_0dte(df['Close'], dif_series, lookback=lb, n=n)
            if d_dif:
                sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_dif, 'ind': 'DIF'})

            # 2. J 值背離 (嚴格過濾：超買 > 80，超賣 < 20)
            j_series = get_j(df)
            curr_j = j_series.iloc[-1]
            d_j = find_div_0dte(df['Close'], j_series, lookback=lb, n=n)
            
            if d_j:
                if d_j == '頂' and curr_j > 80:
                    sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_j, 'ind': 'J'})
                elif d_j == '底' and curr_j < 20:
                    sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_j, 'ind': 'J'})

        except Exception as e:
            print(f"{t}-{lv}出錯: {e}")
            pass
            
    return sigs

def merge_signals(sigs):
    g = {}
    for s in sigs:
        g.setdefault((s['ticker'], s['dir']), []).append(s)
        
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
        emoji = '🚨' if t in ['NQ=F', 'QQQ', 'SMH'] else '🗓️' if 'M' in lv_str else '📅' if 'W' in lv_str else '⚠️' if 'D' in lv_str else '💾'
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
        b.setdefault(s['ticker'], []).append(s)
        
    c = []
    for t, its in b.items():
        lt = [i for i in its if i['level'] in ('M', 'W', 'D') and i['dir'] == '頂']
        lb = [i for i in its if i['level'] in ('M', 'W', 'D') and i['dir'] == '底']
        ht = [i for i in its if i['level'] == '4H' and i['dir'] == '頂']
        hb = [i for i in its if i['level'] == '4H' and i['dir'] == '底']
        
        if lt and hb:
            lv = '+'.join(sorted(set([i['level'] for i in lt]), key=lambda x: {'M': 1, 'W': 2, 'D': 3}[x], reverse=True))
            c.append(f"⚠️ {t} | {lv}頂背離 但 4H底背離 | {ALL[t]['name']} – 長空短多 (今晚忌盲目追空)")
        if lb and ht:
            lv = '+'.join(sorted(set([i['level'] for i in lb]), key=lambda x: {'M': 1, 'W': 2, 'D': 3}[x], reverse=True))
            c.append(f"⚠️ {t} | {lv}底背離 但 4H頂背離 | {ALL[t]['name']} – 長多短空 (今晚忌盲目追多)")
    return c

def generate_0dte_actionable_advice(sigs, conflicts):
    """專門為 0DTE 生成今晚開盤行動建議"""
    nq_sigs = [s for s in sigs if s['ticker'] in ['NQ=F', 'QQQ', 'SMH']]
    nq_4h_top = [s for s in nq_sigs if s['level'] == '4H' and s['dir'] == '頂']
    nq_4h_bot = [s for s in nq_sigs if s['level'] == '4H' and s['dir'] == '底']
    
    macro_top = [s for s in sigs if s['level'] in ['W', 'M'] and s['dir'] == '頂' and s['ticker'] in ['NQ=F', 'ES=F']]
    macro_bot = [s for s in sigs if s['level'] in ['W', 'M'] and s['dir'] == '底' and s['ticker'] in ['NQ=F', 'ES=F']]
    
    advice = []
    if conflicts:
        advice.append("⚠️ 【今晚戰術】：長短週期打架！末期權兩邊洗盤風險高，建議縮減注碼 50%。")
    elif nq_4h_top:
        advice.append("🎯 【今晚戰術】：NQ/QQQ/SMH 出現 4H 頂背離！今晚開盤拉高無力可尋找 Put 機會 (嚴禁追 Call)。")
    elif nq_4h_bot:
        advice.append("🎯 【今晚戰術】：NQ/QQQ/SMH 出現 4H 底背離！今晚開盤急跌可尋找 Call 爆發點 (嚴禁追 Put)。")
    else:
        advice.append("🟢 【今晚戰術】：4H 無直接轉折訊號，順著日線/週線大局方向操作。")
        
    if macro_top:
        advice.append("🏛️ 【大局背景】：週/月線處於大頂背離中！今晚若做 Put 爆發力極大，勝率與盈虧比偏高。")
    elif macro_bot:
        advice.append("🏛️ 【大局背景】：週/月線處於大底背離中！大盤中線有強支撐，跌穿多為假突破。")
        
    return advice

def build_text(r, te, cy, ix, ra, op, tr, mg, cf, sigs):
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    advice = generate_0dte_actionable_advice(sigs, cf)
    
    L = [f"⚡ Radar V15.24 0DTE 早報 | {now} HKT", "="*50]
    L += advice
    L += ["="*50, f"整體風險評級 : {ra} (分數:{r} | 科技{te} / 週期{cy} / 指數{ix})", ""]
    
    if cf:
        L.append("⚔️ 長短週期衝突警告：")
        L += cf
        L.append("")

    # 優先排列 QQQ / NQ / SMH 訊號
    tech_core = [m for m in mg if m['ticker'] in ['NQ=F', 'QQQ', 'SMH']]
    others = [m for m in mg if m['ticker'] not in ['NQ=F', 'QQQ', 'SMH']]
    
    if tech_core:
        L.append("🔥 【QQQ / NQ / 半導體 核心警報】")
        for m in tech_core:
            L.append(m['display'])
        L.append("-" * 50)
        
    L.append("📊 【其他板塊與指數訊號】")
    for m in sorted(others, key=lambda x: x['weight'], reverse=True):
        L.append(m['display'])
        
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
    text_html = f'<div style="text-align:left;font-family:Consolas,monospace;white-space:pre-wrap;line-height:1.6;font-size:14px;background:#f9f9f9;padding:15px;border-radius:8px;">{body}</div>'
    rows = ''.join([f"<tr><td>{m['ticker']}</td><td>{m['name']}</td><td>{m['levels']}</td><td>{m['dir']}</td><td>{m['inds']}</td><td>{m['category']}</td></tr>" for m in merged])
    table_html = f"""<div style="text-align:center;margin-top:25px;"><table style="margin:auto;border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px;width:90%;"><tr style="background:#1a252f;color:white;"><th>Ticker</th><th>名稱</th><th>時段</th><th>方向</th><th>指標</th><th>類別</th></tr>{rows}</table></div>"""
    
    msg = MIMEMultipart('mixed')
    msg['Subject'] = sub
    msg['From'] = EMAIL_CONFIG['sender_email']
    msg['To'] = EMAIL_CONFIG['receiver_email']
    msg.attach(MIMEText(text_html + table_html, 'html', 'utf-8'))
    
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
        r, te, cy, ix, ra, op, tr = analyze_0dte(sigs) # 使用 0DTE 導向評估
        
        body = build_text(r, te, cy, ix, ra, op, tr, mg, cf, sigs)
        ns = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M')
        csv_path = save_csv(mg, ns)
        
        # 標題直接顯示今晚重點，方便在手機通知欄一眼看懂
        tech_4h = [s for s in sigs if s['ticker'] in ['NQ=F', 'QQQ', 'SMH'] and s['level'] == '4H']
        status_tag = f"[{tech_4h[0]['ticker']} {tech_4h[0]['level']}{tech_4h[0]['dir']}背離]" if tech_4h else f"[{ra}]"
        
        send_email(f"⚡ [0DTE 雷達 09:00] {status_tag} Risk{r} - {ns[:8]}", body, csv_path, mg)
        print("✅ V15.24 0DTE 晨報已成功發送 (09:00 HKT 專用)")
    except Exception as e:
        print(f"❌ 執行失敗: {e}")
        traceback.print_exc()
        try:
            send_email("[Radar] 腳本執行失敗", f"錯誤詳情:\n{e}\n\n{traceback.format_exc()}", None, [])
        except:
            pass

def analyze_0dte(sigs):
    tech = cycle = index = 0
    g = {}
    for s in sigs:
        if s['ind'] != 'DIF':
            continue
        g.setdefault((s['ticker'], s['dir']), []).append(s)
        
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
    if risk >= 12:
        rating = '極高轉折風險'
    elif risk >= 7:
        rating = '中高轉折風險'
    elif risk >= 4:
        rating = '溫和波動'
    else:
        rating = '趨勢延續/震盪'
        
    ops = []
    trig = []
    return risk, int(tech), int(cycle), int(index), rating, ops, trig

if __name__ == '__main__':
    main()
