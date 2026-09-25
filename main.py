# main.py - NQ 0DTE 終極全功能晨報腳本 (雙重去重評分 + 1m 均線帶監測穩定版)
import yfinance as yf
import os, smtplib, traceback
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': os.environ.get('EMAIL_USER'),
    'sender_password': os.environ.get('EMAIL_PASS'),
    'receiver_email': os.environ.get('EMAIL_TO', os.environ.get('EMAIL_USER'))
}

# 剔除 QQQ，補齊 10 大行業板塊 ETF
ALL_TARGETS = {
    # 核心期貨與指數
    'NQ=F': {'name':'納指100期貨','sticker':'📱','weight':5,'category':'TECH'},
    'ES=F': {'name':'標普500期貨','sticker':'📈','weight':4,'category':'INDEX'},
    '^VIX': {'name':'恐慌指數','sticker':'😱','weight':3,'category':'INDEX'},
    
    # 科技與科技衍生板塊
    'SMH':  {'name':'美股半導體(核心)','sticker':'💾','weight':4,'category':'TECH'},
    'IGV':  {'name':'美股軟件服務','sticker':'💿','weight':3,'category':'TECH'},
    'XLC':  {'name':'通訊服務ETF','sticker':'📡','weight':3,'category':'TECH'},
    'XLY':  {'name':'非必需消費ETF','sticker':'🛍️','weight':3,'category':'CYCLICAL'},
    
    # 週期與防禦板塊
    'XLF':  {'name':'金融板塊ETF','sticker':'🏦','weight':3,'category':'CYCLICAL'},
    'XLE':  {'name':'能源板塊ETF','sticker':'🛢️','weight':3,'category':'CYCLICAL'},
    'XLI':  {'name':'工業板塊ETF','sticker':'⚙️','weight':3,'category':'CYCLICAL'},
    'XLV':  {'name':'醫療保健ETF','sticker':'🏥','weight':2,'category':'DEFENSIVE'},
    'XLP':  {'name':'必需消費ETF','sticker':'🛒','weight':2,'category':'DEFENSIVE'},
    'XLU':  {'name':'公用事業ETF','sticker':'⚡','weight':2,'category':'DEFENSIVE'},
}

# ==================== 技術指標計算 ====================

def calculate_custom_indicators(df):
    close = df['Close']
    high = df['High']
    low = df['Low']

    ema50   = close.ewm(span=50, adjust=False).mean()
    ema700  = close.ewm(span=700, adjust=False).mean() if len(df) >= 700 else pd.Series(index=df.index)
    ema1000 = close.ewm(span=1000, adjust=False).mean() if len(df) >= 1000 else pd.Series(index=df.index)
    ema3500 = close.ewm(span=3500, adjust=False).mean() if len(df) >= 3500 else pd.Series(index=df.index)

    # MACD DIF
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
        'EMA50': ema50, 'EMA700': ema700, 'EMA1000': ema1000, 'EMA3500': ema3500
    })

def pivothigh(series, n):
    vals = series.values
    highs = []
    for i in range(n, len(vals) - n):
        if all(vals[i] > vals[i-n:i]) and all(vals[i] > vals[i+1:i+n+1]):
            highs.append(i)
    return np.array(highs)

def pivotlow(series, n):
    vals = series.values
    lows = []
    for i in range(n, len(vals) - n):
        if all(vals[i] < vals[i-n:i]) and all(vals[i] < vals[i+1:i+n+1]):
            lows.append(i)
    return np.array(lows)

def find_div_custom(p, i, lookback=80, n=5):
    df = pd.DataFrame({'price': p, 'ind': i}).dropna().tail(lookback)
    if len(df) < n * 2 + 5: return None
    p_s, i_s = df['price'], df['ind']
    highs, lows = pivothigh(p_s, n=n), pivotlow(p_s, n=n)

    if len(highs) >= 2:
        h1, h2 = highs[-2], highs[-1]
        if p_s.iloc[h2] >= p_s.iloc[h1] * 0.985 and i_s.iloc[h2] < i_s.iloc[h1]:
            return '頂'
    if len(lows) >= 2:
        l1, l2 = lows[-2], lows[-1]
        if p_s.iloc[l2] <= p_s.iloc[l1] * 1.015 and i_s.iloc[l2] > i_s.iloc[l1]:
            return '底'
    return None

