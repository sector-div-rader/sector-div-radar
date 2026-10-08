# build_site.py - 生成 index.html Dashboard V18.3
# ============================================
# V18.3 改動：
#   1. 歷史趨勢圖（Chart.js）
#   2. Top 5 標的橫向柱狀圖
#   3. 強度分佈甜甜圈圖
#   4. 多週期共振排行榜
#   5. 點擊 row 彈出詳細 modal
#   6. 今日 vs 昨日對比
#   7. NQ 關鍵位進度條
#   8. 多標的搜尋（逗號分隔）
#   9. 匯出 CSV
#   10. 深色 / 淺色切換
#   11. 強度進度條
#   12. 箭頭方向
#   13. 卡片 hover 動畫
#   14. Sticky header 漸變
#   15. 手機優化
# ============================================

import os
import pandas as pd
from datetime import datetime, timezone, timedelta

def build_html():
    now_hkt = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    today = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    yesterday = (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # 讀 history.csv
    if not os.path.exists('history.csv'):
        df = pd.DataFrame()
    else:
        try:
            df = pd.read_csv('history.csv', encoding='utf-8-sig')
        except Exception as e:
            print(f"⚠️ 讀 history.csv 失敗: {e}")
            df = pd.DataFrame()
    
    if not df.empty and '日期' in df.columns:
        df['日期_str'] = df['日期'].astype(str).str[:10]
        today_df = df[df['日期_str'] == today]
        yesterday_df = df[df['日期_str'] == yesterday]
        df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        cutoff = datetime.now() - timedelta(days=30)
        recent = df[df['日期'] >= cutoff]
    else:
        today_df = pd.DataFrame()
        yesterday_df = pd.DataFrame()
        recent = pd.DataFrame()
    
    # ===== 統計數字 =====
    total_signals = len(df) if not df.empty else 0
    today_count = len(today_df)
    yesterday_count = len(yesterday_df)
    today_top = len(today_df[today_df['方向'] == '頂']) if not today_df.empty else 0
    today_bot = len(today_df[today_df['方向'] == '底']) if not today_df.empty else 0
    today_strong = len(today_df[today_df['強度'] == '強']) if not today_df.empty else 0
    
    # 今日 vs 昨日
    diff_total = today_count - yesterday_count
    
    # ===== 強度分佈（今日）=====
    strength_counts = {'強': 0, '中': 0, '弱': 0}
    if not today_df.empty and '強度' in today_df.columns:
        for s in strength_counts:
            strength_counts[s] = int((today_df['強度'] == s).sum())
    
    # ===== 歷史趨勢（最近 30 日）=====
    trend_dates = []
    trend_top = []
    trend_bot = []
    if not recent.empty and '日期' in recent.columns:
        grouped = recent.groupby(recent['日期'].dt.strftime('%Y-%m-%d'))
        for date, group in grouped:
            trend_dates.append(date)
            trend_top.append(int((group['方向'] == '頂').sum()))
            trend_bot.append(int((group['方向'] == '底').sum()))
        # 排序
        combined = sorted(zip(trend_dates, trend_top, trend_bot))
        trend_dates = [c[0] for c in combined]
        trend_top = [c[1] for c in combined]
        trend_bot = [c[2] for c in combined]
    
    # ===== Top 5 標的 =====
    top_tickers = []
    if not recent.empty and '標的' in recent.columns:
        counts = recent['標的'].value_counts().head(5)
        max_count = counts.max() if len(counts) > 0 else 1
        for t, c in counts.items():
            top_tickers.append({'ticker': t, 'count': int(c), 'pct': int(c / max_count * 100)})
    
    # ===== 多週期共振 =====
    resonance = {}
    for _, row in recent.iterrows():
        if pd.isna(row.get('日期')):
            continue
        key = (row['標的'], row['方向'])
        resonance.setdefault(key, set()).add(row['週期'])
    
    resonance_list = []
    for (ticker, dir_), levels in resonance.items():
        if len(levels) >= 2:
            name = ''
            # 試搵中文名
            if '中文名' in recent.columns:
                m = recent[recent['標的'] == ticker]
                if not m.empty:
                    name = m.iloc[0]['中文名']
            lvl_str = '+'.join(sorted(levels, key=lambda x: {'M': 1, 'W': 2, 'D': 3, '4H': 4}.get(x, 99)))
            stars = '⭐' * len(levels)
            resonance_list.append({'ticker': ticker, 'name': name, 'dir': dir_, 'levels': lvl_str, 'count': len(levels), 'stars': stars})
    resonance_list = sorted(resonance_list, key=lambda x: -x['count'])
    
    # ===== 表格 rows =====
    IND_NAME_MAP = {'DIF': 'MACD-DIF', 'J': 'KDJ-J'}
    def rename_indicator(ind):
        return IND_NAME_MAP.get(ind, ind)
    
    DISPLAY_COLS = ['日期_str', '標的', '中文名', '週期', '方向', '指標',
                    '前高/低', '現價', '價變化%', '指標變化%', '強度',
                    'lookback', 'tag']
    
    HEADER_LABELS = {
        '日期_str': '日期', '標的': '標的', '中文名': '中文名', '週期': '週期',
        '方向': '方向', '指標': '指標', '前高/低': '前高/低', '現價': '現價',
        '價變化%': '價變化%', '指標變化%': '指標變化%', '強度': '強度',
        'lookback': '長/短', 'tag': '型態'
    }
    
    # 強度轉百分比
    STRENGTH_PCT = {'強': 90, '中': 60, '弱': 30}
    
    def df_to_rows(d):
        if d.empty:
            return f"<tr><td colspan='{len(DISPLAY_COLS)}' style='text-align:center;color:#888;padding:20px;'>暫無數據</td></tr>"
        d = d[[c for c in DISPLAY_COLS if c in d.columns]]
        rows = []
        for _, row in d.iterrows():
            direction = row.get('方向', '')
            strength = row.get('強度', '')
            pct = STRENGTH_PCT.get(strength, 30)
            
            if direction == '頂':
                row_class = 'top-row'
                dir_html = '🔴 頂 ▼'
            elif direction == '底':
                row_class = 'bot-row'
                dir_html = '🟢 底 ▲'
            else:
                row_class = ''
                dir_html = direction
            
            cells = []
            for col in d.columns:
                val = row[col]
                if col == '方向':
                    val = dir_html
                elif col == '強度':
                    val = f'<div class="strength-bar"><div class="strength-fill strength-{val}" style="width:{pct}%;"></div><span class="strength-text">{val}</span></div>'
                elif col == '指標':
                    val = rename_indicator(val)
                elif col == 'lookback':
                    val = '長' if val == 'long' else '短'
                cells.append(f"<td>{val}</td>")
            
            # 將 row 轉成 data attribute（for modal）
            row_json = {
                'ticker': str(row.get('標的', '')),
                'name': str(row.get('中文名', '')),
                'date': str(row.get('日期_str', '')),
                'level': str(row.get('週期', '')),
                'direction': str(direction),
                'ind': rename_indicator(str(row.get('指標', ''))),
                'prev_price': str(row.get('前高/低', '')),
                'current_price': str(row.get('現價', '')),
                'price_change': str(row.get('價變化%', '')),
                'ind_change': str(row.get('指標變化%', '')),
                'strength': str(strength),
                'lookback': '長' if str(row.get('lookback', '')) == 'long' else '短',
                'tag': str(row.get('tag', ''))
            }
            import json
            row_json_str = json.dumps(row_json, ensure_ascii=False).replace("'", "&#39;")
            
            rows.append(f'<tr class="{row_class}" data-direction="{direction}" data-strength="{strength}" data-ticker="{row.get("標的","")}" data-json=\'{row_json_str}\' onclick="showDetail(this)">')
            rows.append("".join(cells))
            rows.append("</tr>")
        return "".join(rows)
    
    header_html = "".join(f"<th>{HEADER_LABELS.get(c, c)}</th>" for c in DISPLAY_COLS)
    
    # 共振 HTML
    resonance_html = ""
    if resonance_list:
        for r in resonance_list[:10]:
            resonance_html += f'<div class="resonance-item">{r["stars"]} {r["name"]} ({r["ticker"]}) | {r["levels"]} {r["dir"]}背離</div>'
    else:
        resonance_html = '<p style="color:#888;">暫無共振訊號</p>'
    
    # Top 5 HTML
    top_tickers_html = ""
    for t in top_tickers:
        top_tickers_html += f'''
        <div class="bar-row">
          <span class="bar-label">{t['ticker']}</span>
          <div class="bar-track"><div class="bar-fill" style="width:{t['pct']}%;"></div></div>
          <span class="bar-count">{t['count']}</span>
        </div>'''
    
    # Trend chart data
    import json
    trend_data_json = json.dumps({
        'dates': trend_dates,
        'top': trend_top,
        'bot': trend_bot
    }, ensure_ascii=False)
    
    # Strength donut data
    strength_data_json = json.dumps({
        'strong': strength_counts['強'],
        'medium': strength_counts['中'],
        'weak': strength_counts['弱']
    }, ensure_ascii=False)
    
    # NQ Key Levels
    nq_data_json = json.dumps({
        'high': 31616.5,
        'low': 30760.2,
        'current': 31397.8
    }, ensure_ascii=False)
    
    html = f"""<!DOCTYPE html>
<html lang="zh-HK" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>⚡ 0DTE Radar Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; }}
  :root {{
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #c9d1d9; --muted: #8b949e; --accent: #58a6ff;
    --top-bg: rgba(248, 81, 73, 0.08); --top-hover: rgba(248, 81, 73, 0.15);
    --bot-bg: rgba(63, 185, 80, 0.08); --bot-hover: rgba(63, 185, 80, 0.15);
    --top-color: #f85149; --bot-color: #3fb950;
  }}
  [data-theme="light"] {{
    --bg: #f6f8fa; --card: #ffffff; --border: #d0d7de;
    --text: #1f2328; --muted: #656d76; --accent: #0969da;
    --top-bg: rgba(207, 34, 46, 0.08); --top-hover: rgba(207, 34, 46, 0.15);
    --bot-bg: rgba(26, 127, 55, 0.08); --bot-hover: rgba(26, 127, 55, 0.15);
    --top-color: #cf222e; --bot-color: #1a7f37;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text);
    margin: 0; padding: 20px; transition: all 0.3s;
  }}
  .container {{ max-width: 1400px; margin: 0 auto; }}
  h1 {{ color: var(--accent); border-bottom: 2px solid var(--border); padding-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }}
  h2 {{ color: var(--accent); margin-top: 30px; border-left: 4px solid var(--accent); padding-left: 10px; }}
  .card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    padding: 15px; margin: 10px 0; transition: all 0.3s;
  }}
  .card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 15px; margin: 15px 0; }}
  .stat-box {{
    background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    padding: 15px; text-align: center; transition: all 0.2s;
  }}
  .stat-box:hover {{ border-color: var(--accent); }}
  .stat-box .num {{ font-size: 28px; font-weight: bold; color: var(--accent); }}
  .stat-box .label {{ font-size: 12px; color: var(--muted); margin-top: 5px; }}
  .stat-box.top .num {{ color: var(--top-color); }}
  .stat-box.bot .num {{ color: var(--bot-color); }}
  .delta {{ font-size: 12px; margin-left: 5px; }}
  .delta.up {{ color: var(--top-color); }}
  .delta.down {{ color: var(--bot-color); }}
  
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }}
  @media (max-width: 768px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
  
  .chart-container {{ position: relative; height: 250px; }}
  .donut-container {{ position: relative; height: 200px; }}
  
  .badge {{
    display: inline-block; padding: 4px 10px; margin: 3px;
    background: var(--bg); border-radius: 12px; font-size: 13px;
    border: 1px solid var(--border);
  }}
  table.table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }}
  table.table th {{
    background: linear-gradient(180deg, var(--card) 0%, var(--bg) 100%);
    color: var(--accent); padding: 10px; text-align: left;
    border-bottom: 2px solid var(--border); position: sticky; top: 0; z-index: 10;
    white-space: nowrap;
  }}
  table.table td {{ padding: 8px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }}
  table.table tr {{ transition: background 0.2s; cursor: pointer; }}
  
  tr.top-row {{ background: var(--top-bg); }}
  tr.top-row:hover {{ background: var(--top-hover); }}
  tr.bot-row {{ background: var(--bot-bg); }}
  tr.bot-row:hover {{ background: var(--bot-hover); }}
  
  .strength-bar {{
    position: relative; width: 60px; height: 18px; background: var(--bg);
    border-radius: 9px; overflow: hidden; display: inline-block;
  }}
  .strength-fill {{ position: absolute; left: 0; top: 0; bottom: 0; }}
  .strength-fill.strength-強 {{ background: #f85149; }}
  .strength-fill.strength-中 {{ background: #d29922; }}
  .strength-fill.strength-弱 {{ background: #6e7681; }}
  .strength-text {{
    position: relative; z-index: 1; font-size: 11px; font-weight: bold;
    color: white; line-height: 18px; padding-left: 6px;
  }}
  
  .controls {{
    display: flex; gap: 10px; flex-wrap: wrap; margin: 15px 0;
    padding: 15px; background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    align-items: center;
  }}
  .btn {{
    padding: 8px 14px; border: 1px solid var(--border); background: var(--bg);
    color: var(--text); border-radius: 6px; cursor: pointer;
    font-size: 13px; transition: all 0.2s;
  }}
  .btn:hover {{ background: var(--border); }}
  .btn.active {{ background: var(--accent); color: white; border-color: var(--accent); }}
  .search-input {{
    padding: 8px 14px; border: 1px solid var(--border); background: var(--bg);
    color: var(--text); border-radius: 6px; font-size: 13px; min-width: 200px;
  }}
  .search-input:focus {{ outline: none; border-color: var(--accent); }}
  .label-text {{ color: var(--muted); font-size: 13px; }}
  
  .bar-row {{ display: flex; align-items: center; gap: 10px; margin: 8px 0; }}
  .bar-label {{ width: 80px; font-size: 13px; font-weight: bold; }}
  .bar-track {{ flex: 1; height: 20px; background: var(--bg); border-radius: 10px; overflow: hidden; }}
  .bar-fill {{ height: 100%; background: linear-gradient(90deg, var(--accent) 0%, #1f6feb 100%); border-radius: 10px; }}
  .bar-count {{ width: 40px; text-align: right; font-size: 13px; color: var(--muted); }}
  
  .resonance-item {{ padding: 8px 0; font-size: 14px; border-bottom: 1px solid var(--border); }}
  .resonance-item:last-child {{ border-bottom: none; }}
  
  .keylevel {{ margin: 15px 0; }}
  .keylevel-bar {{
    position: relative; height: 30px; background: linear-gradient(90deg, var(--bot-color) 0%, var(--bg) 50%, var(--top-color) 100%);
    border-radius: 15px; overflow: visible;
  }}
  .keylevel-marker {{
    position: absolute; top: -5px; width: 4px; height: 40px;
    background: white; border-radius: 2px; box-shadow: 0 0 8px rgba(255,255,255,0.8);
  }}
  .keylevel-labels {{ display: flex; justify-content: space-between; margin-top: 8px; font-size: 12px; color: var(--muted); }}
  
  .modal {{
    display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.7); z-index: 1000;
    justify-content: center; align-items: center; padding: 20px;
  }}
  .modal.active {{ display: flex; }}
  .modal-content {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    max-width: 500px; width: 100%; padding: 25px; position: relative;
    max-height: 80vh; overflow-y: auto;
  }}
  .modal-close {{
    position: absolute; top: 15px; right: 15px; cursor: pointer;
    background: var(--bg); border: 1px solid var(--border); color: var(--text);
    width: 30px; height: 30px; border-radius: 50%; font-size: 16px;
  }}
  .modal-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border); }}
  .modal-row:last-child {{ border-bottom: none; }}
  .modal-label {{ color: var(--muted); }}
  .modal-value {{ font-weight: bold; }}
  
  .footer {{
    margin-top: 40px; text-align: center; color: var(--muted);
    font-size: 12px; border-top: 1px solid var(--border); padding-top: 20px;
  }}
  .scroll {{ overflow-x: auto; max-height: 700px; overflow-y: auto; }}
  
  /* 手機優化 */
  @media (max-width: 768px) {{
    body {{ padding: 10px; }}
    h1 {{ font-size: 20px; }}
    h2 {{ font-size: 16px; }}
    .stat-box .num {{ font-size: 22px; }}
    .controls {{ flex-direction: column; align-items: stretch; }}
    .search-input {{ min-width: auto; width: 100%; }}
    table.table {{ font-size: 12px; }}
    table.table th, table.table td {{ padding: 6px 8px; }}
  }}
</style>
</head>
<body>
<div class="container">

<h1>
  <span>⚡ 0DTE Radar Dashboard</span>
  <button class="btn" onclick="toggleTheme()" id="theme-btn">🌙</button>
</h1>
<p style="color:var(--muted);">最後更新：{now_hkt} HKT</p>

<!-- 統計數字 -->
<div class="stats">
  <div class="stat-box">
    <div class="num">{total_signals}</div>
    <div class="label">總訊號數</div>
  </div>
  <div class="stat-box">
    <div class="num">{today_count}</div>
    <div class="label">今日訊號</div>
  </div>
  <div class="stat-box top">
    <div class="num">{today_top}</div>
    <div class="label">🔴 頂背離</div>
  </div>
  <div class="stat-box bot">
    <div class="num">{today_bot}</div>
    <div class="label">🟢 底背離</div>
  </div>
  <div class="stat-box">
    <div class="num">{today_strong}</div>
    <div class="label">🔥 強訊號</div>
  </div>
</div>

<!-- 今日 vs 昨日 -->
<div class="card">
  <strong>📈 今日 vs 昨日：</strong>
  總訊號 {today_count} 
  <span class="delta {'up' if diff_total > 0 else 'down' if diff_total < 0 else ''}">
    ({diff_total:+d})
  </span>
  | 昨日 {yesterday_count}
</div>

<!-- 圖表區 -->
<div class="grid-2">
  <div class="card">
    <h2 style="margin-top:0;">📊 歷史趨勢（30 日）</h2>
    <div class="chart-container"><canvas id="trendChart"></canvas></div>
  </div>
  <div class="card">
    <h2 style="margin-top:0;">📊 強度分佈（今日）</h2>
    <div class="donut-container"><canvas id="donutChart"></canvas></div>
  </div>
</div>

<!-- Top 5 -->
<div class="card">
  <h2 style="margin-top:0;">📈 Top 5 標的（30 日）</h2>
  {top_tickers_html if top_tickers_html else '<p style="color:var(--muted);">暫無數據</p>'}
</div>

<!-- 共振 -->
<div class="card">
  <h2 style="margin-top:0;">⭐ 多週期共振</h2>
  {resonance_html}
</div>

<!-- NQ Key Levels -->
<div class="card">
  <h2 style="margin-top:0;">📍 NQ 關鍵位</h2>
  <div class="keylevel">
    <div class="keylevel-bar" id="nq-bar"></div>
    <div class="keylevel-labels">
      <span>5日低 30,760</span>
      <span>現價 31,398</span>
      <span>5日高 31,616</span>
    </div>
  </div>
</div>

<!-- 今日訊號 -->
<h2>🔥 今日訊號</h2>

<div class="controls">
  <span class="label-text">篩選：</span>
  <button class="btn active" data-filter="all" onclick="filterRows('all', this)">全部</button>
  <button class="btn" data-filter="top" onclick="filterRows('top', this)">🔴 頂</button>
  <button class="btn" data-filter="bot" onclick="filterRows('bot', this)">🟢 底</button>
  <button class="btn" data-filter="strong" onclick="filterRows('strong', this)">🔥 強</button>
  
  <span class="label-text" style="margin-left:20px;">排序：</span>
  <button class="btn" onclick="sortBy('strength', this)">按強度</button>
  <button class="btn" onclick="sortBy('ticker', this)">按標的</button>
  
  <input type="text" class="search-input" placeholder="🔎 搜尋（可逗號分隔）..." oninput="searchRows(this.value)">
  
  <button class="btn" onclick="exportCSV()" style="margin-left:auto;">📥 匯出 CSV</button>
</div>

<div class="card scroll">
  <table class="table" id="today-table">
    <thead><tr>{header_html}</tr></thead>
    <tbody>{df_to_rows(today_df)}</tbody>
  </table>
</div>

<div class="footer">
  ⚡ Radar V18.3 | Powered by GitHub Actions + GitHub Pages
</div>

</div>

<!-- Modal -->
<div class="modal" id="modal" onclick="if(event.target===this) closeModal()">
  <div class="modal-content">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <h2 id="modal-title" style="margin-top:0;"></h2>
    <div id="modal-body"></div>
  </div>
</div>

<script>
// ===== 主題切換 =====
function toggleTheme() {{
  const html = document.documentElement;
  const current = html.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  document.getElementById('theme-btn').textContent = next === 'dark' ? '🌙' : '☀️';
  localStorage.setItem('theme', next);
}}
(function() {{
  const saved = localStorage.getItem('theme');
  if (saved) {{
    document.documentElement.setAttribute('data-theme', saved);
    document.getElementById('theme-btn').textContent = saved === 'dark' ? '🌙' : '☀️';
  }}
}})();

// ===== 篩選 =====
let currentFilter = 'all';

function filterRows(type, btn) {{
  document.querySelectorAll('.controls .btn[data-filter]').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  currentFilter = type;
  applyFilters();
}}

function searchRows(query) {{
  applyFilters(query);
}}

function applyFilters(query = '') {{
  const rows = document.querySelectorAll('#today-table tbody tr');
  const queries = query.toLowerCase().split(',').map(q => q.trim()).filter(q => q);
  
  rows.forEach(row => {{
    if (!row.dataset.direction) return;
    const direction = row.dataset.direction;
    const strength = row.dataset.strength;
    const ticker = (row.dataset.ticker || '').toLowerCase();
    
    let show = true;
    if (currentFilter === 'top' && direction !== '頂') show = false;
    if (currentFilter === 'bot' && direction !== '底') show = false;
    if (currentFilter === 'strong' && strength !== '強') show = false;
    
    if (queries.length > 0) {{
      let matched = false;
      for (const q of queries) {{
        if (ticker.includes(q)) {{ matched = true; break; }}
      }}
      if (!matched) show = false;
    }}
    
    row.style.display = show ? '' : 'none';
  }});
}}

function sortBy(key, btn) {{
  const tbody = document.querySelector('#today-table tbody');
  const rows = Array.from(tbody.querySelectorAll('tr[data-direction]'));
  const strengthOrder = {{'強': 1, '中': 2, '弱': 3}};
  
  rows.sort((a, b) => {{
    if (key === 'strength') {{
      return (strengthOrder[a.dataset.strength] || 9) - (strengthOrder[b.dataset.strength] || 9);
    }} else if (key === 'ticker') {{
      return (a.dataset.ticker || '').localeCompare(b.dataset.ticker || '');
    }}
    return 0;
  }});
  
  rows.forEach(r => tbody.appendChild(r));
  document.querySelectorAll('.controls .btn:not([data-filter])').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
}}

// ===== Modal =====
function showDetail(row) {{
  try {{
    const data = JSON.parse(row.dataset.json.replace(/&#39;/g, "'"));
    document.getElementById('modal-title').textContent = `${{data.name}} (${{data.ticker}})`;
    const body = document.getElementById('modal-body');
    
    const dirIcon = data.direction === '頂' ? '🔴 頂背離' : '🟢 底背離';
    const rows = [
      ['日期', data.date],
      ['週期', data.level],
      ['方向', dirIcon],
      ['指標', data.ind],
      ['型態', data.tag],
      ['長/短', data.lookback],
      ['前高/低', data.prev_price],
      ['現價', data.current_price],
      ['價變化', data.price_change + '%'],
      ['指標變化', data.ind_change + '%'],
      ['強度', data.strength],
    ];
    
    body.innerHTML = rows.map(([k, v]) => 
      `<div class="modal-row"><span class="modal-label">${{k}}</span><span class="modal-value">${{v}}</span></div>`
    ).join('');
    
    document.getElementById('modal').classList.add('active');
  }} catch(e) {{
    console.error(e);
  }}
}}

function closeModal() {{
  document.getElementById('modal').classList.remove('active');
}}

// ===== 匯出 CSV =====
function exportCSV() {{
  const rows = document.querySelectorAll('#today-table tbody tr[data-direction]');
  const visibleRows = Array.from(rows).filter(r => r.style.display !== 'none');
  
  let csv = '日期,標的,中文名,週期,方向,指標,前高/低,現價,價變化%,指標變化%,強度,長/短,型態\\n';
  visibleRows.forEach(r => {{
    const cells = Array.from(r.querySelectorAll('td')).map(td => {{
      let text = td.innerText.trim();
      if (text.includes(',')) text = `"${{text}}"`;
      return text;
    }});
    csv += cells.join(',') + '\\n';
  }});
  
  const blob = new Blob(['\\ufeff' + csv], {{ type: 'text/csv;charset=utf-8;' }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `radar_${{new Date().toISOString().slice(0,10)}}.csv`;
  a.click();
}}

// ===== 圖表 =====
const trendData = {trend_data_json};
const strengthData = {strength_data_json};
const nqData = {nq_data_json};

const isDark = () => document.documentElement.getAttribute('data-theme') === 'dark';
const chartTextColor = () => isDark() ? '#c9d1d9' : '#1f2328';
const chartGridColor = () => isDark() ? '#30363d' : '#d0d7de';

// 趨勢圖
const trendCtx = document.getElementById('trendChart');
if (trendCtx && trendData.dates.length > 0) {{
  new Chart(trendCtx, {{
    type: 'line',
    data: {{
      labels: trendData.dates.map(d => d.slice(5)),
      datasets: [
        {{
          label: '頂背離',
          data: trendData.top,
          borderColor: '#f85149',
          backgroundColor: 'rgba(248, 81, 73, 0.1)',
          tension: 0.3, fill: true,
        }},
        {{
          label: '底背離',
          data: trendData.bot,
          borderColor: '#3fb950',
          backgroundColor: 'rgba(63, 185, 80, 0.1)',
          tension: 0.3, fill: true,
        }}
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ labels: {{ color: chartTextColor() }} }} }},
      scales: {{
        x: {{ ticks: {{ color: chartTextColor() }}, grid: {{ color: chartGridColor() }} }},
        y: {{ ticks: {{ color: chartTextColor() }}, grid: {{ color: chartGridColor() }}, beginAtZero: true }}
      }}
    }}
  }});
}}

// 甜甜圈圖
const donutCtx = document.getElementById('donutChart');
if (donutCtx) {{
  new Chart(donutCtx, {{
    type: 'doughnut',
    data: {{
      labels: ['強', '中', '弱'],
      datasets: [{{
        data: [strengthData.strong, strengthData.medium, strengthData.weak],
        backgroundColor: ['#f85149', '#d29922', '#6e7681'],
        borderWidth: 2,
        borderColor: chartGridColor(),
      }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ position: 'bottom', labels: {{ color: chartTextColor() }} }} }}
    }}
  }});
}}

// NQ Key Level
const nqBar = document.getElementById('nq-bar');
if (nqBar) {{
  const range = nqData.high - nqData.low;
  const pct = ((nqData.current - nqData.low) / range) * 100;
  const marker = document.createElement('div');
  marker.className = 'keylevel-marker';
  marker.style.left = pct + '%';
  nqBar.appendChild(marker);
}}
</script>

</body>
</html>"""
    
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ 生成 index.html ({len(html)} 字元)")

if __name__ == '__main__':
    build_html()
