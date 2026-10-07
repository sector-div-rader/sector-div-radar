# main.py - NQ 0DTE 終極全功能晨報腳本 V16.0
# 改動：
#   - M/W 用 Fractal + ATR
#   - D/4H 用 scipy find_peaks
#   - 頂底同時計，揀最近 + 最強
#   - 加 recent_window（過濾舊訊號）
#   - EMA 補 800 / 900
#   - EMA3500 用 5m interval
#   - Email 分區 + 中英對齊
#   - 唔加 VWAP / 量能

import yfinance as yf
import os, smtplib, traceback, time
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

# ==================== 標的清單 ====================
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

# ==================== 技術指標計算 ====================

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

    # MACD DIF (5/26)
    ema5 = close.ewm(span=5, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema5 - ema26

    # KDJ - J
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

# ==================== 方法 1：Fractal + ATR（M / W）====================

def fractal_atr_pivots(df, n=3, atr_mult=2.0, atr_period=14):
    """Fractal + ATR pivot 偵測（用於長週期）"""
    high, low, close = df['High'], df['Low'], df['Close']

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(atr_period).mean()

    highs, lows = [], []
    for i in range(n, len(close) - n):
        window = close.iloc[i-n:i+n+1]
        center = close.iloc[i]
        others = window.drop(close.index[i])
        if len(others) == 0:
            continue

        atr_val = atr.iloc[i]
        if pd.isna(atr_val) or atr_val == 0:
            continue

        # 頂
        if center == window.max():
            if center - others.max() >= atr_mult * atr_val:
                highs.append(i)
        # 底
        if center == window.min():
            if others.min() - center >= atr_mult * atr_val:
                lows.append(i)

    return highs, lows

# ==================== 方法 2：scipy find_peaks（D / 4H）====================

def scipy_pivots(series, prominence_pct=1.5, distance=3):
    """scipy find_peaks pivot 偵測（用於短週期）"""
    if len(series) < 20:
        return [], []
    prominence = series.mean() * prominence_pct / 100
    highs, _ = find_peaks(series.values, prominence=prominence, distance=distance)
    lows, _ = find_peaks(-series.values, prominence=prominence, distance=distance)
    return list(highs), list(lows)

# ==================== 統一背離判斷邏輯 ====================

def check_divergence(p_s, i_s, highs, lows, last_idx, recent_window):
    """
    檢查背離：
      1. 只睇最近 recent_window 根內形成嘅 pivot
      2. 比較對應嘅前 pivot（最高 / 最低）
      3. 價創新高 + 指標冇 = 頂背離；反之亦然
      4. 頂底同時計，揀最近 + 最強
    """
    top_div = None
    bot_div = None

    # ===== 頂背離 =====
    recent_highs = [h for h in highs if last_idx - h <= recent_window]
    if recent_highs:
        h2 = recent_highs[-1]
        prev_highs = [h for h in highs if h < h2]
        if prev_highs:
            h1 = max(prev_highs, key=lambda x: p_s.iloc[x])
            if p_s.iloc[h2] > p_s.iloc[h1] and i_s.iloc[h2] < i_s.iloc[h1]:
                top_div = {
                    'dist': last_idx - h2,
                    'strength': i_s.iloc[h1] - i_s.iloc[h2],
                    'h1': h1, 'h2': h2
                }

    # ===== 底背離 =====
    recent_lows = [l for l in lows if last_idx - l <= recent_window]
    if recent_lows:
        l2 = recent_lows[-1]
        prev_lows = [l for l in lows if l < l2]
        if prev_lows:
            l1 = min(prev_lows, key=lambda x: p_s.iloc[x])
            if p_s.iloc[l2] < p_s.iloc[l1] and i_s.iloc[l2] > i_s.iloc[l1]:
                bot_div = {
                    'dist': last_idx - l2,
                    'strength': i_s.iloc[l2] - i_s.iloc[l1],
                    'l1': l1, 'l2': l2
                }

    # ===== 揀最近 + 最強 =====
    if top_div and bot_div:
        if top_div['dist'] != bot_div['dist']:
            return '頂' if top_div['dist'] < bot_div['dist'] else '底'
        return '頂' if top_div['strength'] > bot_div['strength'] else '底'
    if top_div: return '頂'
    if bot_div: return '底'
    return None

# ==================== 掃描單一標的 ====================

def scan_asset(t, info):
    sigs = []
    # (level, interval, period, lookback, method, params)
    config = [
        ('M',  '1mo', '5y',  60, 'fractal', {'n':3, 'atr_mult':2.0, 'recent_window':2}),
        ('W',  '1wk', '3y',  100, 'fractal', {'n':3, 'atr_mult':1.5, 'recent_window':2}),
        ('D',  '1d',  '6mo', 30,  'scipy',   {'prominence_pct':1.5, 'distance':3, 'recent_window':5}),
        ('4H', '1h',  '60d', 60,  'scipy',   {'prominence_pct':0.8, 'distance':3, 'recent_window':5}),
    ]

    for lv, itv, per, lb, method, params in config:
        try:
            raw_df = yf.Ticker(t).history(period=per, interval=itv)

            # 4H：由 1h resample
            if lv == '4H' and not raw_df.empty:
                raw_df = raw_df.resample('4h').agg({
                    'Open':'first','High':'max','Low':'min',
                    'Close':'last','Volume':'sum'
                }).dropna()

            if len(raw_df) < 40:
                print(f"[skip] {t} {lv} 數據不足 ({len(raw_df)})")
                continue

            calc_df = calculate_custom_indicators(raw_df)
            p_s = calc_df['Close']
            last_idx = len(calc_df) - 1

            # 搵 pivot
            if method == 'fractal':
                highs, lows = fractal_atr_pivots(raw_df, n=params['n'], atr_mult=params['atr_mult'])
            else:  # scipy
                highs, lows = scipy_pivots(p_s, prominence_pct=params['prominence_pct'], distance=params['distance'])

            recent_window = params['recent_window']

            # 檢查 DIF 背離
            d_dif = check_divergence(p_s, calc_df['DIF'], highs, lows, last_idx, recent_window)
            if d_dif:
                sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_dif, 'ind': 'DIF'})

            # 檢查 J 背離（加 J 值門檻）
            curr_j = calc_df['J'].iloc[-1]
            d_j = check_divergence(p_s, calc_df['J'], highs, lows, last_idx, recent_window)
            if d_j:
                if d_j == '頂' and curr_j > 75:
                    sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_j, 'ind': 'J'})
                elif d_j == '底' and curr_j < 25:
                    sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_j, 'ind': 'J'})

        except Exception as e:
            print(f"[scan_asset] {t} {lv} 失敗: {e}")

    return sigs

