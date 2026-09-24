# radar_v11_weighted_merge.py - 合併多週期背離顯示
import yfinance as yf
import os
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta

SECTORS = {
    'XLE': {'name':'石油天然氣', 'sticker':'🛢️', 'weight':2},
    'KBE': {'name':'銀行', 'sticker':'🏦', 'weight':2},
    'SMH': {'name':'半導體', 'sticker':'💾', 'weight':3},
    'IGV': {'name':'軟件服務', 'sticker':'💿', 'weight':3},
    'IBB': {'name':'生物技術', 'sticker':'🧬', 'weight':1},
    'ITA': {'name':'航太國防', 'sticker':'✈️', 'weight':1},
    'XLP': {'name':'必需消費', 'sticker':'🛒', 'weight':1},
    'CARZ': {'name':'汽車', 'sticker':'🚗', 'weight':2},
    'XLB': {'name':'原材料', 'sticker':'🧪', 'weight':2},
    'XLU': {'name':'公用事業', 'sticker':'💡', 'weight':1},
    'XLRE': {'name':'地產', 'sticker':'🏠', 'weight':2},
    'XLC': {'name':'通訊服務', 'sticker':'📡', 'weight':2},
    'BOTZ': {'name':'AI人工智能', 'sticker':'🤖', 'weight':3},
    'WCLD': {'name':'雲計算', 'sticker':'☁️', 'weight':3},
    'HACK': {'name':'網絡安全', 'sticker':'🔒', 'weight':2},
}

FUTURES = {
    'GC=F': {'name':'黃金期貨', 'sticker':'🥇'},
    'SI=F': {'name':'白銀期貨', 'sticker':'🥈'},
    'CL=F': {'name':'原油期貨', 'sticker':'⛽'},
    'DX-Y.NYB': {'name':'美元指數', 'sticker':'💵'},
    'ZN=F': {'name':'十年國債', 'sticker':'📜'},
    '^VIX': {'name':'恐慌指數', 'sticker':'😱'},
}

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

def scan_asset(code, info, asset_type):
    raw_signals = []
    try:
        df_d = get_hist(code, "1y", "1d")
        df_w = get_hist(code, "3y", "1wk")
        df_m = get_hist(code, "10y", "1mo")
        df_60m = get_hist(code, "3mo", "60m")
        
        if len(df_d)<50: return []

        high_50=round(float(df_d['High'].iloc[-50:].max()),2)
        close=float(df_d['Close'].iloc[-1])
        dist_50=round((close/high_50-1)*100,2)
        print(f"{code} {info['name']} Close:{close} Dist50:{dist_50}%")

        if asset_type == "ETF":
            if dist_50 >= -2.0:
                if close >= high_50 * 0.998 and close == df_d['High'].iloc[-50:].max():
                    raw_signals.append({'ticker':code, 'level':'D', 'type':'新高', 'dir':'', 'sticker':info['sticker'], 'name':info['name']})
                else:
                    raw_signals.append({'ticker':code, 'level':'D', 'type':'逼近', 'dir':'', 'sticker':info['sticker'], 'name':info['name'], 'dist':dist_50})
            if dist_50 <= -15.0:
                raw_signals.append({'ticker':code, 'level':'D', 'type':'超賣', 'dir':'', 'sticker':info['sticker'], 'name':info['name'], 'dist':dist_50})

        # 月線
        if len(df_m)>=30:
            j=get_kdj(df_m).dropna()
            if len(j)>=5:
                div = find_div(df_m['Close'].loc[j.index], j)
                if div and ((div=="頂背離" and j.iloc[-1]<j.iloc[-2]) or (div=="底背離" and j.iloc[-1]>j.iloc[-2])):
                    raw_signals.append({'ticker':code, 'level':'M', 'type':div, 'dir':'頂' if '頂' in div else '底', 
                                       'weight':info.get('weight',1), 'sticker':info['sticker'], 'name':info['name']})

        # 週線
        if len(df_w)>=60:
            div = find_div(df_w['Close'], get_dif(df_w['Close']))
            if div:
                raw_signals.append({'ticker':code, 'level':'W', 'type':div, 'dir':'頂' if '頂' in div else '底',
                                   'sticker':info['sticker'], 'name':info['name']})

        # 4H
        if len(df_60m)>=60:
            df_4h=df_60m.resample("4h").agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
            if len(df_4h)>=60:
                div = find_div(df_4h['Close'], get_dif(df_4h['Close']))
                if div: 
                    raw_signals.append({'ticker':code, 'level':'4H', 'type':div, 'dir':'頂' if '頂' in div else '底',
                                       'sticker':info['sticker'], 'name':info['name']})

    except Exception as e:
        print(f"skip {code} {e}")
    
    return raw_signals

