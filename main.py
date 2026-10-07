# main.py - NQ 0DTE 終極全功能晨報腳本 V16.1
# 改動：
#   - M/W/D/4H 全部用 scipy find_peaks（放棄 Fractal+ATR）
#   - recent_window: M=3 W=4 D=7 4H=7
#   - J filter: >70 / <30
#   - prominence_pct: M=5.0 W=3.0 D=1.5 4H=0.8
#   - EMA 補 800/900
#   - EMA3500 用 5m
#   - Email 中文喺前 + 分區
#   - 戰術判斷加科技板塊（NQ/SMH/IGV/XLC）

import yfinance as yf
import os, smtplib, traceback
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from scipy.signal import find_peaks

EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': os.environ.get('EMAIL_USER'),
    'sender_password': os.environ.get('EMAIL_PASS'),
    'receiver_email': os.environ.get('EMAIL_TO', os.environ.get('EMAIL_USER'))
}

TECH_TICKERS = ['NQ=F', 'SMH', 'IGV', 'XLC']

ALL_TARGETS = {
    'NQ=F':       {'name':'納斯達克100期貨','sticker':'📱','weight':5,'category':'TECH'},
    'ES=F':       {'name':'標普500期貨',   'sticker':'📈','weight':4,'category':'INDEX'},
    'YM=F':       {'name':'道瓊斯工業期貨','sticker':'🏛️','weight':4,'category':'INDEX'},
    '^VIX':       {'name':'恐慌指數',      'sticker':'😱','weight':3,'category':'INDEX'},
    'GC=F':       {'name':'黃金期貨',      'sticker':'🥇','weight':3,'category':'MACRO'},
    'CL=F':       {'name':'原油期貨',      'sticker':'🛢️','weight':3,'category':'MACRO'},
    'DX-Y.NYB':   {'name':'美元指數',      'sticker':'💵','weight':3,'category':'MACRO'},
    '^TNX':       {'name':'美債10年收益率','sticker':'📊','weight':3,'category':'MACRO'},
    'SMH':        {'name':'半導體ETF',     'sticker':'💾','weight':4,'category':'TECH'},
    'IGV':        {'name':'軟件服務ETF',   'sticker':'💿','weight':3,'category':'TECH'},
    'XLC':        {'name':'通訊服務ETF',   'sticker':'📡','weight':3,'category':'TECH'},
    'XLY':        {'name':'非必需消費ETF', 'sticker':'🛍️','weight':3,'category':'CYCLICAL'},
    'XLF':        {'name':'金融板塊ETF',   'sticker':'🏦','weight':3,'category':'CYCLICAL'},
    'XLE':        {'name':'能源板塊ETF',   'sticker':'⚡','weight':3,'category':'CYCLICAL'},
    'XLI':        {'name':'工業板塊ETF',   'sticker':'⚙️','weight':3,'category':'CYCLICAL'},
    'XLV':        {'name':'醫療保健ETF',   'sticker':'🏥','weight':2,'category':'DEFENSIVE'},
    'XLP':        {'name':'必需消費ETF',   'sticker':'🛒','weight':2,'category':'DEFENSIVE'},
    'XLU':        {'name':'公用事業ETF',   'sticker':'💡','weight':2,'category':'DEFENSIVE'},
}

# ==================== 指標 ====================