# ==================== 風險評分引擎 ====================

def calculate_detailed_risk_score(sigs):
    level_weights = {'M': 4.0, 'W': 4.0, 'D': 2.5, '4H': 1.5}
    level_priority = {'M': 4, 'W': 3, 'D': 2, '4H': 1}

    ticker_max_sigs = {}
    for s in sigs:
        t = s['ticker']
        lvl = s['level']
        new_prio = level_priority.get(lvl, 0)

        if t not in ticker_max_sigs:
            ticker_max_sigs[t] = {'max_lvl_prio': new_prio, 'sigs': [s]}
        else:
            current_prio = ticker_max_sigs[t]['max_lvl_prio']
            if new_prio > current_prio:
                ticker_max_sigs[t]['max_lvl_prio'] = new_prio
                ticker_max_sigs[t]['sigs'] = [s]
            elif new_prio == current_prio:
                ticker_max_sigs[t]['sigs'].append(s)

    tech_score = 0.0
    cyclical_score = 0.0
    defensive_score = 0.0

    for t, data in ticker_max_sigs.items():
        max_sigs = data['sigs']
        dif_sig = next((s for s in max_sigs if s['ind'] == 'DIF'), None)
        target_sig = dif_sig if dif_sig else max_sigs[0]

        base_w = ALL_TARGETS.get(t, {}).get('weight', 3)
        lvl_w = level_weights.get(target_sig['level'], 1.5)
        cat = ALL_TARGETS.get(t, {}).get('category', 'CYCLICAL')

        score_item = base_w * lvl_w

        if cat == 'TECH':
            tech_score += score_item * 1.5
        elif cat == 'DEFENSIVE':
            defensive_score += score_item * 0.8
        else:
            cyclical_score += score_item * 1.0

    total_score = round(tech_score + cyclical_score + defensive_score, 1)

    if total_score >= 35:
        rating = "🚨🚨 極高轉折/變盤風險 (全市場多個大週期背離)"
    elif total_score >= 22:
        rating = "🚨 高轉折風險 (核心板塊大週期背離)"
    elif total_score >= 12:
        rating = "⚠️ 中度波動風險 (局部板塊背離)"
    elif total_score >= 5:
        rating = "🟢 低風險/偏趨勢 (個別標的背離)"
    else:
        rating = "🟢🟢 極低風險 (順勢運行)"

    breakdown = (f"總分: {total_score} | 科技權重: {round(tech_score, 1)} / "
                 f"週期與宏觀: {round(cyclical_score, 1)} / "
                 f"防禦權重: {round(defensive_score, 1)}")

    return rating, breakdown

