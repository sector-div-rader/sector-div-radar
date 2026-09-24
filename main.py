# radar_v11.py - ETF板塊 + 期貨背離版，去重4H噪音
import yfinance as yf
import os
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta

SECTORS = {
    'XLE':   {'name':'石油天然氣', 'sticker':'🛢️'},
    'KBE':   {'name':'銀行',       'sticker':'🏦'},
    'SMH':   {'name':'半導體',     'sticker':'💾'},
    'IGV':   {'name':'軟件服務',   'sticker':'💿'},
    'IBB':   {'name':'生物技術',   'sticker':'🧬'},
    'ITA':   {'name':'航太國防',   'sticker':'✈️'},
    'XLP':   {'name':'必需消費',   'sticker':'🛒'},
    'CARZ':  {'name':'汽車',       'sticker':'🚗'},
    'XLB':   {'name':'原材料',     'sticker':'🧪'},
    'XLU':   {'name':'公用事業',   'sticker':'💡'},
    'XLRE':  {'name':'地產',       'sticker':'🏠'},
    'XLC':   {'name':'通訊服務',   'sticker':'📡'},
    'BOTZ':  {'name':'AI人工智能', 'sticker':'🤖'},
    'WCLD':  {'name':'雲計算',     'sticker':'☁️'},
    'HACK':  {'name':'網絡安全',   'sticker':'🔒'},
}

