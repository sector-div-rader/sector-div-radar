# radar_v11_index.py - 大勢版：指數共振 + 背離天數 + 中文板塊名
import yfinance as yf
import os
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta
from supabase import create_client

# ========== 指數權重最高，5分 ==========
INDICES = {
    'SPY': {'name':'標普500', 'sticker':'📈', 'weight':5, 'index':'SPX'},
    'QQQ': {'name':'納指100', 'sticker':'📱', 'weight':5, 'index':'NDX'},
    'DIA': {'name':'道指', 'sticker':'🏛️', 'weight':3, 'index':'DJI'},
}

SECTORS = {
    'XLE': {'name':'石油天然氣', 'sticker':'🛢️', 'weight':2, 'index':'SPX'},
    'KBE': {'name':'銀行', 'sticker':'🏦', 'weight':2, 'index':'SPX'},
    'SMH': {'name':'半導體', 'sticker':'💾', 'weight':3, 'index':'NDX'},
    'IGV': {'name':'軟件服務', 'sticker':'💿', 'weight':3, 'index':'NDX'},
    'IBB': {'name':'生物技術', 'sticker':'🧬', 'weight':1, 'index':'SPX'},
    'ITA': {'name':'航太國防', 'sticker':'✈️', 'weight':1, 'index':'SPX'},
    'XLP': {'name':'必需消費', 'sticker':'🛒', 'weight':1, 'index':'SPX'},
    'CARZ': {'name':'汽車', 'sticker':'🚗', 'weight':2, 'index':'SPX'},
    'XLB': {'name':'原材料', 'sticker':'🧪', 'weight':2, 'index':'SPX'},
    'XLU': {'name':'公用事業', 'sticker':'💡', 'weight':1, 'index':'SPX'},
    'XLRE': {'name':'地產', 'sticker':'🏠', 'weight':2, 'index':'SPX'},
    'XLC': {'name':'通訊服務', 'sticker':'📡', 'weight':2, 'index':'NDX'},
    'BOTZ': {'name':'AI人工智能', 'sticker':'🤖', 'weight':3, 'index':'NDX'},
    'WCLD': {'name':'雲計算', 'sticker':'☁️', 'weight':3, 'index':'NDX'},
    'HACK': {'name':'網絡安全', 'sticker':'🔒', 'weight':2, 'index':'NDX'},
}

FUTURES = {
    'GC=F': {'name':'黃金期貨', 'sticker':'🥇', 'index':'GOLD'},
    'SI=F': {'name':'白銀期貨', 'sticker':'🥈', 'index':'SILVER'},
    'CL=F': {'name':'原油期貨', 'sticker':'⛽', 'index':'OIL'},
    'DX-Y.NYB': {'name':'美元指數', 'sticker':'💵', 'index':'DXY'},
    'ZN=F': {'name':'十年國債', 'sticker':'📜', 'index':'BOND'},
    '^VIX': {'name':'恐慌指數', 'sticker':'😱', 'index':'VIX'},
}

ALL_ASSETS = {**INDICES, **SECTORS, **FUTURES}

