# main.py - NQ 0DTE 全宏觀晨報 V17.7
# ============================================
# V17.7 改動（相對 V17.6）：
#   1. 刪除「🎯 今晚戰術」句子
#   2. 其他保持不變
# ============================================

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

# ==================== 時間顯示 ====================

def time_ago(dist, lv):
    if dist == 0:
        return '最新'
    if lv == 'M':
        return f'{dist} 個月前'
    if lv == 'W':
        return f'{dist} 週前'
    if lv == 'D':
        return f'{dist} 日前'
    if lv == '4H':
        hours = dist * 4
        if hours >= 24:
            days = hours // 24
            return f'{days} 日前'
        return f'{hours} 小時前'
    return f'{dist} 根前'

# ==================== 指標計算 ====================

def calculate_custom_indicators(df):
    close = df['Close']; high = df['High']; low = df['Low']

    ema50   = close.ewm(span=50, adjust=False).mean()
    ema700  = close.ewm(span=700, adjust=False).mean() if len(df) >= 700 else pd.Series(index=df.index, dtype=float)
    ema800  = close.ewm(span=800, adjust=False).mean() if len(df) >= 800 else pd.Series(index=df.index, dtype=float)
    ema900  = close.ewm(span=900, adjust=False).mean() if len(df) >= 900 else pd.Series(index=df.index, dtype=float)
    ema1000 = close.ewm(span=1000, adjust=False).mean() if len(df) >= 1000 else pd.Series(index=df.index, dtype=float)
    ema3500 = close.ewm(span=3500, adjust=False).mean() if len(df) >= 3500 else pd.Series(index=df.index, dtype=float)

    ema5 = close.ewm(span=5, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema5 - ema26

    low9 = low.rolling(9).min(); high9 = high.rolling(9).max()
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

# ==================== 舊邏輯：Pivot-to-pivot（M/W）====================

def scipy_pivots(series, prominence_pct=3.0, distance=2):
    if len(series) < 20:
        return [], []
    prominence = series.mean() * prominence_pct / 100
    highs, _ = find_peaks(series.values, prominence=prominence, distance=distance)
    lows, _ = find_peaks(-series.values, prominence=prominence, distance=distance)
    return list(highs), list(lows)

def check_pivot_divergence(p_s, i_s, highs, lows, last_idx, recent_window):
    top_div = None
    bot_div = None

    recent_highs = [h for h in highs if last_idx - h <= recent_window]
    if recent_highs:
        h2 = recent_highs[-1]
        prev_highs = [h for h in highs if h < h2]
        if prev_highs:
            h1 = max(prev_highs, key=lambda x: p_s.iloc[x])
            if p_s.iloc[h2] > p_s.iloc[h1] and i_s.iloc[h2] < i_s.iloc[h1]:
                top_div = {'dist': last_idx - h2}

    recent_lows = [l for l in lows if last_idx - l <= recent_window]
    if recent_lows:
        l2 = recent_lows[-1]
        prev_lows = [l for l in lows if l < l2]
        if prev_lows:
            l1 = min(prev_lows, key=lambda x: p_s.iloc[x])
            if p_s.iloc[l2] < p_s.iloc[l1] and i_s.iloc[l2] > i_s.iloc[l1]:
                bot_div = {'dist': last_idx - l2}

    if top_div and bot_div:
        return ('頂', top_div['dist']) if top_div['dist'] <= bot_div['dist'] else ('底', bot_div['dist'])
    if top_div: return ('頂', top_div['dist'])
    if bot_div: return ('底', bot_div['dist'])
    return None

# ==================== 新邏輯：雙重 Lookback ====================

def check_dual_lookback(price, indicator, short_lb=5, long_lb=20,
                        price_tol=0.005, ind_drop_min=0.05):
    if len(price) < long_lb + 2:
        return {'long': [], 'short': []}

    last_idx = len(price) - 1
    p_now = float(price.iloc[last_idx])
    i_now = float(indicator.iloc[last_idx])

    result = {'long': [], 'short': []}

    for label, lb in [('long', long_lb), ('short', short_lb)]:
        if last_idx - lb < 0:
            continue

        recent_price = price.iloc[last_idx - lb:last_idx]
        recent_ind = indicator.iloc[last_idx - lb:last_idx]
        if len(recent_price) == 0:
            continue

        # 頂背離
        prev_high_pos = int(np.argmax(recent_price.values))
        prev_high_price = float(recent_price.iloc[prev_high_pos])
        prev_high_ind = float(recent_ind.iloc[prev_high_pos])

        if prev_high_price != 0 and prev_high_ind != 0:
            price_close = p_now >= prev_high_price * (1 - price_tol)
            ind_change = (i_now - prev_high_ind) / abs(prev_high_ind)

            if price_close and ind_change <= -ind_drop_min:
                is_new_high = p_now > prev_high_price
                dist = lb - prev_high_pos
                result[label].append({
                    'type': '頂',
                    'tag': '新高' if is_new_high else '雙頂',
                    'current_price': p_now,
                    'prev_price': prev_high_price,
                    'current_ind': i_now,
                    'prev_ind': prev_high_ind,
                    'dist': dist,
                    'price_diff_pct': (p_now - prev_high_price) / prev_high_price * 100,
                    'ind_change_pct': ind_change * 100
                })
                continue

        # 底背離
        prev_low_pos = int(np.argmin(recent_price.values))
        prev_low_price = float(recent_price.iloc[prev_low_pos])
        prev_low_ind = float(recent_ind.iloc[prev_low_pos])

        if prev_low_price != 0 and prev_low_ind != 0:
            price_close_low = p_now <= prev_low_price * (1 + price_tol)
            ind_change = (i_now - prev_low_ind) / abs(prev_low_ind)

            if price_close_low and ind_change >= ind_drop_min:
                is_new_low = p_now < prev_low_price
                dist = lb - prev_low_pos
                result[label].append({
                    'type': '底',
                    'tag': '新低' if is_new_low else '雙底',
                    'current_price': p_now,
                    'prev_price': prev_low_price,
                    'current_ind': i_now,
                    'prev_ind': prev_low_ind,
                    'dist': dist,
                    'price_diff_pct': (p_now - prev_low_price) / prev_low_price * 100,
                    'ind_change_pct': ind_change * 100
                })

    return result

# ==================== 參數 ====================

PIVOT_CONFIG = [
    ('M', '1mo', '5y',  60, {'prominence_pct': 5.0, 'distance': 2, 'recent_window': 3}),
    ('W', '1wk', '3y',  100, {'prominence_pct': 3.0, 'distance': 2, 'recent_window': 4}),
]

DUAL_LB_CONFIG = {
    'M':  {'short': 3,  'long': 6,  'price_tol': 0.02,  'ind_drop': 0.05},
    'W':  {'short': 4,  'long': 10, 'price_tol': 0.015, 'ind_drop': 0.05},
    'D':  {'short': 5,  'long': 20, 'price_tol': 0.005, 'ind_drop': 0.05},
    '4H': {'short': 5,  'long': 20, 'price_tol': 0.003, 'ind_drop': 0.05},
}

INTERVAL_MAP = {
    'M':  ('1mo', '5y',  60),
    'W':  ('1wk', '3y',  100),
    'D':  ('1d',  '6mo', 30),
    '4H': ('1h',  '60d', 60),
}

# ==================== 掃描 ====================

def get_raw_df(t, lv):
    itv, per, _ = INTERVAL_MAP[lv]
    raw = yf.Ticker(t).history(period=per, interval=itv)
    if lv == '4H' and not raw.empty:
        raw = raw.resample('4h').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min',
            'Close': 'last', 'Volume': 'sum'
        }).dropna()
    return raw