# ==================== 日曆 ====================

def get_today_calendar_events():
    now_hkt = datetime.now(timezone(timedelta(hours=8)))
    weekday = now_hkt.weekday()

    events = []
    if weekday == 3:
        events.append("20:30 HKT | 🇺🇸 美國初請失業金人數")
    elif weekday == 4:
        events.append("20:30 HKT | 🇺🇸 美國核心 PCE / 耐久財訂單")

    events.append("21:30 HKT | 🔔 美股常規盤開盤 (0DTE 流動性湧入)")
    events.append("22:00 HKT | 🇺🇸 密歇根消費者信心 / ISM PMI (若有)")

    lines = ["📅 【今晚 0DTE 關鍵日曆】："]
    for ev in events:
        lines.append(f"   * {ev}")
    lines.extend([
        "",
        "🛡️ 【風控鐵律】：",
        "   1. 數據發佈前 15 分鐘：平 15s/1m 短線倉，防插針",
        "   2. 數據後 15 分鐘：待 EMA 帶定型再入場"
    ])
    return "\n".join(lines)

# ==================== 隔夜與 Key Levels ====================

def get_overnight_and_key_levels():
    try:
        nq = yf.Ticker('NQ=F').history(period='5d', interval='1d')
        es = yf.Ticker('ES=F').history(period='5d', interval='1d')
        ym = yf.Ticker('YM=F').history(period='5d', interval='1d')
        vix = yf.Ticker('^VIX').history(period='5d', interval='1d')
        gc = yf.Ticker('GC=F').history(period='5d', interval='1d')
        cl = yf.Ticker('CL=F').history(period='5d', interval='1d')
        dxy = yf.Ticker('DX-Y.NYB').history(period='5d', interval='1d')
        tnx = yf.Ticker('^TNX').history(period='5d', interval='1d')

        nq_c, nq_p = nq['Close'].iloc[-1], nq['Close'].iloc[-2]
        es_c, es_p = es['Close'].iloc[-1], es['Close'].iloc[-2]
        ym_c, ym_p = ym['Close'].iloc[-1], ym['Close'].iloc[-2]
        vix_c, vix_p = vix['Close'].iloc[-1], vix['Close'].iloc[-2]
        gc_c, gc_p = gc['Close'].iloc[-1], gc['Close'].iloc[-2]
        cl_c, cl_p = cl['Close'].iloc[-1], cl['Close'].iloc[-2]
        dxy_c, dxy_p = dxy['Close'].iloc[-1], dxy['Close'].iloc[-2]
        tnx_c, tnx_p = tnx['Close'].iloc[-1], tnx['Close'].iloc[-2]

        def pct(a, b): return ((a - b) / b) * 100

        header_lines = [
            f"🌐 隔夜與宏觀數據：",
            f"   * 指數: NQ {nq_c:,.1f} ({pct(nq_c,nq_p):+.2f}%) | ES {es_c:,.1f} ({pct(es_c,es_p):+.2f}%) | YM {ym_c:,.1f} ({pct(ym_c,ym_p):+.2f}%) | VIX {vix_c:.1f} ({pct(vix_c,vix_p):+.2f}%)",
            f"   * 大宗: 黃金 ${gc_c:,.1f} ({pct(gc_c,gc_p):+.2f}%) | 原油 ${cl_c:.2f} ({pct(cl_c,cl_p):+.2f}%)",
            f"   * 宏觀: 美指 {dxy_c:.2f} ({pct(dxy_c,dxy_p):+.2f}%) | 10年美債 {tnx_c:.3f}% ({pct(tnx_c,tnx_p):+.2f}%)"
        ]
        header = "\n".join(header_lines)

        high_p = nq['High'].iloc[-2]
        low_p = nq['Low'].iloc[-2]
        close_p = nq['Close'].iloc[-2]

        pivot = (high_p + low_p + close_p) / 3.0
        r1 = (2 * pivot) - low_p
        s1 = (2 * pivot) - high_p
        swing_high = nq['High'].max()
        swing_low = nq['Low'].min()

        levels = [
            "📍 NQ=F 今晚 0DTE 核心戰術卡位：",
            f"   * 5日波段強阻力 : {swing_high:,.1f}",
            f"   * R1 第一壓力   : {r1:,.1f}",
            f"   * Pivot 中軸    : {pivot:,.1f}  (昨收: {close_p:,.1f})",
            f"   * S1 第一支撐   : {s1:,.1f}",
            f"   * 5日波段強支撐 : {swing_low:,.1f}"
        ]
        return header, "\n".join(levels)
    except Exception as e:
        return "🌐 隔夜數據擷取失敗", "📍 Key Levels 計算失敗"