def scan_asset(t, info):
    sigs = []
    config = [('M', ('1mo','5y',60), 2), ('W', ('1wk','3y',100), 3), ('D', ('1d','6mo',30), 5), ('4H', ('1h','60d',60), 4)]
    for lv, (itv, per, lb), n in config:
        try:
            raw_df = yf.Ticker(t).history(period=per, interval=itv)
            if len(raw_df) < 40: continue
            calc_df = calculate_custom_indicators(raw_df)
            
            d_dif = find_div_custom(calc_df['Close'], calc_df['DIF'], lookback=lb, n=n)
            if d_dif: sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_dif, 'ind': 'DIF'})

            curr_j = calc_df['J'].iloc[-1]
            d_j = find_div_custom(calc_df['Close'], calc_df['J'], lookback=lb, n=n)
            if d_j:
                if d_j == '頂' and curr_j > 75: sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_j, 'ind': 'J'})
                elif d_j == '底' and curr_j < 25: sigs.append({**info, 'ticker': t, 'level': lv, 'dir': d_j, 'ind': 'J'})
        except: pass
    return sigs

# ==================== 風險評分引擎 (雙重去重算分) ====================

def calculate_detailed_risk_score(sigs):
    level_weights = {'M': 4.0, 'W': 4.0, 'D': 2.5, '4H': 1.5}
    level_priority = {'M': 4, 'W': 3, 'D': 2, '4H': 1}

    # 第一階段：按 Ticker 篩選出最長週期的所有訊號
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

    # 第二階段：每個標的僅計算 1 次最長週期分數 (DIF 優先)
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

    if total_score >= 30:
        rating = "🚨🚨 極高轉折/變盤風險 (全市場多個大週期背離)"
    elif total_score >= 18:
        rating = "🚨 高轉折風險 (核心板塊大週期背離)"
    elif total_score >= 10:
        rating = "⚠️ 中度波動風險 (局部板塊背離)"
    elif total_score >= 4:
        rating = "🟢 低風險/偏趨勢 (個別標的背離)"
    else:
        rating = "🟢🟢 極低風險 (順勢運行)"

    breakdown = (f"總分: {total_score} | 科技權重: {round(tech_score, 1)} / "
                 f"週期權重: {round(cyclical_score, 1)} / "
                 f"防禦權重: {round(defensive_score, 1)}")

    return rating, breakdown

# ==================== 關鍵數據與日曆 ====================

def get_today_calendar_events():
    now_hkt = datetime.now(timezone(timedelta(hours=8)))
    weekday = now_hkt.weekday()
    
    events = []
    if weekday == 3:
        events.append("20:30 HKT | 🇺🇸 美國初請失業金人數 (Initial Jobless Claims)")
    elif weekday == 4:
        events.append("20:30 HKT | 🇺🇸 美國核心 PCE / 核心 CPI / 耐久財訂單數據")
        
    events.append("21:30 HKT | 🔔 美股常規盤正式開盤 (0DTE 主要流動性湧入)")
    events.append("22:00 HKT | 🇺🇸 密歇根大學消費者信心指數 / ISM 採購經理人指數 (若有)")
    
    lines = ["📅 【今晚 0DTE 關鍵日曆與催化劑時間軸】："]
    for ev in events:
        lines.append(f"   * {ev}")
        
    lines.extend([
        "",
        "🛡️ 【0DTE 日曆風控鐵律】：",
        "   1. 重大數據發佈前 15 分鐘（如 20:15）：建議平掉所有 15s/1m 極短線 0DTE 頭寸，防範雙向插針殺 IV。",
        "   2. 數據發佈後 15 分鐘（20:45 後）：待 1m EMA 700-1000 帶重新定型並出現方向突破，再順勢尋找進場點。"
    ])
    return "\n".join(lines)

def get_overnight_and_key_levels():
    try:
        nq = yf.Ticker('NQ=F').history(period='5d', interval='1d')
        es = yf.Ticker('ES=F').history(period='5d', interval='1d')
        vix = yf.Ticker('^VIX').history(period='5d', interval='1d')
        
        nq_c, nq_p = nq['Close'].iloc[-1], nq['Close'].iloc[-2]
        es_c, es_p = es['Close'].iloc[-1], es['Close'].iloc[-2]
        vix_c, vix_p = vix['Close'].iloc[-1], vix['Close'].iloc[-2]

        nq_chg = ((nq_c - nq_p) / nq_p) * 100
        es_chg = ((es_c - es_p) / es_p) * 100
        vix_chg = ((vix_c - vix_p) / vix_p) * 100

        header = f"🌐 隔夜期貨 (09:00 HKT): NQ: {nq_c:,.1f} ({nq_chg:+.2f}%) | ES: {es_c:,.1f} ({es_chg:+.2f}%) | VIX: {vix_c:.1f} ({vix_chg:+.2f}%)"

        high_p = nq['High'].iloc[-2]
        low_p = nq['Low'].iloc[-2]
        close_p = nq['Close'].iloc[-2]
        
        pivot = (high_p + low_p + close_p) / 3.0
        r1 = (2 * pivot) - low_p
        s1 = (2 * pivot) - high_p
        swing_high = nq['High'].max()
        swing_low = nq['Low'].min()

        levels = [
            "📍 NQ=F 期貨今晚 0DTE 核心戰術卡位 (Key Levels)：",
            f"   * 5日波段強阻力 (Swing High): {swing_high:,.1f}",
            f"   * 今晚第一壓力 (R1)        : {r1:,.1f}",
            f"   * 今晚 Pivot 中軸          : {pivot:,.1f}  (昨收: {close_p:,.1f})",
            f"   * 今晚第一支撐 (S1)        : {s1:,.1f}",
            f"   * 5日波段強支撐 (Swing Low) : {swing_low:,.1f}"
        ]
        return header, "\n".join(levels)
    except Exception as e:
        return "🌐 隔夜數據擷取失敗", "📍 Key Levels 計算失敗"

