import yfinance as yf, requests, os
ETFS = ["XLB","XLE","XLF","XLI","XLK","XLP","XLU","XLV","XLY","XLG","XLC"]
for sym in ETFS:
    t = yf.Ticker(sym)
    hist = t.history(period="2d")
    try:
        shares = t.info.get('floatShares') or t.info.get('sharesOutstanding')
        turnover = hist['Volume'].iloc[-1] / shares * 100
        if turnover > 5:
            msg = f"🔥【高換手】{sym} 今日換手率 {turnover:.2f}% >5%"
            requests.get(f"https://api.callmebot.com/whatsapp.php?phone=85263306575&text={msg}&apikey={os.getenv('CALLMEBOT_APIKEY')}")
    except: pass