# ==================== NQ 5m EMA 帶監測 ====================

def get_nq_custom_chart_status():
    try:
        ticker = yf.Ticker('NQ=F')
        raw_df = ticker.history(period='1mo', interval='5m')

        if raw_df.empty or len(raw_df) < 100:
            return "NQ 5m 數據獲取失敗"

        calc_df = calculate_custom_indicators(raw_df)
        last = calc_df.iloc[-1]
        price = last['Close']

        ema700, ema800, ema900, ema1000, ema3500 = (
            last['EMA700'], last['EMA800'], last['EMA900'],
            last['EMA1000'], last['EMA3500']
        )

        lines = [
            "🛡️ 【NQ 5m EMA 700-1000 帶 & 3500 監測】：",
            f"   * 現價 : {price:.1f}"
        ]

        band_vals = [v for v in [ema700, ema800, ema900, ema1000] if not np.isnan(v)]
        if len(band_vals) >= 2:
            band_top, band_bot = max(band_vals), min(band_vals)
            band_width_pts = band_top - band_bot
            band_width_pct = (band_width_pts / price) * 100

            if band_width_pct < 0.15:
                inner_status = f"🚨 【帶內極度黏合】 (帶寬 {band_width_pts:.1f} 點 / {band_width_pct:.2f}%)"
                inner_hint = "籌碼極度集中！突破易爆單邊強趨勢，可讓利潤奔跑。"
            elif band_width_pct > 0.60:
                inner_status = f"⚠️ 【帶內寬幅發散】 (帶寬 {band_width_pts:.1f} 點 / {band_width_pct:.2f}%)"
                inner_hint = "動能發散中，留意背離，見好即收。"
            else:
                inner_status = f"🟢 【常態帶寬】 (帶寬 {band_width_pts:.1f} 點 / {band_width_pct:.2f}%)"
                inner_hint = "按 15s/1m 貼身線與背離正常操作。"

            lines.append(f"   * 📍 5m EMA 700-1000 帶 : {band_bot:.1f} - {band_top:.1f}")
            lines.append(f"     └─ {inner_status}")

            if not np.isnan(ema3500):
                lines.append(f"   * 🏛️ 5m EMA 3500 : {ema3500:.1f}")
                if ema3500 > band_top:
                    cross = "🚨 3500 在帶上方 (長線壓制)"
                elif ema3500 < band_bot:
                    cross = "🟢 3500 在帶下方 (標準多頭)"
                else:
                    cross = "⚡ 3500 穿越/嵌入帶 (極易洗盤！)"
                lines.append(f"     └─ {cross}")
            else:
                lines.append("   * 🏛️ 5m EMA 3500 : 數據不足 3500 條")

            lines.append(f"   🎯 {inner_hint}")

        return "\n".join(lines)
    except Exception as e:
        return f"5m 均線帶監測失敗: {e}"

# ==================== 訊號分組 + Email 對齊 ====================

def pad_cn(s, width):
    """中文字當 2 寬，英文字當 1 寬；向左對齊補空格"""
    cn_count = sum(1 for c in s if '\u4e00' <= c <= '\u9fff')
    actual_width = len(s) + cn_count
    return s + ' ' * max(0, width - actual_width)