# NQ 期貨 1 分鐘 (1m) 圖形態監測
def get_nq_custom_chart_status():
    try:
        ticker = yf.Ticker('NQ=F')
        
        # 抓取 5 天的 1m 數據 (約有 6,000-7,000 筆 K 線，完美支援 EMA 3500 計算)
        raw_df = ticker.history(period='5d', interval='1m')

        if raw_df.empty or len(raw_df) < 100: 
            return "NQ 1m 數據獲取失敗 (Yahoo Finance API 暫時無回應)"
            
        calc_df = calculate_custom_indicators(raw_df)
        last = calc_df.iloc[-1]
        price = last['Close']
        
        ema700, ema1000, ema3500 = last['EMA700'], last['EMA1000'], last['EMA3500']
        lines = [
            "🛡️ 【NQ 期貨 1m 圖 EMA 700-1000 帶 & 3500 形態監測】：", 
            f"   * 現價 : {price:.1f}"
        ]
        
        if not np.isnan(ema700) and not np.isnan(ema1000):
            band_top, band_bot = max(ema700, ema1000), min(ema700, ema1000)
            band_width_pts = band_top - band_bot
            band_width_pct = (band_width_pts / price) * 100
            
            if band_width_pct < 0.15:
                inner_status = f"🚨 【1m 帶內極度黏合】 (帶寬僅 {band_width_pts:.1f} 點 / {band_width_pct:.2f}%)"
                inner_hint = "1m 日內籌碼極度集中！今晚突破容易爆發單邊強趨勢，0DTE 可適當讓利潤奔跑。"
            elif band_width_pct > 0.60:
                inner_status = f"⚠️ 【1m 帶內寬幅發散】 (帶寬達 {band_width_pts:.1f} 點 / {band_width_pct:.2f}%)"
                inner_hint = "1m 動能充分發散中，留意背離訊號，見好即收，防範帶內劇烈回歸。"
            else:
                inner_status = f"🟢 【1m 常態帶寬】 (帶寬 {band_width_pts:.1f} 點 / {band_width_pct:.2f}%)"
                inner_hint = "帶寬處於常態，按 15s/1m 貼身線與背離訊號正常操作。"
                
            lines.append(f"   * 📍 1m EMA 700-1000 帶範圍 : {band_bot:.1f} - {band_top:.1f}")
            lines.append(f"     └─ 形態: {inner_status}")
            
            if not np.isnan(ema3500):
                lines.append(f"   * 🏛️ 1m EMA 3500 鐵板位 : {ema3500:.1f}")
                if ema3500 > band_top:
                    cross_status = "🚨 【EMA 3500 在 700-1000 帶上方】 (1m 級別長線壓制)"
                elif ema3500 < band_bot:
                    cross_status = "🟢 【EMA 3500 在 700-1000 帶下方】 (1m 級別標準多頭)"
                else:
                    cross_status = "⚡ 【EMA 3500 穿越/嵌入 700-1000 帶】 (1m 長短線籌碼交織，極易劇烈洗盤！)"
                lines.append(f"     └─ 穿越狀態: {cross_status}")
            else:
                lines.append("   * 🏛️ 1m EMA 3500 : 數據累積不足 3500 條，暫不顯示")
            
            lines.extend([
                "   --------------------------------------------------", 
                f"   🎯 實戰戰術指引：{inner_hint}"
            ])
            
        return "\n".join(lines)
    except Exception as e:
        return f"1m 均線帶形態監測失敗: {e}"