def scan_pivot(t, info, lv, params):
    results = []
    try:
        raw_df = get_raw_df(t, lv)
        if len(raw_df) < 40:
            return results
        calc_df = calculate_custom_indicators(raw_df)
        p_s = calc_df['Close']
        last_idx = len(calc_df) - 1
        highs, lows = scipy_pivots(p_s, prominence_pct=params['prominence_pct'],
                                    distance=params['distance'])
        rw = params['recent_window']

        d = check_pivot_divergence(p_s, calc_df['DIF'], highs, lows, last_idx, rw)
        if d:
            results.append({'ind': 'DIF', 'dir': d[0], 'dist': d[1]})

        d = check_pivot_divergence(p_s, calc_df['J'], highs, lows, last_idx, rw)
        if d:
            curr_j = float(calc_df['J'].iloc[-1])
            if (d[0] == '頂' and curr_j > 70) or (d[0] == '底' and curr_j < 30):
                results.append({'ind': 'J', 'dir': d[0], 'dist': d[1]})
    except Exception as e:
        print(f"[scan_pivot] {t} {lv}: {e}")
    return results

def scan_dual_lookback(t, info, lv):
    results = []
    try:
        raw_df = get_raw_df(t, lv)
        if len(raw_df) < 40:
            return results

        if lv in ['M', 'W']:
            raw_df = raw_df.iloc[:-1]

        if len(raw_df) < 40:
            return results

        calc_df = calculate_custom_indicators(raw_df)
        p_s = calc_df['Close']
        params = DUAL_LB_CONFIG[lv]

        for ind_name in ['DIF', 'J']:
            r = check_dual_lookback(
                p_s, calc_df[ind_name],
                short_lb=params['short'], long_lb=params['long'],
                price_tol=params['price_tol'], ind_drop_min=params['ind_drop']
            )
            for sig in r['long']:
                sig['ind'] = ind_name; sig['lookback'] = 'long'
                results.append(sig)
            for sig in r['short']:
                sig['ind'] = ind_name; sig['lookback'] = 'short'
                results.append(sig)

    except Exception as e:
        print(f"[scan_dual_lookback] {t} {lv}: {e}")
    return results

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
        def c(x): return float(x['Close'].iloc[-1])
        def p(x): return float(x['Close'].iloc[-2])

        header = "\n".join([
            "🌐 隔夜與宏觀數據：",
            f"   * 指數: NQ {c(nq):,.1f} ({pct(c(nq),p(nq)):+.2f}%) | ES {c(es):,.1f} ({pct(c(es),p(es)):+.2f}%) | YM {c(ym):,.1f} ({pct(c(ym),p(ym)):+.2f}%) | VIX {c(vix):.1f} ({pct(c(vix),p(vix)):+.2f}%)",
            f"   * 大宗: 黃金 ${c(gc):,.1f} ({pct(c(gc),p(gc)):+.2f}%) | 原油 ${c(cl):.2f} ({pct(c(cl),p(cl)):+.2f}%)",
            f"   * 宏觀: 美指 {c(dxy):.2f} ({pct(c(dxy),p(dxy)):+.2f}%) | 10年美債 {c(tnx):.3f}% ({pct(c(tnx),p(tnx)):+.2f}%)"
        ])

        high_p = float(nq['High'].iloc[-2]); low_p = float(nq['Low'].iloc[-2]); close_p = float(nq['Close'].iloc[-2])
        pivot = (high_p + low_p + close_p) / 3.0
        r1 = 2 * pivot - low_p
        s1 = 2 * pivot - high_p

        levels = "\n".join([
            "📍 NQ=F 今晚 0DTE 核心戰術卡位：",
            f"   * 5日強阻力 : {float(nq['High'].max()):,.1f}",
            f"   * R1 第一壓力: {r1:,.1f}",
            f"   * Pivot 中軸 : {pivot:,.1f}  (昨收: {close_p:,.1f})",
            f"   * S1 第一支撐: {s1:,.1f}",
            f"   * 5日強支撐 : {float(nq['Low'].min()):,.1f}"
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
        price = float(last['Close'])

        lines = [
            "🛡️ 【NQ 5m EMA 700-1000 帶 & 3500 監測】：",
            f"   * 現價 : {price:.1f}"
        ]

        band_vals = [float(v) for v in [last['EMA700'], last['EMA800'], last['EMA900'], last['EMA1000']] if not np.isnan(v)]
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
                e3500 = float(last['EMA3500'])
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

# ==================== 格式化 ====================

def cap_pct(pct):
    if pct > 100: return ">+100%"
    if pct < -100: return "<-100%"
    return f"{pct:+.2f}%"

def fmt_pivot_signal(sig):
    dist = sig['dist']
    time_str = time_ago(dist, sig['level'])
    icon = '⚡'
    return f"   {icon} [已確認] [{sig['level']}][{sig['ind']}] {sig['dir']}背離 ({time_str})"

def fmt_dual_signal_body(sig):
    label = sig.get('lookback', 'long')
    is_long = (label == 'long')

    icon = '🔥🔥' if is_long else '🔥'
    if sig['tag'] in ['雙頂', '雙底']:
        icon = '⚡⚡' if is_long else '⚡'

    label_str = '長' if is_long else '短'
    ind_name = sig['ind']
    dist = sig['dist']
    lv = sig['level']

    time_str = time_ago(dist, lv)
    price_pct = cap_pct(sig['price_diff_pct'])
    ind_pct = cap_pct(sig['ind_change_pct'])

    return (
        f"      [{lv}][{ind_name}] {icon} {label_str}{sig['tag']}："
        f"前{'高' if sig['type'] == '頂' else '低'} {sig['prev_price']:,.2f} ({time_str})\n"
        f"            價: {price_pct} / {ind_name}: {ind_pct}"
    )

# ==================== 分組 ====================

def group_dual_by_ticker(signals):
    groups = {}
    for s in signals:
        groups.setdefault(s['ticker'], []).append(s)

    blocks = []
    for ticker, sigs in groups.items():
        info = ALL_TARGETS[ticker].copy()
        info['ticker'] = ticker

        top_sigs = [s for s in sigs if s['type'] == '頂']
        bot_sigs = [s for s in sigs if s['type'] == '底']

        current_price = sigs[0]['current_price']
        header = f"🚨 {info['name']} ({ticker}) (現價 {current_price:,.2f})"

        body_lines = []

        if top_sigs:
            body_lines.append("   🔴 頂背離")
            long_top = [s for s in top_sigs if s.get('lookback') == 'long']
            short_top = [s for s in top_sigs if s.get('lookback') == 'short']
            display = long_top if long_top else short_top
            display = sorted(display, key=lambda x: (0 if x['ind'] == 'DIF' else 1))
            for s in display:
                body_lines.append(fmt_dual_signal_body(s))
            if long_top and short_top:
                body_lines.append("      ⚡ 另有短訊號（未顯示）")

        if bot_sigs:
            body_lines.append("   🟢 底背離")
            long_bot = [s for s in bot_sigs if s.get('lookback') == 'long']
            short_bot = [s for s in bot_sigs if s.get('lookback') == 'short']
            display = long_bot if long_bot else short_bot
            display = sorted(display, key=lambda x: (0 if x['ind'] == 'DIF' else 1))
            for s in display:
                body_lines.append(fmt_dual_signal_body(s))
            if long_bot and short_bot:
                body_lines.append("      ⚡ 另有短訊號（未顯示）")

        if top_sigs and bot_sigs:
            body_lines.append("   ⚠️ 短長方向矛盾")

        blocks.append(header + "\n" + "\n".join(body_lines))

    return blocks

# ==================== 大勢合併 ====================

def build_macro_section(pivot_sigs, dual_mw):
    tickers_seen = set()
    for s in pivot_sigs + dual_mw:
        if s['level'] in ['M', 'W']:
            tickers_seen.add(s['ticker'])

    lines = []
    for ticker in sorted(tickers_seen):
        info = ALL_TARGETS.get(ticker, {})
        sticker = info.get('sticker', '')
        name = info.get('name', ticker)

        lines.append(f"{sticker} {name} ({ticker})")

        p_sigs = [s for s in pivot_sigs if s['ticker'] == ticker and s['level'] in ['M', 'W']]
        for s in p_sigs:
            lines.append(fmt_pivot_signal(s))

        d_sigs = [s for s in dual_mw if s['ticker'] == ticker and s['level'] in ['M', 'W']]
        if d_sigs:
            top_sigs = [s for s in d_sigs if s['type'] == '頂']
            bot_sigs = [s for s in d_sigs if s['type'] == '底']

            if top_sigs:
                lines.append("   🔴 頂背離")
                long_top = [s for s in top_sigs if s.get('lookback') == 'long']
                short_top = [s for s in top_sigs if s.get('lookback') == 'short']
                display = long_top if long_top else short_top
                display = sorted(display, key=lambda x: (0 if x['ind'] == 'DIF' else 1))
                for s in display:
                    lines.append(fmt_dual_signal_body(s))
                if long_top and short_top:
                    lines.append("      ⚡ 另有短訊號（未顯示）")

            if bot_sigs:
                lines.append("   🟢 底背離")
                long_bot = [s for s in bot_sigs if s.get('lookback') == 'long']
                short_bot = [s for s in bot_sigs if s.get('lookback') == 'short']
                display = long_bot if long_bot else short_bot
                display = sorted(display, key=lambda x: (0 if x['ind'] == 'DIF' else 1))
                for s in display:
                    lines.append(fmt_dual_signal_body(s))
                if long_bot and short_bot:
                    lines.append("      ⚡ 另有短訊號（未顯示）")

            if top_sigs and bot_sigs:
                lines.append("   ⚠️ 短長方向矛盾")

        lines.append("")

    return lines

# ==================== Email 組裝 ====================

def build_email_body(pivot_sigs, dual_dh, dual_mw):
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    overnight_str, levels_str = get_overnight_and_key_levels()
    nq_status = get_nq_custom_chart_status()
    calendar_str = get_today_calendar_events()

    sep = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    big_top = [s for s in pivot_sigs if s['level'] in ['M', 'W'] and s['dir'] == '頂']
    macro_bg = "🏛️ 大勢背景：週/月線大頂背離中！做 Put 爆發力大。" if big_top else \
               "🏛️ 大勢背景：大週期結構常態，順應日內動能。"

    L = [
        f"⚡ Radar V17.7 0DTE 全宏觀晨報 | {now} HKT",
        sep, "🏛️ 大勢背景（月 / 週線）", sep,
    ]

    macro_lines = build_macro_section(pivot_sigs, dual_mw)
    if macro_lines:
        L.extend(macro_lines)
    else:
        L.append("   🟢 暫無")

    L.append("   " + macro_bg)

    L.extend([sep, "🚨 今晚即時（日 / 4H）", sep])
    if dual_dh:
        for block in group_dual_by_ticker(dual_dh):
            L.append(block)
    else:
        L.append("   🟢 暫無顯著背離")

    L.extend([sep, "📊 隔夜與宏觀", sep, overnight_str])
    L.extend([sep, "📍 NQ 關鍵位", sep, levels_str])
    L.extend([sep, "🛡️ 5m EMA 帶監測", sep, nq_status])
    L.extend([sep, "📅 今晚日曆", sep, calendar_str, sep])

    return "\n".join(L)

# ==================== 主程式 ====================

def main():
    try:
        print(f"=== 掃描 {len(ALL_TARGETS)} 個標的 ===", flush=True)

        pivot_sigs = []
        dual_mw = []
        dual_dh = []

        for t, info in ALL_TARGETS.items():
            for lv, itv, per, lb, params in PIVOT_CONFIG:
                res = scan_pivot(t, info, lv, params)
                for r in res:
                    pivot_sigs.append({**info, 'ticker': t, 'level': lv, **r})

            for lv in ['M', 'W']:
                res = scan_dual_lookback(t, info, lv)
                for r in res:
                    dual_mw.append({**info, 'ticker': t, 'level': lv, **r})

            for lv in ['D', '4H']:
                res = scan_dual_lookback(t, info, lv)
                for r in res:
                    dual_dh.append({**info, 'ticker': t, 'level': lv, **r})

        print(f"舊邏輯訊號: {len(pivot_sigs)}", flush=True)
        print(f"新邏輯 M/W: {len(dual_mw)}", flush=True)
        print(f"新邏輯 D/4H: {len(dual_dh)}", flush=True)

        body = build_email_body(pivot_sigs, dual_dh, dual_mw)

        msg = MIMEMultipart()
        msg['Subject'] = f"⚡ [0DTE 雷達 V17.7] 大勢+今晚雙重背離 ({datetime.now().strftime('%m/%d')})"
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = EMAIL_CONFIG['receiver_email']
        msg.attach(MIMEText(
            f"<pre style='font-family:Consolas,Menlo,monospace;font-size:13px;background:#f8f9fa;padding:15px;'>{body}</pre>",
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
