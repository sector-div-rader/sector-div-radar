# Sector Div Radar

港股/美股板塊資金流分析與回測工具。項目會抓取盤中資金流數據、生成 dashboard 數據，並提供回測結果。

## 功能
- 盤中資金流抓取：`scripts/intraday_flow.py`
- 回測：`backtest.py`
- 生成靜態站點：`build_site.py`
- 自動更新數據：GitHub Actions（`.github/workflows/flow.yml`）

## 快速開始
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/intraday_flow.py
python backtest.py
python build_site.py