def calculate_custom_indicators(df):
    close = df['Close']
    high = df['High']
    low = df['Low']

    ema50   = close.ewm(span=50, adjust=False).mean()
    ema700  = close.ewm(span=700, adjust=False).mean() if len(df) >= 700 else pd.Series(index=df.index, dtype=float)
    ema800  = close.ewm(span=800, adjust=False).mean() if len(df) >= 800 else pd.Series(index=df.index, dtype=float)
    ema900  = close.ewm(span=900, adjust=False).mean() if len(df) >= 900 else pd.Series(index=df.index, dtype=float)
    ema1000 = close.ewm(span=1000, adjust=False).mean() if len(df) >= 1000 else pd.Series(index=df.index, dtype=float)
    ema3500 = close.ewm(span=3500, adjust=False).mean() if len(df) >= 3500 else pd.Series(index=df.index, dtype=float)

    ema5 = close.ewm(span=5, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema5 - ema26

    low9 = low.rolling(9).min()
    high9 = high.rolling(9).max()
    rsv = (close - low9) / (high9 - low9) * 100
    rsv = rsv.fillna(50)
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d

    return pd.DataFrame({
        'Close': close, 'High': high, 'Low': low, 'DIF': dif, 'J': j,
        'EMA50': ema50, 'EMA700': ema700, 'EMA800': ema800,
        'EMA900': ema900, 'EMA1000': ema1000, 'EMA3500': ema3500
    })

# ==================== scipy pivots（所有週期統一）====================

def scipy_pivots(series, prominence_pct=1.5, distance=3):
    if len(series) < 20:
        return [], []
    prominence = series.mean() * prominence_pct / 100
    highs, _ = find_peaks(series.values, prominence=prominence, distance=distance)
    lows, _ = find_peaks(-series.values, prominence=prominence, distance=distance)
    return list(highs), list(lows)

# ==================== 背離判斷 ====================

def check_divergence(p_s, i_s, highs, lows, last_idx, recent_window):
    top_div = None
    bot_div = None

    recent_highs = [h for h in highs if last_idx - h <= recent_window]
    if recent_highs:
        h2 = recent_highs[-1]
        prev_highs = [h for h in highs if h < h2]
        if prev_highs:
            h1 = max(prev_highs, key=lambda x: p_s.iloc[x])
            if p_s.iloc[h2] > p_s.iloc[h1] and i_s.iloc[h2] < i_s.iloc[h1]:
                top_div = {'dist': last_idx - h2, 'strength': i_s.iloc[h1] - i_s.iloc[h2]}

    recent_lows = [l for l in lows if last_idx - l <= recent_window]
    if recent_lows:
        l2 = recent_lows[-1]
        prev_lows = [l for l in lows if l < l2]
        if prev_lows:
            l1 = min(prev_lows, key=lambda x: p_s.iloc[x])
            if p_s.iloc[l2] < p_s.iloc[l1] and i_s.iloc[l2] > i_s.iloc[l1]:
                bot_div = {'dist': last_idx - l2, 'strength': i_s.iloc[l2] - i_s.iloc[l1]}

    if top_div and bot_div:
        if top_div['dist'] != bot_div['dist']:
            return '頂' if top_div['dist'] < bot_div['dist'] else '底'
        return '頂' if top_div['strength'] > bot_div['strength'] else '底'
    if top_div: return '頂'
    if bot_div: return '底'
    return None

# ==================== 掃描 ====================

def scan_asset(t, info):
    sigs = []
    config = [
        ('M',  '1mo', '5y',  60, {'prominence_pct':5.0, 'distance':2, 'recent_window':3}),
        ('W',  '1wk', '3y',  100, {'prominence_pct':3.0, 'distance':2, 'recent_window':4}),
        ('D',  '1d',  '6mo', 30,  {'prominence_pct':1.5, 'distance':3, 'recent_window':7}),
        ('4H', '1h',  '60d', 60,  {'prominence_pct':0.8, 'distance':3, 'recent_window':7}),
    ]

    for lv, itv, per, lb, params in config:
        try:
            raw_df = yf.Ticker(t).history(period=per, interval=itv)

            if lv == '4H' and not raw_df.empty:
                raw_df = raw_df.resample('4h').agg({
                    'Open':'first','High':'max','Low':'min',
                    'Close':'last','Volume':'sum'
                }).dropna()

            if len(raw_df) < 40:
                continue

            calc_df = calculate_custom_indicators(raw_df)
            p_s = calc_df['Close']
            last_idx = len(calc_df) - 1

            highs, lows = scipy_pivots(
                p_s,
                prominence_pct=params['prominence_pct'],
                distance=params['distance']
            )
            rw = params['recent_window']

            # DIF 背離
            d_dif = check_divergence(p_s, calc_df['DIF'], highs, lows, last_idx, rw)
            if d_dif:
                sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_dif, 'ind': 'DIF'})

            # J 背離（>70 / <30）
            curr_j = calc_df['J'].iloc[-1]
            d_j = check_divergence(p_s, calc_df['J'], highs, lows, last_idx, rw)
            if d_j:
                if d_j == '頂' and curr_j > 70:
                    sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_j, 'ind': 'J'})
                elif d_j == '底' and curr_j < 30:
                    sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_j, 'ind': 'J'})

        except Exception as e:
            print(f"[scan_asset] {t} {lv} 失敗: {e}")

    return sigs

# ==================== 風險評分 ====================