def merge_signals(all_signals):
    """合併同一ticker多週期背離，4H+週+月一行"""
    grouped = {}
    for s in all_signals:
        key = (s['ticker'], s.get('dir','')) # 頂背離同底背離分開合併
        grouped.setdefault(key, []).append(s)
    
    final_msgs = []
    level_order = {'4H':1, 'W':2, 'M':3, 'D':4} # 排序用
    
    for (ticker, direction), sigs in grouped.items():
        if not direction: # 新高/逼近/超賣，直接出
            for s in sigs:
                if s['type']=='新高': final_msgs.append(f"🚀 {s['sticker']} {s['ticker']} 50日新高")
                elif s['type']=='逼近': final_msgs.append(f"🔝 {s['sticker']} {s['ticker']} 逼近50日頂 僅{s['dist']}%")
                elif s['type']=='超賣': final_msgs.append(f"🔻 {s['sticker']} {s['ticker']} 遠離高位 {s['dist']}%")
            continue
            
        # 背離類，合併週期
        sigs_sorted = sorted(sigs, key=lambda x: level_order[x['level']])
        levels = [s['level'] for s in sigs_sorted if s['level'] in ['4H','W','M']]
        if not levels: continue
        
        sticker = sigs[0]['sticker']
        name = sigs[0]['name']
        weight = max([s.get('weight',1) for s in sigs if s['level']=='M'], default=1)
        
        level_str = '+'.join(levels) # 4H+W+M
        icon = '🗓️' if 'M' in levels else '⚠️'
        weight_str = f" [{weight}分]" if 'M' in levels else ""
        
        final_msgs.append(f"{icon} {sticker} {ticker} {level_str}{direction}背離{weight_str} - {name}")
    
    return final_msgs

def calc_risk_score(all_signals):
    month_tops = [s for s in all_signals if s['level']=='M' and s['type']=='頂背離']
    total_weight = sum(s.get('weight',1) for s in month_tops)
    tech_weight = sum(s.get('weight',1) for s in month_tops if s.get('weight',1)>=3)
    cycle_weight = total_weight - tech_weight
    tickers = [s['ticker'] for s in month_tops]
    return total_weight, tech_weight, cycle_weight, tickers

def main():
    all_signals = []
    hk_tz = timezone(timedelta(hours=8))
    now_str = datetime.now(hk_tz).strftime('%m-%d %H:%M')
    
    print(f"=== Radar V11 Merge 開始 {now_str} ===")
    
    for ticker, info in SECTORS.items():
        all_signals += scan_asset(ticker, info, "ETF")
    for ticker, info in FUTURES.items():
        all_signals += scan_asset(ticker, info, "FUT")

    risk_score, tech_score, cycle_score, risk_tickers = calc_risk_score(all_signals)
    final_msgs = merge_signals(all_signals)
    
    if risk_score >= 8:
        final_msgs.insert(0, f"🚨🚨 系統性風險！總分{risk_score}分 科技{tech_score}分 週期{cycle_score}分")
        final_msgs.insert(1, f"觸發：{', '.join(risk_tickers)}")
    elif risk_score >= 5:
        final_msgs.insert(0, f"⚠️ 高風險！總分{risk_score}分 科技{tech_score}分 週期{cycle_score}分")
    
    if final_msgs:
        message = f"Radar V11 {now_str}\n\n" + "\n\n".join(final_msgs)
        title = f"Risk: {risk_score}/20 T{tech_score}C{cycle_score}"
        pri = "high" if risk_score >= 8 else "default"
    else:
        message = f"Radar V11 {now_str}\n\n今日無信號\n風險分數: 0/20"
        title = "Radar - No Signal"
        pri = "low"

    print("\n" + message + "\n")
    try:
        requests.post("https://ntfy.sh/sector-radar-ivan117", data=message.encode('utf-8'), 
                      headers={"Title": title, "Priority": pri}, timeout=10)
    except: pass

if __name__ == "__main__":
    main()