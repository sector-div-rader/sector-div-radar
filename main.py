# radar_v11.py - ETF板塊 + 期貨背離版，無成交量
import yfinance as yf
import os
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta

# ========== 板塊用ETF，數據穩定 ==========
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

# ========== 期貨保留 ==========
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
    major, minor, signals = [], [], []
    ticker = code if asset_type == "ETF" else code
    try:
        df_d = get_hist(ticker, "1y", "1d")
        df_w = get_hist(ticker, "3y", "1wk")
        df_m = get_hist(ticker, "10y", "1mo")
        df_60m = get_hist(ticker, "3mo", "60m")
        
        if len(df_d)<50:
            print(f"skip {code} 無數據")
            return [], [], []

        high_50=round(float(df_d['High'].iloc[-50:].max()),2)
        high_200=round(float(df_d['High'].iloc[-200:].max()),2) if len(df_d)>=200 else round(float(df_d['High'].max()),2)
        close=float(df_d['Close'].iloc[-1])
        dist_50=round((close/high_50-1)*100,2)
        dist_200=round((close/high_200-1)*100,2)

        print(f"{code} {info['name']} Close:{close} Dist50:{dist_50}%")

        if asset_type == "ETF":
            if dist_50 >= -2.0:
                if close >= high_50 * 0.998 and close == df_d['High'].iloc[-50:].max():
                    major.append(f"🚀 {info['sticker']} {code} 50日新高 - {info['name']}")
                else:
                    major.append(f"🔝 {info['sticker']} {code} 逼近50日頂 - {info['name']} 僅{dist_50}%")
            if dist_50 <= -15.0:
                major.append(f"🔻 {info['sticker']} {code} 遠離高位 - {info['name']} {dist_50}% 可能超賣")

        sig="正常"
        if len(df_m)>=30:
            j=get_kdj(df_m).dropna()
            if len(j)>=5:
                div=find_div(df_m['Close'].loc[j.index], j)
                if div:
                    j_now=float(j.iloc[-1]); j_prev=float(j.iloc[-2])
                    if ("頂" in div and j_now<j_prev) or ("底" in div and j_now>j_prev):
                        sig=f"月線{div}"
                        major.append(f"🗓️🗓️ {info['sticker']} {code} {sig} - {info['name']}見大{'頂' if '頂' in div else '底'}")

        if len(df_w)>=60:
            div=find_div(df_w['Close'], get_dif(df_w['Close']))
            if div:
                if sig=="正常": sig=f"週線{div}"
                major.append(f"⚠️ {info['sticker']} {code} 週線{div} - {info['name']}見{'頂' if '頂' in div else '底'}")

        if len(df_60m)>=60:
            df_4h=df_60m.resample("4h").agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
            if len(df_4h)>=60:
                div=find_div(df_4h['Close'], get_dif(df_4h['Close']))
                if div: minor.append(f"{info['sticker']} {code} 4H{div} - {info['name']}")

        signals.append({"ticker":code, "name_cn":info['name'], "dist_50d":dist_50, "dist_200d":dist_200, "signal":sig, "type":asset_type})
    except Exception as e:
        print(f"skip {code} {e}")
    
    return major, minor, signals

def main():
    signals, major, minor = [], [], []
    hk_tz = timezone(timedelta(hours=8))
    now_str = datetime.now(hk_tz).strftime('%m-%d %H:%M')
    
    print(f"=== Radar V11 ETF+Futures 開始 {now_str} ===")
    
    for ticker, info in SECTORS.items():
        ma, mi, sig = scan_asset(ticker, info, "ETF")
        major += ma; minor += mi; signals += sig

    for ticker, info in FUTURES.items():
        ma, mi, sig = scan_asset(ticker, info, "FUT")
        major += ma; minor += mi; signals += sig

    # Supabase
    try:
        from supabase import create_client
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_KEY')
        if url and key:
            sb=create_client(url, key)
            sb.table("signals").delete().neq("ticker","XXX").execute()
            if signals:
                sb.table("signals").insert(signals).execute()
            print(f"Supabase OK {len(signals)} 筆")
    except Exception as e:
        print(f"Supabase error: {e}")

    all_msgs = major + [f"({m})" for m in minor]
    if all_msgs:
        message = f"Radar V11 {now_str}\n\n" + "\n\n".join(all_msgs)
        title = "Sector+Futures Radar"
        pri = "high"
    else:
        message = f"Radar V11 {now_str}\n\n今日無背離\n已掃描 {len(signals)} 個資產"
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