# ==================== 背離多週期整合顯示與打架檢測 ====================

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
                'ind': s['ind'], 'levels': [], 'info': s
            }
        grouped[key]['levels'].append(s['level'])

    result_lines = []
    ticker_dirs = {}

    for key, data in grouped.items():
        t, direction, ind = key
        if t not in ticker_dirs: ticker_dirs[t] = set()
        ticker_dirs[t].add(direction)

        sorted_lvls = sorted(data['levels'], key=lambda x: level_order.get(x, 99))
        lvl_str = "+".join(sorted_lvls)
        
        emoji = '🚨' if t in ['NQ=F', 'SMH'] else '⚠️'
        line = f"{emoji} {t} | {lvl_str} {direction}背離 [{ind}] | {data['name']}"
        result_lines.append(line)

    for t, dirs in ticker_dirs.items():
        if '頂' in dirs and '底' in dirs:
            name = ALL_TARGETS.get(t, {}).get('name', t)
            conflicts.append(f"⚡ 【多空衝突/背離打架】: {t} ({name}) 同時出現大/小週期「頂背離 + 底背離」！盤面劇烈震盪洗盤，建議觀望或緊貼 15s/1m 帶狀止損。")

    return result_lines, conflicts

# ==================== 郵件組裝 ====================

def build_email_body(sigs):
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    overnight_str, levels_str = get_overnight_and_key_levels()
    nq_status = get_nq_custom_chart_status()
    calendar_str = get_today_calendar_events()
    
    grouped_sig_lines, conflict_lines = process_and_group_signals(sigs)
    rating, breakdown_str = calculate_detailed_risk_score(sigs)
    
    nq_4h_top = [s for s in sigs if s['ticker'] == 'NQ=F' and s['level'] == '4H' and s['dir'] == '頂']
    nq_4h_bot = [s for s in sigs if s['ticker'] == 'NQ=F' and s['level'] == '4H' and s['dir'] == '底']
    big_top = [s for s in sigs if s['level'] in ['W', 'M'] and s['dir'] == '頂']
    
    tactics = "🎯 【今晚戰術】：NQ/SMH 出現 4H 頂背離！今晚開盤拉高無力可尋找 Put 機會 (嚴禁追 Call)。" if nq_4h_top else \
              "🎯 【今晚戰術】：NQ/SMH 出現 4H 底背離！今晚開盤急跌砸盤可尋找 Call 機會。" if nq_4h_bot else \
              "🟢 【今晚戰術】：無直接 4H 轉折訊號，結合 1m EMA 帶形態，開盤用 15s/1m 貼身線尋找進場點。"
              
    macro_bg = "🏛️ 【大局背景】：週/月線處於大頂背離中！今晚若做 Put 爆發力極大，勝率與盈虧比偏高。" if big_top else \
               "🏛️ 【大局背景】：大週期結構常態，順應日內 15s/1m 貼身動能即可。"

    L = [
        f"⚡ Radar V15.28 0DTE 早報 | {now} HKT",
        "="*55,
        overnight_str,
        "="*55,
        tactics,
        macro_bg,
        "="*55,
        f"整體風險評級 : {rating}",
        f"📊 風險得分拆解 : {breakdown_str} (去重後總分)",
        "",
        levels_str,
        "="*55,
        nq_status,
        "="*55,
        calendar_str,
        "="*55,
    ]

    if conflict_lines:
        L.append("🔥 【⚠️ 多空背離打架 (衝突警告)】")
        for c in conflict_lines:
            L.append(f"   * {c}")
        L.append("="*55)

    L.append("🔥 【詳細背離警報列表 (多週期整合版)】")
    if grouped_sig_lines:
        for line in grouped_sig_lines:
            L.append(line)
    else:
        L.append("🟢 各大板塊與指數目前暫無顯著背離訊號。")

    return "\n".join(L)

def main():
    try:
        sigs = []
        for t, info in ALL_TARGETS.items():
            sigs += scan_asset(t, info)
            
        body = build_email_body(sigs)
        
        msg = MIMEMultipart()
        msg['Subject'] = f"⚡ [0DTE 雷達 09:00] NQ 期貨與 10 大板塊戰術地圖 ({datetime.now().strftime('%m/%d')})"
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = EMAIL_CONFIG['receiver_email']
        msg.attach(MIMEText(f"<pre style='font-family:Consolas,monospace;font-size:14px;background:#f8f9fa;padding:15px;'>{body}</pre>", 'html', 'utf-8'))
        
        s = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        s.starttls()
        s.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        s.send_message(msg)
        s.quit()
        print("✅ 終極全功能 0DTE 晨報已成功發送 (09:00 HKT)")
    except Exception as e:
        print(f"❌ 執行失敗: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    main()
