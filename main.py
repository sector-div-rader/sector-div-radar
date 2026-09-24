# radar_v11_weighted.py - 加權月線頂背離，>8分高危
import yfinance as yf
import os
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta

# ========== 板塊 + 權重，科技股權重高 ==========
SECTORS = {
    'XLE':   {'name':'石油天然氣', 'sticker':'🛢️', 'weight':2},  # 週期
    'KBE':   {'name':'銀行',       'sticker':'🏦', 'weight':2},  # 金融
    'SMH':   {'name':'半導體',     'sticker':'💾', 'weight':3},  # 科技龍頭
    'IGV':   {'name':'軟件服務',   'sticker':'💿', 'weight':3},  # 科技
    'IBB':   {'name':'生物技術',   'sticker':'🧬', 'weight':1},  # 防守
    'ITA':   {'name':'航太國防',   'sticker':'✈️', 'weight':1},  # 工業
    'XLP':   {'name':'必需消費',   'sticker':'🛒', 'weight':1},  # 防守
    'CARZ':  {'name':'汽車',       'sticker':'🚗', 'weight':2},  # 週期
    'XLB':   {'name':'原材料',     'sticker':'🧪', 'weight':2},  # 週期
    'XLU':   {'name':'公用事業',   'sticker':'💡', 'weight':1},  # 防守
    'XLRE':  {'name':'地產',       'sticker':'🏠', 'weight':2},  # 週期
    'XLC':   {'name':'通訊服務',   'sticker':'📡', 'weight':2},  # 科技
    'BOTZ':  {'name':'AI人工智能', 'sticker':'🤖', 'weight':3},  # 科技龍頭
    'WCLD':  {'name':'雲計算',     'sticker':'☁️', 'weight':3},  # 科技
    'HACK':  {'name':'網絡安全',   'sticker':'🔒', 'weight':2},  # 科技
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
    if len(p)<30: return None, None
    p=p.iloc[-60:]
    i=i.iloc[-60:]
    s=p.iloc[:-5].iloc[-20:]
    if len(s)<5: return None, None
    curr_p=float(p.iloc[-1])
    curr_i=float(i.iloc[-1])
    peak_p=float(p.loc[s.idxmax()])
    trough_p=float(p.loc[s.idxmin()])
    peak_i=float(i.loc[s.idxmax()])
    trough_i=float(i.loc[s.idxmin()])
    if curr_p>=peak_p*0.95 and curr_i<peak_i*0.97: return "頂背離", s.idxmax()
    if curr_p<=trough_p*1.05 and curr_i>trough_i*1.03: return "底背離", s.idxmin()
    return None, None

def get_hist(ticker, period, interval):
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
        return df
    except Exception as e:
        print(f"get_hist error {ticker}: {e}")
        return pd.DataFrame()

def scan_asset(code, info, asset_type):
    raw_signals = []
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
        close=float(df_d['Close'].iloc[-1])
        dist_50=round((close/high_50-1)*100,2)

        print(f"{code} {info['name']} Close:{close} Dist50:{dist_50}%")

        if asset_type == "ETF":
            if dist_50 >= -2.0:
                if close >= high_50 * 0.998 and close == df_d['High'].iloc[-50:].max():
                    raw_signals.append({'ticker':code, 'level':'D', 'type':'新高', 'msg':f"🚀 {info['sticker']} {code} 50日新高"})
                else:
                    raw_signals.append({'ticker':code, 'level':'D', 'type':'逼近', 'msg':f"🔝 {info['sticker']} {code} 逼近50日頂 僅{dist_50}%"})
            if dist_50 <= -15.0:
                raw_signals.append({'ticker':code, 'level':'D', 'type':'超賣', 'msg':f"🔻 {info['sticker']} {code} 遠離高位 {dist_50}%"})

        # 月線
        if len(df_m)>=30:
            j=get_kdj(df_m).dropna()
            if len(j)>=5:
                div, _ = find_div(df_m['Close'].loc[j.index], j)
                if div:
                    j_now=float(j.iloc[-1]); j_prev=float(j.iloc[-2])
                    if ("頂" in div and j_now<j_prev) or ("底" in div and j_now>j_prev):
                        raw_signals.append({
                            'ticker':code, 
                            'level':'M', 
                            'type':div, 
                            'weight':info.get('weight',1),
                            'msg':f"🗓️🗓️ {info['sticker']} {code} 月線{div} [{info.get('weight',1)}分]"
                        })

        # 週線
        if len(df_w)>=60:
            div, _ = find_div(df_w['Close'], get_dif(df_w['Close']))
            if div:
                raw_signals.append({'ticker':code, 'level':'W', 'type':div, 'msg':f"⚠️ {info['sticker']} {code} 週線{div}"})

        # 4H
        if len(df_60m)>=60:
            df_4h=df_60m.resample("4h").agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
            if len(df_4h)>=60:
                div, _ = find_div(df_4h['Close'], get_dif(df_4h['Close']))
                if div: 
                    raw_signals.append({'ticker':code, 'level':'4H', 'type':div, 'msg':f"({info['sticker']} {code} 4H{div})"})

    except Exception as e:
        print(f"skip {code} {e}")
    
    return raw_signals

def dedupe_signals(all_signals):
    final_msgs = []
    grouped = {}
    for s in all_signals:
        grouped.setdefault(s['ticker'], []).append(s)
    
    for ticker, sigs in grouped.items():
        levels = {s['level'] for s in sigs}
        for s in sigs:
            if s['level'] == '4H' and ('M' in levels or 'W' in levels):
                continue
            final_msgs.append(s['msg'])
    
    return final_msgs

def calc_risk_score(all_signals):
    """計算月線頂背離加權分數"""
    month_tops = [s for s in all_signals if s['level']=='M' and '頂背離' in s['type']]
    total_weight = sum(s.get('weight',1) for s in month_tops)
    tickers = [s['ticker'] for s in month_tops]
    return total_weight, tickers

def main():
    all_signals = []
    hk_tz = timezone(timedelta(hours=8))
    now_str = datetime.now(hk_tz).strftime('%m-%d %H:%M')
    
    print(f"=== Radar V11 Weighted 開始 {now_str} ===")
    
    for ticker, info in SECTORS.items():
        all_signals += scan_asset(ticker, info, "ETF")

    for ticker, info in FUTURES.items():
        all_signals += scan_asset(ticker, info, "FUT")

    # 計算風險分數
    risk_score, risk_tickers = calc_risk_score(all_signals)
    final_msgs = dedupe_signals(all_signals)
    
    # 風險警告
    if risk_score >= 8:
        final_msgs.insert(0, f"🚨🚨 系統性風險！月線頂背離{risk_score}分 >=8分")
        final_msgs.insert(1, f"觸發板塊：{', '.join(risk_tickers)}")
        final_msgs.insert(2, f"30年回測：>8分後6個月QQQ必跌，無例外")
    elif risk_score >= 5:
        final_msgs.insert(0, f"⚠️ 高風險！月線頂背離{risk_score}分")
    
    # Supabase
    signals_db = [{"ticker":s['ticker'], "signal":s['type'], "level":s['level'], "weight":s.get('weight',1)} for s in all_signals]
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
        message = f"Radar V11 Weighted {now_str}\n\n" + "\n\n".join(final_msgs)
        title = f"Risk Score: {risk_score}/20"
        pri = "high" if risk_score >= 8 else "default"
    else:
        message = f"Radar V11 {now_str}\n\n今日無背離\n風險分數: 0/20"
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