def calculate_detailed_risk_score(sigs):
    level_weights = {'M': 4.0, 'W': 4.0, 'D': 2.5, '4H': 1.5}
    level_priority = {'M': 4, 'W': 3, 'D': 2, '4H': 1}

    ticker_max_sigs = {}
    for s in sigs:
        t = s['ticker']
        new_prio = level_priority.get(s['level'], 0)
        if t not in ticker_max_sigs:
            ticker_max_sigs[t] = {'max_lvl_prio': new_prio, 'sigs': [s]}
        else:
            cur = ticker_max_sigs[t]['max_lvl_prio']
            if new_prio > cur:
                ticker_max_sigs[t] = {'max_lvl_prio': new_prio, 'sigs': [s]}
            elif new_prio == cur:
                ticker_max_sigs[t]['sigs'].append(s)

    tech_score = cyclical_score = defensive_score = 0.0
    for t, data in ticker_max_sigs.items():
        max_sigs = data['sigs']
        dif_sig = next((s for s in max_sigs if s['ind'] == 'DIF'), None)
        target = dif_sig if dif_sig else max_sigs[0]

        base_w = ALL_TARGETS.get(t, {}).get('weight', 3)
        lvl_w = level_weights.get(target['level'], 1.5)
        cat = ALL_TARGETS.get(t, {}).get('category', 'CYCLICAL')
        score_item = base_w * lvl_w

        if cat == 'TECH': tech_score += score_item * 1.5
        elif cat == 'DEFENSIVE': defensive_score += score_item * 0.8
        else: cyclical_score += score_item * 1.0

    total = round(tech_score + cyclical_score + defensive_score, 1)

    if total >= 35: rating = "🚨🚨 極高轉折/變盤風險"
    elif total >= 22: rating = "🚨 高轉折風險"
    elif total >= 12: rating = "⚠️ 中度波動風險"
    elif total >= 5: rating = "🟢 低風險/偏趨勢"
    else: rating = "🟢🟢 極低風險"

    breakdown = (f"總分: {total} | 科技: {round(tech_score,1)} / "
                 f"週期宏觀: {round(cyclical_score,1)} / "
                 f"防禦: {round(defensive_score,1)}")
    return rating, breakdown

# ==================== 日曆 ====================

def get_today_calendar_events():
    now_hkt = datetime.now(timezone(timedelta(hours=8)))
    wd = now_hkt.weekday()
    events = []
    if wd == 3: events.append("20:30 HKT | 🇺🇸 美國初請失業金人數")
    elif wd == 4: events.append("20:30 HKT | 🇺🇸 美國核心 PCE / 耐久財訂單")
    events.append("21:30 HKT | 🔔 美股常規盤開盤")
    events.append("22:00 HKT | 🇺🇸 密歇根消費者信心 / ISM PMI (若有)")

    lines = ["📅 【今晚 0DTE 關鍵日曆】："]
    for ev in events: lines.append(f"   * {ev}")
    lines.extend([
        "",
        "🛡️ 【風控鐵律】：",
        "   1. 數據前 15 分鐘：平 15s/1m 短線倉",
        "   2. 數據後 15 分鐘：待 EMA 帶定型再入場"
    ])
    return "\n".join(lines)

# ==================== 隔夜數據 ====================

def get_overnight_and_key_levels():
    try:
        def h(sym): return yf.Ticker(sym).history(period='5d', interval='1d')
        nq, es, ym = h('NQ=F'), h('ES=F'), h('YM=F')
        vix, gc, cl = h('^VIX'), h('GC=F'), h('CL=F')
        dxy, tnx = h('DX-Y.NYB'), h('^TNX')

        def pct(a, b): return ((a - b) / b) * 100
        def c(x): return x['Close'].iloc[-1]
        def p(x): return x['Close'].iloc[-2]

        header = "\n".join([
            "🌐 隔夜與宏觀數據：",
            f"   * 指數: NQ {c(nq):,.1f} ({pct(c(nq),p(nq)):+.2f}%) | ES {c(es):,.1f} ({pct(c(es),p(es)):+.2f}%) | YM {c(ym):,.1f} ({pct(c(ym),p(ym)):+.2f}%) | VIX {c(vix):.1f} ({pct(c(vix),p(vix)):+.2f}%)",
            f"   * 大宗: 黃金 ${c(gc):,.1f} ({pct(c(gc),p(gc)):+.2f}%) | 原油 ${c(cl):.2f} ({pct(c(cl),p(cl)):+.2f}%)",
            f"   * 宏觀: 美指 {c(dxy):.2f} ({pct(c(dxy),p(dxy)):+.2f}%) | 10年美債 {c(tnx):.3f}% ({pct(c(tnx),p(tnx)):+.2f}%)"
        ])

        high_p = nq['High'].iloc[-2]
        low_p = nq['Low'].iloc[-2]
        close_p = nq['Close'].iloc[-2]
        pivot = (high_p + low_p + close_p) / 3.0
        r1 = 2 * pivot - low_p
        s1 = 2 * pivot - high_p

        levels = "\n".join([
            "📍 NQ=F 今晚 0DTE 核心戰術卡位：",
            f"   * 5日強阻力 : {nq['High'].max():,.1f}",
            f"   * R1 第一壓力: {r1:,.1f}",
            f"   * Pivot 中軸 : {pivot:,.1f}  (昨收: {close_p:,.1f})",
            f"   * S1 第一支撐: {s1:,.1f}",
            f"   * 5日強支撐 : {nq['Low'].min():,.1f}"
        ])
        return header, levels
    except Exception as e:
        return "🌐 隔夜數據失敗", "📍 Key Levels 失敗"