def process_and_group_signals(sigs):
    grouped = {}
    conflicts = []
    level_order = {'4H': 1, 'D': 2, 'W': 3, 'M': 4}

    for s in sigs:
        t = s['ticker']
        key = (t, s['dir'], s['ind'])
        if key not in grouped:
            grouped[key] = {
                'ticker': t, 'name': s['name'], 'dir': s['dir'],
                'ind': s['ind'], 'levels': []
            }
        grouped[key]['levels'].append(s['level'])

    # 分大勢 / 今晚
    big_picture = []   # M / W
    tonight = []       # D / 4H
    ticker_dirs = {}

    for key, data in grouped.items():
        t, direction, ind = key
        if t not in ticker_dirs:
            ticker_dirs[t] = set()
        ticker_dirs[t].add(direction)

        sorted_lvls = sorted(set(data['levels']), key=lambda x: level_order.get(x, 99))
        lvl_str = "+".join(sorted_lvls)

        line = f"{pad_cn(t, 12)} | {pad_cn(data['name'], 18)} | {pad_cn(lvl_str, 6)} {direction}背離 [{ind}]"

        if any(lv in ['M', 'W'] for lv in data['levels']):
            big_picture.append(line)
        if any(lv in ['D', '4H'] for lv in data['levels']):
            tonight.append(line)

    for t, dirs in ticker_dirs.items():
        if '頂' in dirs and '底' in dirs:
            name = ALL_TARGETS.get(t, {}).get('name', t)
            conflicts.append(f"⚡ {t} ({name}) 同時出現「頂背離 + 底背離」！盤面劇烈震盪洗盤，建議觀望。")

    return big_picture, tonight, conflicts

# ==================== Email 組裝 ====================

def build_email_body(sigs):
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    overnight_str, levels_str = get_overnight_and_key_levels()
    nq_status = get_nq_custom_chart_status()
    calendar_str = get_today_calendar_events()

    big_picture, tonight, conflict_lines = process_and_group_signals(sigs)
    rating, breakdown_str = calculate_detailed_risk_score(sigs)

    # 戰術判斷
    nq_4h_top = [s for s in sigs if s['ticker'] == 'NQ=F' and s['level'] == '4H' and s['dir'] == '頂']
    nq_4h_bot = [s for s in sigs if s['ticker'] == 'NQ=F' and s['level'] == '4H' and s['dir'] == '底']
    big_top = [s for s in sigs if s['level'] in ['W', 'M'] and s['dir'] == '頂']

    if nq_4h_top:
        tactics = "🎯 今晚戰術：NQ 4H 頂背離！開盤拉高無力可搵 Put (嚴禁追 Call)。"
    elif nq_4h_bot:
        tactics = "🎯 今晚戰術：NQ 4H 底背離！開盤急跌可搵 Call。"
    else:
        tactics = "🟢 今晚戰術：無 4H 轉折訊號，結合 5m EMA 帶形態即市操作。"

    macro_bg = "🏛️ 大勢背景：週/月線大頂背離中！做 Put 爆發力大。" if big_top else \
               "🏛️ 大勢背景：大週期結構常態，順應日內動能。"

    sep = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    L = [
        f"⚡ Radar V16.0 0DTE 全宏觀晨報 | {now} HKT",
        sep,
        "🏛️ 大勢背景（月 / 週線）",
        sep,
    ]
    if big_picture:
        L.extend(big_picture)
    else:
        L.append("   🟢 月/週線暫無顯著背離")
    L.append("   " + macro_bg)

    L.extend([sep, "🎯 今晚操作（日 / 4H）", sep])
    if tonight:
        L.extend(tonight)
    else:
        L.append("   🟢 日/4H 暫無顯著背離")
    L.append("   " + tactics)

    L.extend([sep, "📊 隔夜與宏觀", sep, overnight_str])

    L.extend([sep, "📍 NQ 關鍵位", sep, levels_str])

    L.extend([sep, "🛡️ 5m EMA 帶監測", sep, nq_status])

    L.extend([sep, "📅 今晚日曆", sep, calendar_str])

    if conflict_lines:
        L.extend([sep, "🔥 多空衝突警告", sep])
        for c in conflict_lines:
            L.append(f"   * {c}")

    L.extend([sep, f"整體風險評級 : {rating}", f"📊 拆解 : {breakdown_str}", sep])

    return "\n".join(L)

# ==================== 主程式 ====================

def main():
    try:
        print(f"=== 開始掃描 {len(ALL_TARGETS)} 個標的 ===", flush=True)
        sigs = []
        for t, info in ALL_TARGETS.items():
            print(f"[掃描] {t} ({info['name']})...", flush=True)
            result = scan_asset(t, info)
            print(f"  → 搵到 {len(result)} 個訊號", flush=True)
            sigs += result

        print(f"=== 總共 {len(sigs)} 個訊號 ===", flush=True)
        body = build_email_body(sigs)

        msg = MIMEMultipart()
        msg['Subject'] = f"⚡ [0DTE 雷達 V16] 三大期指與跨資產宏觀戰術地圖 ({datetime.now().strftime('%m/%d')})"
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
        print("✅ 晨報已成功發送", flush=True)
    except Exception as e:
        print(f"❌ 執行失敗: {e}", flush=True)
        traceback.print_exc()

if __name__ == '__main__':
    main()