def get_dif(c):
    return c.ewm(span=5, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()

def get_kdj(df):
    low=df['Low'].rolling(9).min()
    high=df['High'].rolling(9).max()
    rsv=(df['Close']-low)/(high-low)*100
    k=rsv.ewm(com=2, adjust=False).mean()
    d=k.ewm(com=2, adjust=False).mean()
    return 3*k-2*d

def find_div(p,i):
    if len(p)<30: return None
    p=p.iloc[-60:]
    i=i.iloc[-60:]
    s=p.iloc[:-5].iloc[-20:]
    if len(s)<5: return None
    curr_p=float(p.iloc[-1])
    curr_i=float(i.iloc[-1])
    peak_p=float(p.loc[s.idxmax()])
    trough_p=float(p.loc[s.idxmin()])
    peak_i=float(i.loc[s.idxmax()])
    trough_i=float(i.loc[s.idxmin()])
    if curr_p>=peak_p*0.95 and curr_i<peak_i*0.97: return "頂背離"
    if curr_p<=trough_p*1.05 and curr_i>trough_i*1.03: return "底背離"
    return None

def get_hist(ticker, period, interval):
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
        return df
    except: return pd.DataFrame()

def get_div_days(sb, ticker, level, div_type):
    """查 Supabase 睇背離第幾日"""
    try:
        res = sb.table("signals").select("created_at").eq("ticker",ticker).eq("level",level).eq("signal",div_type).order("created_at").limit(1).execute()
        if res.data:
            first_day = datetime.fromisoformat(res.data[0]['created_at'].replace('Z','+00:00'))
            days = (datetime.now(timezone.utc) - first_day).days + 1
            return days
        return 1
    except: return 1

def scan_asset(code, info, sb):
    raw_signals = []
    try:
        df_w = get_hist(code, "3y", "1wk")
        df_m = get_hist(code, "10y", "1mo")
        df_60m = get_hist(code, "3mo", "60m")

        if len(df_w)<60: return []
        print(f"掃描 {code} {info['name']}")

        # 月線
        if len(df_m)>=30:
            j=get_kdj(df_m).dropna()
            if len(j)>=5:
                div = find_div(df_m['Close'].loc[j.index], j)
                if div and ((div=="頂背離" and j.iloc[-1]<j.iloc[-2]) or (div=="底背離" and j.iloc[-1]>j.iloc[-2])):
                    days = get_div_days(sb, code, 'M', div)
                    raw_signals.append({'ticker':code, 'level':'M', 'type':div, 'dir':'頂' if '頂' in div else '底',
                                       'weight':info.get('weight',1), 'sticker':info['sticker'], 'name':info['name'],
                                       'index':info['index'], 'days':days})

        # 週線
        div = find_div(df_w['Close'], get_dif(df_w['Close']))
        if div:
            days = get_div_days(sb, code, 'W', div)
            raw_signals.append({'ticker':code, 'level':'W', 'type':div, 'dir':'頂' if '頂' in div else '底',
                               'sticker':info['sticker'], 'name':info['name'], 'index':info['index'], 'days':days})

        # 4H
        if len(df_60m)>=60:
            df_4h=df_60m.resample("4h").agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
            if len(df_4h)>=60:
                div = find_div(df_4h['Close'], get_dif(df_4h['Close']))
                if div:
                    raw_signals.append({'ticker':code, 'level':'4H', 'type':div, 'dir':'頂' if '頂' in div else '底',
                                       'sticker':info['sticker'], 'name':info['name'], 'index':info['index']})

    except Exception as e:
        print(f"skip {code} {e}")

    return raw_signals

def merge_signals(all_signals):
    grouped = {}
    for s in all_signals:
        key = (s['ticker'], s['dir'])
        grouped.setdefault(key, []).append(s)

    final_msgs = []
    level_order = {'4H':1, 'W':2, 'M':3}

    for (ticker, direction), sigs in grouped.items():
        sigs_sorted = sorted(sigs, key=lambda x: level_order[x['level']])
        levels = [s['level'] for s in sigs_sorted]
        if not levels: continue

        sticker = sigs[0]['sticker']
        name = sigs[0]['name']
        weight = max([s.get('weight',1) for s in sigs if s['level']=='M'], default=0)
        days = max([s.get('days',1) for s in sigs if s['level']=='M'], default=1)

        level_str = '+'.join(levels)
        icon = '🗓️' if 'M' in levels else '⚠️'
        weight_str = f" [{weight}分]" if 'M' in levels and weight>0 else ""
        days_str = f" 第{days}日" if 'M' in levels else ""
        name_str = f" - {name}"

        final_msgs.append(f"{icon} {sticker} {ticker} {level_str}{direction}背離{weight_str}{days_str}{name_str}")

    return final_msgs

def analyze_risk(all_signals):
    month_tops = [s for s in all_signals if s['level']=='M' and s['type']=='頂背離']
    month_bots = [s for s in all_signals if s['level']=='M' and s['type']=='底背離']
    index_tops = [s for s in month_tops if s['ticker'] in INDICES]

    total_score = sum(s.get('weight',1) for s in month_tops)
    tech_score = sum(s.get('weight',1) for s in month_tops if s['index']=='NDX')
    cycle_score = sum(s.get('weight',1) for s in month_tops if s['index']=='SPX')
    index_score = sum(s.get('weight',1) for s in index_tops)

    # 大勢判斷
    advice = []
    if total_score >= 13 and index_score >= 5:
        advice.append("大熊市實錘：2000/2007級別，現金為王，SPY/QQQ做空，6-12個月")
    elif total_score >= 8 and index_score >= 5:
        advice.append("系統性風險：指數共振，SPY/QQQ減倉至30%，買VXX/TLT對沖")
    elif total_score >= 8 and tech_score >= 6:
        advice.append("科技泡沫破裂：空QQQ/SMH，避開成長股")
    elif total_score >= 8 and cycle_score >= 6:
        advice.append("經濟衰退交易：空SPY+資源股，買長債TLT避險")
    elif total_score >= 5:
        advice.append("高風險區：減倉至50%，等日線共振再操作")
    elif len(month_bots) >= 2:
        advice.append("月線底背離>=2：左側佈局，撈底信號出現")
    else:
        advice.append("震盪市：控倉操作，無大趨勢")

    impacted = []
    if index_score > 0: impacted.append("美股三大指數")
    if cycle_score >= 4: impacted.append("週期股")
    if tech_score >= 4: impacted.append("科技股")
    advice.append(f"主要影響：{' + '.join(impacted) if impacted else '暫無'}")

    return total_score, tech_score, cycle_score, index_score, [s['ticker'] for s in month_tops], advice

def main():
    all_signals = []
    hk_tz = timezone(timedelta(hours=8))
    now_str = datetime.now(hk_tz).strftime('%m-%d %H:%M')

    # Supabase 連線
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    sb = create_client(url, key) if url and key else None

    print(f"=== Radar V11 Index 開始 {now_str} ===")

    for ticker, info in {**INDICES, **SECTORS}.items():
        all_signals += scan_asset(ticker, info, sb)
    for ticker, info in FUTURES.items():
        all_signals += scan_asset(ticker, info, sb)

    # 寫入 Supabase 記錄天數
    if sb:
        try:
            sb.table("signals").delete().neq("ticker","XXX").execute()
            if all_signals:
                sb.table("signals").insert([{
                    "ticker":s['ticker'], "signal":s['type'], "level":s['level'], "weight":s.get('weight',1)
                } for s in all_signals]).execute()
        except Exception as e: print(f"Supabase error: {e}")

    if not all_signals:
        message = f"Radar V11 {now_str}\n\n今日無背離信號\n風險分數: 0/20"
        title = "Radar - No Signal"
        pri = "low"
    else:
        risk_score, tech_score, cycle_score, index_score, risk_tickers, advice = analyze_risk(all_signals)
        final_msgs = merge_signals(all_signals)

        header = []
        if risk_score >= 13:
            header.append(f"💀 末日級別 總分{risk_score} 科技{tech_score} 週期{cycle_score} 指數{index_score}")
        elif risk_score >= 8:
            header.append(f"🚨 系統風險 總分{risk_score} 科技{tech_score} 週期{cycle_score} 指數{index_score}")
        elif risk_score >= 5:
            header.append(f"⚠️ 高風險 總分{risk_score} 科技{tech_score} 週期{cycle_score} 指數{index_score}")
        else:
            header.append(f"📊 風險分數 總分{risk_score} 科技{tech_score} 週期{cycle_score} 指數{index_score}")

        if risk_tickers:
            risk_names = [f"{t}({ALL_ASSETS[t]['name']})" for t in risk_tickers]
            header.append(f"月線觸發：{', '.join(risk_names)}")
        header += advice

        message = f"Radar V11 {now_str}\n\n" + "\n\n".join(header + [""] + final_msgs)
        title = f"Risk:{risk_score} T{tech_score}C{cycle_score}I{index_score}"
        pri = "high" if risk_score >= 8 else "default"

    print("\n" + message + "\n")
    try:
        requests.post("https://ntfy.sh/sector-radar-ivan117", data=message.encode('utf-8'),
                      headers={"Title": title, "Priority": pri}, timeout=10)
    except: pass

if __name__ == "__main__":
    main()