# ==================== NQ 5m EMA 帶 ====================

def get_nq_custom_chart_status():
    try:
        raw_df = yf.Ticker('NQ=F').history(period='1mo', interval='5m')
        if raw_df.empty or len(raw_df) < 100:
            return "NQ 5m 數據獲取失敗"

        calc_df = calculate_custom_indicators(raw_df)
        last = calc_df.iloc[-1]
        price = last['Close']

        lines = [
            "🛡️ 【NQ 5m EMA 700-1000 帶 & 3500 監測】：",
            f"   * 現價 : {price:.1f}"
        ]

        band_vals = [v for v in [last['EMA700'], last['EMA800'], last['EMA900'], last['EMA1000']] if not np.isnan(v)]
        if len(band_vals) >= 2:
            band_top, band_bot = max(band_vals), min(band_vals)
            w_pts = band_top - band_bot
            w_pct = (w_pts / price) * 100

            if w_pct < 0.15:
                status = f"🚨 【帶內極度黏合】({w_pts:.1f}點 / {w_pct:.2f}%)"
                hint = "籌碼極度集中！突破易爆單邊強趨勢。"
            elif w_pct > 0.60:
                status = f"⚠️ 【帶內寬幅發散】({w_pts:.1f}點 / {w_pct:.2f}%)"
                hint = "動能發散，留意背離見好即收。"
            else:
                status = f"🟢 【常態帶寬】({w_pts:.1f}點 / {w_pct:.2f}%)"
                hint = "按 15s/1m 貼身線與背離正常操作。"

            lines.append(f"   * 📍 5m EMA 700-1000 帶 : {band_bot:.1f} - {band_top:.1f}")
            lines.append(f"     └─ {status}")

            if not np.isnan(last['EMA3500']):
                e3500 = last['EMA3500']
                lines.append(f"   * 🏛️ 5m EMA 3500 : {e3500:.1f}")
                if e3500 > band_top: cross = "🚨 3500 在帶上方 (長線壓制)"
                elif e3500 < band_bot: cross = "🟢 3500 在帶下方 (標準多頭)"
                else: cross = "⚡ 3500 穿越/嵌入帶 (極易洗盤！)"
                lines.append(f"     └─ {cross}")
            else:
                lines.append("   * 🏛️ 5m EMA 3500 : 數據不足")
            lines.append(f"   🎯 {hint}")

        return "\n".join(lines)
    except Exception as e:
        return f"5m 均線帶失敗: {e}"

# ==================== 訊號分組（中文喺前）====================

def process_and_group_signals(sigs):
    grouped = {}
    conflicts = []
    level_order = {'4H': 1, 'D': 2, 'W': 3, 'M': 4}

    for s in sigs:
        t = s['ticker']
        key = (t, s['dir'], s['ind'])
        if key not in grouped:
            grouped[key] = {
                'ticker': t, 'name': s['name'], 'sticker': s.get('sticker', ''),
                'dir': s['dir'], 'ind': s['ind'], 'levels': []
            }
        grouped[key]['levels'].append(s['level'])

    big_picture = []
    tonight = []
    ticker_dirs = {}

    for key, data in grouped.items():
        t, direction, ind = key
        if t not in ticker_dirs:
            ticker_dirs[t] = set()
        ticker_dirs[t].add(direction)

        sorted_lvls = sorted(set(data['levels']), key=lambda x: level_order.get(x, 99))
        lvl_str = "+".join(sorted_lvls)

        line = f"{data['sticker']} {data['name']} ({t}) | {lvl_str} {direction}背離 [{ind}]"

        if any(lv in ['M', 'W'] for lv in data['levels']):
            big_picture.append(line)
        if any(lv in ['D', '4H'] for lv in data['levels']):
            tonight.append(line)

    for t, dirs in ticker_dirs.items():
        if '頂' in dirs and '底' in dirs:
            name = ALL_TARGETS.get(t, {}).get('name', t)
            conflicts.append(f"⚡ {name} ({t}) 同時出現「頂背離 + 底背離」！劇烈震盪洗盤，建議觀望。")

    return big_picture, tonight, conflicts