FUTURES = {
    'GC=F':     {'name':'黃金期貨', 'sticker':'🥇'},
    'SI=F':     {'name':'白銀期貨', 'sticker':'🥈'},
    'CL=F':     {'name':'原油期貨', 'sticker':'⛽'},
    'DX-Y.NYB': {'name':'美元指數', 'sticker':'💵'},
    'ZN=F':     {'name':'十年國債', 'sticker':'📜'},
    '^VIX':     {'name':'恐慌指數', 'sticker':'😱'},
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
    except Exception as e:
        print(f"get_hist error {ticker}: {e}")
        return pd.DataFrame()

def scan_asset(code, info, asset_type):
    raw_signals = []  # 改成存原始信號，唔直接分major/minor
    ticker = code
    try:
        df_d = get_hist(ticker, "1y", "1d")
        df_w = get_hist(ticker, "3y", "1wk")
        df_m = get_hist(ticker, "10y", "1mo")
        df_60m = get_hist(ticker, "3mo", "60m")
        
        if len(df_d)<50:
            print(f"skip {code} 無數據")
            return []

        high_50=round(float(df_d['High'].iloc[-50:].max()),2)
        high_200=round(float(df_d['High'].iloc[-200:].max()),2) if len(df_d)>=200 else round(float(df_d['High'].max()),2)
        close=float(df_d['Close'].iloc[-1])
        dist_50=round((close/high_50-1)*100,2)
        dist_200=round((close/high_200-1)*100,2)

        print(f"{code} {info['name']} Close:{close} Dist50:{dist_50}%")

        if asset_type == "ETF":
            if dist_50 >= -2.0:
                if close >= high_50 * 0.998 and close == df_d['High'].iloc[-50:].max():
                    raw_signals.append({'ticker':code, 'level':'D', 'type':'新高', 'msg':f"🚀 {info['sticker']} {code} 50日新高 - {info['name']}"})
                else:
                    raw_signals.append({'ticker':code, 'level':'D', 'type':'逼近', 'msg':f"🔝 {info['sticker']} {code} 逼近50日頂 - {info['name']} 僅{dist_50}%"})
            if dist_50 <= -15.0:
                raw_signals.append({'ticker':code, 'level':'D', 'type':'超賣', 'msg':f"🔻 {info['sticker']} {code} 遠離高位 - {info['name']} {dist_50}% 可能超賣"})

        # 月線
        if len(df_m)>=30:
            j=get_kdj(df_m).dropna()
            if len(j)>=5:
                div=find_div(df_m['Close'].loc[j.index], j)
                if div:
                    j_now=float(j.iloc[-1]); j_prev=float(j.iloc[-2])
                    if ("頂" in div and j_now<j_prev) or ("底" in div and j_now>j_prev):
                        raw_signals.append({'ticker':code, 'level':'M', 'type':div, 'msg':f"🗓️🗓️ {info['sticker']} {code} 月線{div} - {info['name']}見大{'頂' if '頂' in div else '底'}"})

        # 週線
        if len(df_w)>=60:
            div=find_div(df_w['Close'], get_dif(df_w['Close']))
            if div:
                raw_signals.append({'ticker':code, 'level':'W', 'type':div, 'msg':f"⚠️ {info['sticker']} {code} 週線{div} - {info['name']}見{'頂' if '頂' in div else '底'}"})

        # 4H
        if len(df_60m)>=60:
            df_4h=df_60m.resample("4h").agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
            if len(df_4h)>=60:
                div=find_div(df_4h['Close'], get_dif(df_4h['Close']))
                if div: 
                    raw_signals.append({'ticker':code, 'level':'4H', 'type':div, 'msg':f"({info['sticker']} {code} 4H{div} - {info['name']})"})

    except Exception as e:
        print(f"skip {code} {e}")
    
    return raw_signals

def dedupe_signals(all_signals):
    """去重：同一個ticker，有月線/週線就唔要4H"""
    final_msgs = []
    # 按ticker分組
    grouped = {}
    for s in all_signals:
        grouped.setdefault(s['ticker'], []).append(s)
    
    for ticker, sigs in grouped.items():
        levels = {s['level'] for s in sigs}
        for s in sigs:
            # 如果有M或W，就唔要4H
            if s['level'] == '4H' and ('M' in levels or 'W' in levels):
                continue
            final_msgs.append(s['msg'])
    
    return final_msgs

def main():
    all_signals = []
    hk_tz = timezone(timedelta(hours=8))
    now_str = datetime.now(hk_tz).strftime('%m-%d %H:%M')
    
    print(f"=== Radar V11 ETF+Futures 開始 {now_str} ===")
    
    for ticker, info in SECTORS.items():
        all_signals += scan_asset(ticker, info, "ETF")

    for ticker, info in FUTURES.items():
        all_signals += scan_asset(ticker, info, "FUT")

    # 去重過濾
    final_msgs = dedupe_signals(all_signals)
    
    # 系統風險提醒
    month_top = len([s for s in all_signals if s['level']=='M' and '頂背離' in s['type']])
    if month_top >= 3:
        final_msgs.insert(0, f"🚨🚨 月線頂背離{month_top}個，系統性風險！")

    # Supabase
    signals_db = [{"ticker":s['ticker'], "signal":s['type'], "level":s['level']} for s in all_signals]
    try:
        from supabase import create_client
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_KEY')
        if url and key:
            sb=create_client(url, key)
            sb.table("signals").delete().neq("ticker","XXX").execute()
            if signals_db:
                sb.table("signals").insert(signals_db).execute()
            print(f"Supabase OK {len(signals_db)} 筆")
    except Exception as e:
        print(f"Supabase error: {e}")

    if final_msgs:
        message = f"Radar V11 {now_str}\n\n" + "\n\n".join(final_msgs)
        title = "Sector+Futures Radar"
        pri = "high" if any('🗓️' in m for m in final_msgs) else "default"
    else:
        message = f"Radar V11 {now_str}\n\n今日無背離\n已掃描 {len(SECTORS)+len(FUTURES)} 個資產"
        title = "Radar - No Signal"
        pri = "low"

    print("\n" + message + "\n")
    
    try:
        requests.post("https://ntfy.sh/sector-radar-ivan117", 
                      data=message.encode('utf-8'), 
                      headers={"Title": title, "Priority": pri}, 
                      timeout=10)
        print("ntfy sent OK")
    except Exception as e:
        print(f"ntfy error {e}")

if __name__ == "__main__":
    main()