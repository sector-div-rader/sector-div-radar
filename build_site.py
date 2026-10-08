# build_site.py - 生成 index.html Dashboard V18.0
# ============================================
# 讀 history.csv，生成 index.html
# ============================================

import os
import pandas as pd
from datetime import datetime, timezone, timedelta

def build_html():
    now_hkt = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    
    # 讀 history.csv
    if not os.path.exists('history.csv'):
        print("⚠️ history.csv 唔存在，生成空頁")
        df = pd.DataFrame()
    else:
        try:
            df = pd.read_csv('history.csv', encoding='utf-8-sig')
        except Exception as e:
            print(f"⚠️ 讀 history.csv 失敗: {e}")
            df = pd.DataFrame()
    
    # 今日訊號
    today = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    if not df.empty and '日期' in df.columns:
        today_df = df[df['日期'] == today]
    else:
        today_df = pd.DataFrame()
    
    # 統計（最近 30 日）
    if not df.empty and '日期' in df.columns:
        df['日期'] = pd.to_datetime(df['日期'])
        cutoff = datetime.now() - timedelta(days=30)
        recent = df[df['日期'] >= cutoff]
    else:
        recent = pd.DataFrame()
    
    # 生成表格 HTML
    def df_to_table(d, cols=None):
        if d.empty:
            return "<p style='color:#888;'>暫無數據</p>"
        if cols:
            d = d[cols]
        return d.to_html(index=False, classes='table', border=0, escape=False)
    
    # 統計資訊
    total_signals = len(df) if not df.empty else 0
    today_count = len(today_df) if not today_df.empty else 0
    
    # 強度分佈
    strength_stats = ""
    if not recent.empty and '強度' in recent.columns:
        counts = recent['強度'].value_counts()
        for s in ['強', '中', '弱']:
            c = counts.get(s, 0)
            strength_stats += f"<span class='badge'>{s}: {c}</span>"
    
    # 標的 TOP 5
    ticker_stats = ""
    if not recent.empty and '標的' in recent.columns:
        top = recent['標的'].value_counts().head(5)
        for t, c in top.items():
            ticker_stats += f"<span class='badge'>{t}: {c}</span>"
    
    html = f"""<!DOCTYPE html>
<html lang="zh-HK">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>⚡ 0DTE Radar Dashboard</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #0d1117; color: #c9d1d9;
    margin: 0; padding: 20px;
  }}
  .container {{ max-width: 1400px; margin: 0 auto; }}
  h1 {{ color: #58a6ff; border-bottom: 2px solid #30363d; padding-bottom: 10px; }}
  h2 {{ color: #58a6ff; margin-top: 30px; border-left: 4px solid #58a6ff; padding-left: 10px; }}
  .card {{
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    padding: 15px; margin: 10px 0;
  }}
  .stats {{ display: flex; gap: 15px; flex-wrap: wrap; margin: 15px 0; }}
  .stat-box {{
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    padding: 15px 20px; min-width: 120px; text-align: center;
  }}
  .stat-box .num {{ font-size: 28px; font-weight: bold; color: #58a6ff; }}
  .stat-box .label {{ font-size: 12px; color: #8b949e; margin-top: 5px; }}
  .badge {{
    display: inline-block; padding: 4px 10px; margin: 3px;
    background: #21262d; border-radius: 12px; font-size: 13px;
    border: 1px solid #30363d;
  }}
  table.table {{
    width: 100%; border-collapse: collapse; font-size: 13px;
    margin-top: 10px;
  }}
  table.table th {{
    background: #21262d; color: #58a6ff; padding: 10px;
    text-align: left; border-bottom: 2px solid #30363d;
    position: sticky; top: 0;
  }}
  table.table td {{
    padding: 8px 10px; border-bottom: 1px solid #21262d;
  }}
  table.table tr:hover {{ background: #1c2128; }}
  .footer {{
    margin-top: 40px; text-align: center; color: #8b949e;
    font-size: 12px; border-top: 1px solid #30363d; padding-top: 20px;
  }}
  .scroll {{ overflow-x: auto; max-height: 600px; overflow-y: auto; }}
</style>
</head>
<body>
<div class="container">

<h1>⚡ 0DTE Radar Dashboard</h1>
<p style="color:#8b949e;">最後更新：{now_hkt} HKT</p>

<div class="stats">
  <div class="stat-box">
    <div class="num">{total_signals}</div>
    <div class="label">總訊號數</div>
  </div>
  <div class="stat-box">
    <div class="num">{today_count}</div>
    <div class="label">今日訊號</div>
  </div>
</div>

<h2>📊 強度分佈（最近 30 日）</h2>
<div class="card">
  {strength_stats if strength_stats else '<p style="color:#888;">暫無數據</p>'}
</div>

<h2>📈 熱門標的 TOP 5（最近 30 日）</h2>
<div class="card">
  {ticker_stats if ticker_stats else '<p style="color:#888;">暫無數據</p>'}
</div>

<h2>🔥 今日訊號</h2>
<div class="card scroll">
  {df_to_table(today_df)}
</div>

<h2>📜 歷史紀錄（最近 30 日）</h2>
<div class="card scroll">
  {df_to_table(recent.tail(200))}
</div>

<div class="footer">
  ⚡ Radar V18.0 | Powered by GitHub Actions + GitHub Pages
</div>

</div>
</body>
</html>"""
    
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ 生成 index.html ({len(html)} 字元)")

if __name__ == '__main__':
    build_html()