# ==================== Email ====================

def build_email_body(sigs):
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    overnight_str, levels_str = get_overnight_and_key_levels()
    nq_status = get_nq_custom_chart_status()
    calendar_str = get_today_calendar_events()

    big_picture, tonight, conflicts = process_and_group_signals(sigs)
    rating, breakdown = calculate_detailed_risk_score(sigs)

    # 戰術（科技板塊）
    tech_4h_top = [s for s in sigs if s['ticker'] in TECH_TICKERS and s['level'] == '4H' and s['dir'] == '頂']
    tech_4h_bot = [s for s in sigs if s['ticker'] in TECH_TICKERS and s['level'] == '4H' and s['dir'] == '底']
    big_top = [s for s in sigs if s['level'] in ['W', 'M'] and s['dir'] == '頂']

    if tech_4h_top:
        tactics = "🎯 今晚戰術：科技板塊 4H 頂背離！開盤拉高無力可搵 Put (嚴禁追 Call)。"
    elif tech_4h_bot:
        tactics = "🎯 今晚戰術：科技板塊 4H 底背離！開盤急跌可搵 Call。"
    else:
        tactics = "🟢 今晚戰術：無 4H 轉折訊號，結合 5m EMA 帶形態即市操作。"

    macro_bg = "🏛️ 大勢背景：週/月線大頂背離中！做 Put 爆發力大。" if big_top else \
               "🏛️ 大勢背景：大週期結構常態，順應日內動能。"

    sep = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    L = [
        f"⚡ Radar V16.1 0DTE 全宏觀晨報 | {now} HKT",
        sep,
        "🏛️ 大勢背景（月 / 週線）",
        sep,
    ]
    L.extend(big_picture if big_picture else ["   🟢 月/週線暫無顯著背離"])
    L.append("   " + macro_bg)

    L.extend([sep, "🎯 今晚操作（日 / 4H）", sep])
    L.extend(tonight if tonight else ["   🟢 日/4H 暫無顯著背離"])
    L.append("   " + tactics)

    L.extend([sep, "📊 隔夜與宏觀", sep, overnight_str])
    L.extend([sep, "📍 NQ 關鍵位", sep, levels_str])
    L.extend([sep, "🛡️ 5m EMA 帶監測", sep, nq_status])
    L.extend([sep, "📅 今晚日曆", sep, calendar_str])

    if conflicts:
        L.extend([sep, "🔥 多空衝突警告", sep])
        for c in conflicts: L.append(f"   * {c}")

    L.extend([sep, f"整體風險評級 : {rating}", f"📊 拆解 : {breakdown}", sep])
    return "\n".join(L)

# ==================== 主程式 ====================

def main():
    try:
        print(f"=== 掃描 {len(ALL_TARGETS)} 個標的 ===", flush=True)
        sigs = []
        for t, info in ALL_TARGETS.items():
            result = scan_asset(t, info)
            if result:
                print(f"  {t}: {len(result)} 個訊號", flush=True)
            sigs += result

        print(f"=== 總共 {len(sigs)} 個訊號 ===", flush=True)
        body = build_email_body(sigs)

        msg = MIMEMultipart()
        msg['Subject'] = f"⚡ [0DTE 雷達 V16.1] 三大期指與跨資產宏觀戰術地圖 ({datetime.now().strftime('%m/%d')})"
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = EMAIL_CONFIG['receiver_email']
        msg.attach(MIMEText(
            f"<pre style='font-family:Consolas,Menlo,monospace;font-size:14px;background:#f8f9fa;padding:15px;'>{body}</pre>",
            'html', 'utf-8'
        ))

        s = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        s.starttls()
        s.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        s.send_message(msg)
        s.quit()
        print("✅ 晨報已發送", flush=True)
    except Exception as e:
        print(f"❌ 失敗: {e}", flush=True)
        traceback.print_exc()

if __name__ == '__main__':
    main()
