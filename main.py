# radar_v13.2_html.py
import yfinance as yf
import os
import pandas as pd
import requests
import smtplib
import time
import base64
from io import BytesIO
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from supabase import create_client

EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': os.environ.get('EMAIL_USER'),
    'sender_password': os.environ.get('EMAIL_PASS'),
    'receiver_email': os.environ.get('EMAIL_TO', os.environ.get('EMAIL_USER'))
}

INDICES = {
    'ES=F': {'name':'標普500期貨', 'sticker':'📈', 'weight':5, 'index':'SPX', 'etf':'SPY'},
    'NQ=F': {'name':'納指100期貨', 'sticker':'📱', 'weight':5, 'index':'NDX', 'etf':'QQQ'},
    'YM=F': {'name':'道指期貨', 'sticker':'🏛️', 'weight':3, 'index':'DJI', 'etf':'DIA'},
}

SECTORS = {
    'XLE': {'name':'美股石油天然氣', 'sticker':'🛢️', 'weight':2, 'index':'SPX'},
    'KBE': {'name':'美股銀行', 'sticker':'🏦', 'weight':2, 'index':'SPX'},
    'SMH': {'name':'美股半導體', 'sticker':'💾', 'weight':3, 'index':'NDX'},
    'IGV': {'name':'美股軟件服務', 'sticker':'💿', 'weight':3, 'index':'NDX'},
    'IBB': {'name':'美股生物技術', 'sticker':'🧬', 'weight':1, 'index':'SPX'},
    'ITA': {'name':'美股航太國防', 'sticker':'✈️', 'weight':1, 'index':'SPX'},
    'XLP': {'name':'美股必需消費', 'sticker':'🛒', 'weight':1, 'index':'SPX'},
    'CARZ': {'name':'美股汽車', 'sticker':'🚗', 'weight':2, 'index':'SPX'},
    'XLB': {'name':'美股原材料', 'sticker':'🧪', 'weight':2, 'index':'SPX'},
    'XLU': {'name':'美股公用事業', 'sticker':'💡', 'weight':1, 'index':'SPX'},
    'XLRE': {'name':'美股地產', 'sticker':'🏠', 'weight':2, 'index':'SPX'},
    'XLC': {'name':'美股通訊服務', 'sticker':'📡', 'weight':2, 'index':'NDX'},
    'BOTZ': {'name':'美股AI人工智能', 'sticker':'🤖', 'weight':3, 'index':'NDX'},
    'WCLD': {'name':'美股雲計算', 'sticker':'☁️', 'weight':3, 'index':'NDX'},
    'HACK': {'name':'美股網絡安全', 'sticker':'🔒', 'weight':2, 'index':'NDX'},
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

def get_dif(data):
    if len(data) < 35: return pd.Series()
    ema12 = data['Close'].ewm(span=12).mean()
    ema26 = data['Close'].ewm(span=26).mean()
    return ema12 - ema26

def get_kdj(data):
    if len(data) < 34: return pd.Series()
    low_min = data['Low'].rolling(9).min()
    high_max = data['High'].rolling(9).max()
    rsv = (data['Close'] - low_min) / (high_max - low_min) * 100
    k = rsv.ewm(com=2).mean()
    d = k.ewm(com=2).mean()
    return 3 * k - 2 * d

def find_div(price, indicator, lookback=60):
    price = price.dropna().tail(lookback)
    indicator = indicator.dropna().tail(lookback)
    if len(price) < 20 or len(indicator) < 20: return None
    p1, p2 = price.iloc[-20:-10].idxmax(), price.iloc[-10:].idxmax()
    if pd.isna(p1) or pd.isna(p2) or p1 >= p2: return None
    i1, i2 = indicator.loc[p1], indicator.loc[p2]
    if price.loc[p2] > price.loc[p1] and i2 < i1: return '頂'
    if price.loc[p2] < price.loc[p1] and i2 > i1: return '底'
    return None

def get_hist(ticker, interval, period):
    return yf.Ticker(ticker).history(period=period, interval=interval)

def get_div_days(ticker, interval, period, indicator):
    df = get_hist(ticker, interval, period)
    if df.empty: return 0, None
    ind = get_dif(df) if indicator == 'DIF' else get_kdj(df)
    days = 0
    if not ind.empty:
        for i in range(len(df)-1, 0, -1):
            if find_div(df['Close'].iloc[:i+1], ind.iloc[:i+1]) == '頂':
                days += 1
            else: break
    return days, df

def scan_asset(ticker, info, sb_client=None):
    sigs = []
    etf_ticker = info.get('etf', ticker)
    try:
        m_df = get_hist(etf_ticker, "1mo", "2y")
        if not m_df.empty:
            m_ind = get_dif(m_df)
            m_div = find_div(m_df['Close'], m_ind)
            if m_div:
                days, _ = get_div_days(etf_ticker, "1mo", "2y", "DIF")
                sigs.append({**info, 'ticker':ticker, 'level':'M', 'type':f"M{m_div}背離[DIF]", 'dir':m_div, 'indicator':'DIF', 'days':max(1,days), 'weight':info.get('weight',1)})
            m_kdj = get_kdj(m_df)
            m_div_k = find_div(m_df['Close'], m_kdj)
            if m_div_k:
                days, _ = get_div_days(etf_ticker, "1mo", "2y", "J")
                sigs.append({**info, 'ticker':ticker, 'level':'M', 'type':f"M{m_div_k}背離[J]", 'dir':m_div_k, 'indicator':'J', 'days':max(1,days), 'weight':info.get('weight',1)})

        for lv, (intv, per) in [('W',("1wk","1y")), ('D',("1d","6mo")), ('4H',("1h","3mo"))]:
            df = get_hist(etf_ticker, intv, per)
            if df.empty: continue
            ind = get_dif(df)
            div = find_div(df['Close'], ind)
            if div: sigs.append({**info, 'ticker':ticker, 'level':lv, 'type':f"{lv}{div}背離[DIF]", 'dir':div, 'indicator':'DIF'})
    except Exception as e:
        print(f"掃描 {ticker} 失敗: {e}")
    return sigs

def merge_signals(sigs):
    out = []
    grouped = {}
    for s in sigs:
        key = (s['ticker'], s['dir'], s['indicator'])
        if key not in grouped: grouped[key] = []
        grouped[key].append(s)

    for (ticker, dir_type, ind), items in grouped.items():
        items.sort(key=lambda x: {'M':4,'W':3,'D':2,'4H':1}[x['level']])
        base = items[0]
        emoji = {'M':'🗓️','W':'📅','D':'⚠️','4H':'💾'}[base['level']]
        weight_str = f" [{base.get('weight',1)}分]" if base['level']=='M' else ""
        days_str = f" 第{base.get('days',1)}日" if base['level']=='M' else ""
        extra = [f"{i['level']}{i['dir']}背離[{i['indicator']}]" for i in items[1:]]
        extra_str = f" ({', '.join(extra)})" if extra else ""
        out.append(f"{emoji} {base['sticker']} {ticker} {base['level']}{dir_type}背離[{ind}]{weight_str}{days_str}{extra_str} - {base['name']}")
    return out

def analyze_risk(sigs):
    tech, cycle, index = 0, 0, 0
    tech_tickers, cycle_tickers, index_tickers = set(), set(), set()

    for s in sigs:
        # V13.2邏輯：M*5分 + W*2分 + D*1分
        if s['level']=='M': w = s.get('weight',1) * 5
        elif s['level']=='W': w = 2
        elif s['level']=='D': w = 1
        else: w = 0

        idx = s['index']
        if idx == 'NDX': tech += w; tech_tickers.add(s['ticker'])
        elif idx == 'SPX': cycle += w; cycle_tickers.add(s['ticker'])
        elif idx in ['SPX','NDX','DJI']: index += w; index_tickers.add(s['ticker'])

    risk_score = tech + cycle + index
    advice = []

    if index >= 10 and risk_score >= 13:
        advice = [
            "🚨 大熊市實錘：2000/2007級別股災，SPX/NDX/DJI全滅",
            "操作：清倉避險資產、ES/NQ做空、國債/黃金對沖",
            "時長：6-12個月，月線死叉確認反彈再入場",
            f"主要影響：美股三大指數期貨 + 週期股",
            f"觸發：{', '.join([ALL_ASSETS[t]['name'] for t in index_tickers])}"
        ]
    elif tech >= 10 and risk_score >= 8:
        advice = [
            "⚠️ 科技股災：科網股重災區，QQQ/ARKK重創",
            "操作：科技股清倉、SMH/SOXL止損、減槓桿",
            f"觸發：{', '.join([ALL_ASSETS[t]['name'] for t in tech_tickers])}"
        ]
    elif cycle >= 10 and risk_score >= 5:
        advice = [
            "🔄 經濟衰退：週期股殺跌，SPY/DIA受累",
            "操作：週期股減倉、XLE/KBE止損、防守股",
            f"觸發：{', '.join([ALL_ASSETS[t]['name'] for t in cycle_tickers])}"
        ]
    else:
        advice = ["📊 震盪市：無系統風險，控制倉位即可"]

    return risk_score, tech, cycle, index, list(tech_tickers|cycle_tickers|index_tickers), advice

def generate_mini_chart(ticker):
    try:
        df = yf.Ticker(ticker).history(period="1mo", interval="1d")
        if len(df) < 5: return None
        fig, ax = plt.subplots(figsize=(3, 1.5), dpi=100)
        ax.plot(df.index, df['Close'], color='black', linewidth=1.5)
        ax.fill_between(df.index, df['Close'], df['Close'].min(), alpha=0.1)
        ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values(): spine.set_visible(False)
        plt.tight_layout(pad=0)
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')
    except:
        return None

def build_html_email(risk_score, tech_score, cycle_score, index_score, risk_tickers, advice, final_msgs, all_signals):
    if risk_score >= 13: risk_color = "#8B0000"; risk_text = "末日級別"
    elif risk_score >= 8: risk_color = "#FF4500"; risk_text = "系統風險"
    elif risk_score >= 5: risk_color = "#FFA500"; risk_text = "高風險"
    else: risk_color = "#32CD32"; risk_text = "震盪市"

    month_sigs = [s for s in all_signals if s['level']=='M']
    month_html = ""
    for s in month_sigs:
        chart_b64 = generate_mini_chart(s['ticker'])
        chart_img = f'<img src="data:image/png;base64,{chart_b64}" width="150">' if chart_b64 else ""
        weight_str = f"<b>{s.get('weight',1)}分</b>"
        days_str = f"第{s.get('days',1)}日"
        tv_link = f"https://www.tradingview.com/chart/?symbol={s['ticker']}"
        month_html += f"""
        <tr style="background:{'#FFE4E1' if s['dir']=='頂' else '#E0FFE0'};">
            <td>{s['sticker']} <a href="{tv_link}">{s['ticker']}</a></td>
            <td>{s['name']}</td>
            <td><b>M{s['dir']}背離[{s['indicator']}]</b></td>
            <td>{weight_str}</td>
            <td>{days_str}</td>
            <td>{chart_img}</td>
        </tr>
        """

    html = f"""
    <html><head><style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
     .risk-box {{ padding: 15px; border-radius: 8px; color: white; background: {risk_color}; margin: 20px 0; }}
     .advice {{ background: #f0f0f0; padding: 15px; border-left: 4px solid {risk_color}; margin: 20px 0; }}
    </style></head><body>
        <div class="risk-box">
            <h2>💀 Radar V13.2 {risk_text}</h2>
            <h1>總分 {risk_score} | 科技 {tech_score} | 週期 {cycle_score} | 指數 {index_score}</h1>
        </div>
        <div class="advice"><h3>操作建議</h3>{"<br>".join([f"• {a}" for a in advice])}</div>
        <h3>月線級別信號 ({len(month_sigs)}個)</h3>
        <table><tr><th>Ticker</th><th>名稱</th><th>信號</th><th>權重</th><th>持續</th><th>30日走勢</th></tr>
        {month_html if month_html else "<tr><td colspan=6>今日無月線信號</td></tr>"}
        </table>
        <h3>全部信號明細</h3>
        <pre style="background:#f5f5f5;padding:15px;border-radius:5px;">{"<br>".join(final_msgs)}</pre>
        <p style="color:#888;font-size:12px;">Radar V13.2 | {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M HKT')}</p>
    </body></html>
    """
    return html

def send_email_html(subject, html_body, csv_path=None):
    if not EMAIL_CONFIG['sender_email'] or not EMAIL_CONFIG['sender_password']:
        print("Email未配置，跳過"); return False
    try:
        msg = MIMEMultipart('mixed')
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = EMAIL_CONFIG['receiver_email']
        msg['Subject'] = subject
        msg_alt = MIMEMultipart('alternative')
        msg_alt.attach(MIMEText("請用支援HTML的郵件客戶端查看", 'plain', 'utf-8'))
        msg_alt.attach(MIMEText(html_body, 'html', 'utf-8'))
        msg.attach(msg_alt)
        if csv_path and os.path.exists(csv_path):
            with open(csv_path, 'rb') as f:
                part = MIMEText(f.read().decode('utf-8'), 'csv', 'utf-8')
                part.add_header('Content-Disposition', 'attachment', filename='history.csv')
                msg.attach(part)
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        server.send_message(msg)
        server.quit()
        print(f"HTML Email已發送到 {EMAIL_CONFIG['receiver_email']}")
        return True
    except Exception as e:
        print(f"Email發送失敗: {e}")
        return False

def main():
    all_signals = []
    hk_tz = timezone(timedelta(hours=8))
    now_str = datetime.now(hk_tz).strftime('%m-%d %H:%M')

    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    sb = create_client(url, key) if url and key else None

    print(f"=== Radar V13.2 HTML Email 開始 {now_str} ===")

    for ticker, info in {**INDICES, **SECTORS}.items():
        all_signals += scan_asset(ticker, info, sb)
    for ticker, info in FUTURES.items():
        all_signals += scan_asset(ticker, info, sb)

    if sb:
        try:
            sb.table("signals").delete().neq("ticker","XXX").execute()
            if all_signals:
                sb.table("signals").insert([{
                    "ticker":s['ticker'], "signal":s['type'], "level":s['level'], "weight":s.get('weight',1)
                } for s in all_signals]).execute()
        except Exception as e: print(f"Supabase error: {e}")

    if not all_signals:
        message = f"Radar V13.2 {now_str}\n\n今日無背離信號\n風險分數: 0/20"
        title = "Radar - No Signal"
        requests.post("https://ntfy.sh/sector-radar-ivan117", data=message.encode('utf-8'),
            headers={"Title": title.encode('utf-8'), "Priority": "low"}, timeout=10)
        send_email_html(title, f"<h2>今日無信號</h2><p>{now_str}</p>")
    else:
        risk_score, tech, cycle, index, risk_tickers, advice = analyze_risk(all_signals)
        final_msgs = merge_signals(all_signals)

        header = []
        if risk_score >= 13: header.append(f"💀 末日級別 總分{risk_score} 科技{tech} 週期{cycle} 指數{index}")
        elif risk_score >= 8: header.append(f"🚨 系統風險 總分{risk_score} 科技{tech} 週期{cycle} 指數{index}")
        elif risk_score >= 5: header.append(f"⚠️ 高風險 總分{risk_score} 科技{tech} 週期{cycle} 指數{index}")
        else: header.append(f"📊 風險分數 總分{risk_score} 科技{tech} 週期{cycle} 指數{index}")

        if risk_tickers:
            risk_names = [f"{t}({ALL_ASSETS[t]['name']})" for t in risk_tickers]
            header.append(f"月線觸發：{', '.join(risk_names)}")
        header += advice

        summary_msg = f"Radar V13.2 {now_str}\n\n" + "\n\n".join(header)
        title = f"Risk{risk_score} T{tech}C{cycle}I{index}"
        pri = "max" if risk_score >= 13 else "high" if risk_score >= 8 else "default"

        requests.post("https://ntfy.sh/sector-radar-ivan117", data=summary_msg.encode('utf-8'),
            headers={"Title": f"💀 {title}".encode('utf-8'), "Priority": pri}, timeout=10)
        time.sleep(2)
        detail_msg = f"信號明細 {now_str}\n\n" + "\n".join(final_msgs)
        requests.post("https://ntfy.sh/sector-radar-ivan117", data=detail_msg.encode('utf-8'),
            headers={"Title": f"📊 信號明細 Risk{risk_score}".encode('utf-8'), "Priority": "default"}, timeout=10)

        html_body = build_html_email(risk_score, tech, cycle, index, risk_tickers, advice, final_msgs, all_signals)
        email_subject = f"💀 {title} - {now_str}"
        send_email_html(email_subject, html_body, 'history.csv')

    print("\n發送完成\n")

if __name__ == "__main__":
    main()