# main.py - NQ / QQQ 0DTE 全宏觀晨報 V21.0
# ============================================
# V21.0 核心升級：
#   1. 新增 QQQ 0DTE 綜合多空評分卡（按權重與宏觀相關性加權）
#   2. 新增 QQQ 現貨關鍵位（Pivot / R1 / S1）+ VIX 隱含預期波幅 + 14D ATR
#   3. 打通 data/flow/intraday.json 長橋資金流，自動標記「資金共振 / 逆流預警」
#   4. 優先讀取 backtest_results.json 動態勝率 + 實裝 50% 勝率過濾器
#   5. 宏觀反向指標（^TNX / DX-Y.NYB / ^VIX）自動翻譯對 QQQ 多空影響 + EMA50 順逆勢標記
#   6. M/W 大週期自動標記 [新觸發] / [持續中] 避免重複洗版
#   7. 修正 FMP 財經日曆 HKT 時區、06:00 HKT Pivot 日期基準、數據快取加速及手機版 HTML Email
# ============================================

import os
import math
import json
import smtplib
import traceback
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from scipy.signal import find_peaks

os.makedirs("/tmp/yf_cache", exist_ok=True)
yf.set_tz_cache_location("/tmp/yf_cache")

EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': os.environ.get('EMAIL_USER'),
    'sender_password': os.environ.get('EMAIL_PASS'),
    'receiver_email': os.environ.get('EMAIL_TO', os.environ.get('EMAIL_USER'))
}

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
FMP_API_KEY = os.environ.get('FMP_API_KEY')

MIN_WIN_RATE = 0.50       # 低於 50% 勝率的雜訊訊號自動過濾
MIN_BACKTEST_SAMPLES = 5  # 回測樣本至少 5 次才採用動態勝率

# 反向宏觀指標（底背離反彈 = 利空 QQQ；頂背離回落 = 利好 QQQ）
MACRO_INVERSE_TICKERS = {'^TNX', 'DX-Y.NYB', '^VIX'}

ALL_TARGETS = {
    'NQ=F':     {'name': '納斯達克100期貨', 'sticker': '📱', 'weight': 5, 'category': 'TECH',      'qqq_beta': 2.0,  'flow_etf': 'QQQ'},
    'QQQ':      {'name': '納指100ETF',     'sticker': '🎯', 'weight': 5, 'category': 'TECH',      'qqq_beta': 2.0,  'flow_etf': 'QQQ'},
    'ES=F':     {'name': '標普500期貨',    'sticker': '📈', 'weight': 4, 'category': 'INDEX',     'qqq_beta': 1.2,  'flow_etf': None},
    'YM=F':     {'name': '道瓊斯工業期貨', 'sticker': '🏛️', 'weight': 4, 'category': 'INDEX',     'qqq_beta': 0.8,  'flow_etf': None},
    '^VIX':     {'name': '恐慌指數',       'sticker': '😱', 'weight': 3, 'category': 'INDEX',     'qqq_beta': -1.5, 'flow_etf': None},
    'GC=F':     {'name': '黃金期貨',       'sticker': '🥇', 'weight': 3, 'category': 'MACRO',     'qqq_beta': 0.0,  'flow_etf': None},
    'CL=F':     {'name': '原油期貨',       'sticker': '🛢️', 'weight': 3, 'category': 'MACRO',     'qqq_beta': -0.3, 'flow_etf': 'XLE'},
    'DX-Y.NYB': {'name': '美元指數',       'sticker': '💵', 'weight': 3, 'category': 'MACRO',     'qqq_beta': -1.5, 'flow_etf': None},
    '^TNX':     {'name': '美債10年收益率', 'sticker': '📊', 'weight': 3, 'category': 'MACRO',     'qqq_beta': -1.8, 'flow_etf': None},
    'SMH':      {'name': '半導體ETF',      'sticker': '💾', 'weight': 4, 'category': 'TECH',      'qqq_beta': 1.8,  'flow_etf': 'XLK'},
    'IGV':      {'name': '軟件服務ETF',    'sticker': '💿', 'weight': 3, 'category': 'TECH',      'qqq_beta': 1.5,  'flow_etf': 'XLK'},
    'XLC':      {'name': '通訊服務ETF',    'sticker': '📡', 'weight': 3, 'category': 'TECH',      'qqq_beta': 1.4,  'flow_etf': 'XLC'},
    'XLY':      {'name': '非必需消費ETF',  'sticker': '🛍️', 'weight': 3, 'category': 'CYCLICAL',  'qqq_beta': 1.2,  'flow_etf': 'XLY'},
    'XLF':      {'name': '金融板塊ETF',    'sticker': '🏦', 'weight': 3, 'category': 'CYCLICAL',  'qqq_beta': 0.7,  'flow_etf': 'XLF'},
    'XLE':      {'name': '能源板塊ETF',    'sticker': '⚡', 'weight': 3, 'category': 'CYCLICAL',  'qqq_beta': 0.2,  'flow_etf': 'XLE'},
    'XLI':      {'name': '工業板塊ETF',    'sticker': '⚙️', 'weight': 3, 'category': 'CYCLICAL',  'qqq_beta': 0.6,  'flow_etf': 'XLI'},
    'XLV':      {'name': '醫療保健ETF',    'sticker': '🏥', 'weight': 2, 'category': 'DEFENSIVE', 'qqq_beta': -0.5, 'flow_etf': 'XLV'},
    'XLP':      {'name': '必需消費ETF',    'sticker': '🛒', 'weight': 2, 'category': 'DEFENSIVE', 'qqq_beta': -0.6, 'flow_etf': 'XLP'},
    'XLU':      {'name': '公用事業ETF',    'sticker': '💡', 'weight': 2, 'category': 'DEFENSIVE', 'qqq_beta': -0.7, 'flow_etf': 'XLU'},
}

# ==================== 預設歷史勝率（作後備，優先讀 backtest_results.json）====================

DEFAULT_WIN_RATE = {
    ('^VIX', '4H', '底'): 0.778, ('DX-Y.NYB', 'M', '底'): 0.765, ('XLU', 'W', '底'): 0.718,
    ('^VIX', 'W', '底'): 0.691, ('XLV', 'W', '底'): 0.690, ('XLI', 'W', '底'): 0.654,
    ('XLP', 'W', '底'): 0.652, ('XLP', '4H', '底'): 0.619, ('IGV', 'D', '底'): 0.612,
    ('XLU', 'D', '底'): 0.609, ('GC=F', '4H', '底'): 0.608, ('XLP', 'D', '底'): 0.596,
    ('GC=F', 'D', '底'): 0.585, ('XLI', 'D', '底'): 0.579, ('DX-Y.NYB', '4H', '底'): 0.578,
    ('XLF', 'D', '底'): 0.577, ('CL=F', 'W', '底'): 0.576, ('XLE', 'D', '底'): 0.573,
    ('DX-Y.NYB', 'W', '底'): 0.569, ('GC=F', 'W', '底'): 0.568, ('SMH', 'D', '底'): 0.567,
    ('^VIX', 'D', '底'): 0.565, ('XLV', 'D', '底'): 0.551, ('CL=F', 'D', '底'): 0.548,
    ('XLC', 'D', '底'): 0.535, ('XLY', 'D', '底'): 0.538, ('XLI', '4H', '底'): 0.485,
    ('XLU', '4H', '底'): 0.409, ('XLF', '4H', '底'): 0.167, ('XLE', 'W', '底'): 0.423,
    ('XLC', 'W', '底'): 0.333, ('SMH', 'W', '底'): 0.333, ('^TNX', 'D', '底'): 0.473,
    ('^TNX', 'W', '底'): 0.547, ('XLF', 'W', '底'): 0.450, ('IGV', 'W', '底'): 0.486,
    ('XLV', 'M', '底'): 1.000, ('XLI', 'M', '底'): 1.000, ('SMH', 'M', '底'): 1.000,
    ('XLE', 'M', '底'): 0.800, ('XLY', 'M', '底'): 0.800, ('CL=F', 'M', '底'): 0.750,
    ('XLP', 'M', '底'): 0.667, ('XLU', 'M', '底'): 0.667, ('GC=F', 'M', '底'): 0.667,
    ('DX-Y.NYB', 'D', '底'): 0.498, ('^TNX', 'M', '底'): 0.286,

    ('^VIX', '4H', '頂'): 0.786, ('^VIX', 'W', '頂'): 0.692, ('^VIX', 'D', '頂'): 0.600,
    ('^VIX', 'M', '頂'): 0.600, ('CL=F', 'M', '頂'): 0.625, ('XLE', 'M', '頂'): 0.765,
    ('XLE', '4H', '頂'): 0.647, ('XLE', 'W', '頂'): 0.472, ('XLC', '4H', '頂'): 0.857,
    ('XLY', '4H', '頂'): 1.000, ('XLI', '4H', '頂'): 1.000, ('XLP', '4H', '頂'): 1.000,
    ('XLU', '4H', '頂'): 1.000, ('XLF', '4H', '頂'): 0.600, ('XLF', 'W', '頂'): 0.478,
    ('GC=F', '4H', '頂'): 0.600, ('GC=F', 'M', '頂'): 0.379, ('GC=F', 'W', '頂'): 0.467,
    ('GC=F', 'D', '頂'): 0.421, ('XLP', 'M', '頂'): 0.500, ('XLP', 'W', '頂'): 0.352,
    ('XLP', 'D', '頂'): 0.459, ('XLU', 'M', '頂'): 0.360, ('XLU', 'W', '頂'): 0.360,
    ('XLU', 'D', '頂'): 0.457, ('XLI', 'M', '頂'): 0.407, ('XLI', 'W', '頂'): 0.395,
    ('XLI', 'D', '頂'): 0.426, ('XLV', 'M', '頂'): 0.481, ('XLV', 'W', '頂'): 0.380,
    ('XLV', 'D', '頂'): 0.459, ('XLF', 'M', '頂'): 0.381, ('XLF', 'D', '頂'): 0.469,
    ('XLY', 'M', '頂'): 0.360, ('XLY', 'W', '頂'): 0.455, ('XLY', 'D', '頂'): 0.446,
    ('XLC', 'M', '頂'): 0.158, ('XLC', 'W', '頂'): 0.267, ('XLC', 'D', '頂'): 0.440,
    ('SMH', 'M', '頂'): 0.323, ('SMH', 'W', '頂'): 0.374, ('SMH', 'D', '頂'): 0.378,
    ('SMH', '4H', '頂'): 0.462, ('IGV', 'M', '頂'): 0.074, ('IGV', 'W', '頂'): 0.323,
    ('IGV', 'D', '頂'): 0.378, ('IGV', '4H', '頂'): 0.231, ('DX-Y.NYB', 'M', '頂'): 0.462,
    ('DX-Y.NYB', 'W', '頂'): 0.453, ('DX-Y.NYB', 'D', '頂'): 0.474, ('DX-Y.NYB', '4H', '頂'): 0.301,
    ('^TNX', 'M', '頂'): 0.444, ('^TNX', 'W', '頂'): 0.411, ('^TNX', 'D', '頂'): 0.498,
    ('^TNX', '4H', '頂'): 0.462, ('CL=F', 'W', '頂'): 0.492, ('CL=F', 'D', '頂'): 0.404,
    ('CL=F', '4H', '頂'): 0.304,
}


def load_dynamic_win_rates():
    """優先載入 backtest_results.json 最新 T+5 勝率，樣本不足或無檔案時用預設表"""
    win_map = {k: (v, None) for k, v in DEFAULT_WIN_RATE.items()}
    if not os.path.exists('backtest_results.json'):
        return win_map

    try:
        with open('backtest_results.json', 'r', encoding='utf-8') as f:
            bt = json.load(f)
        updated = 0
        for ticker, levels in bt.items():
            for lv, dirs in levels.items():
                for direction in ['底', '頂']:
                    t5 = dirs.get(direction, {}).get('T+5')
                    if t5 and t5.get('count', 0) >= MIN_BACKTEST_SAMPLES:
                        win_map[(ticker, lv, direction)] = (
                            round(float(t5['winRate']) / 100.0, 4),
                            int(t5['count'])
                        )
                        updated += 1
        print(f"✅ 已從 backtest_results.json 載入 {updated} 組有效勝率", flush=True)
    except Exception as e:
        print(f"⚠️ 讀取 backtest_results.json 失敗，改用內建勝率: {e}", flush=True)

    return win_map


WIN_RATE_MAP = load_dynamic_win_rates()


def get_win_info(ticker, level, direction):
    """回傳 (win_rate, sample_count)"""
    return WIN_RATE_MAP.get((ticker, level, direction), (None, None))


def get_win_tag(win_rate, sample_count=None):
    if win_rate is None:
        return ''
    sample_note = f'({sample_count}次)' if sample_count is not None else ''
    if win_rate >= 0.65:
        return f' ⭐⭐⭐{sample_note}'
    elif win_rate >= 0.55:
        return f' ⭐⭐{sample_note}'
    else:
        return f' ⭐{sample_note}'


# ==================== 數據快取（大幅減少 Yahoo Finance 重複請求）====================

RAW_DF_CACHE = {}
LIVE_PRICE_CACHE = {}


def get_raw_df(t, lv):
    key = (t, lv)
    if key in RAW_DF_CACHE:
        return RAW_DF_CACHE[key].copy()

    itv, per, _ = INTERVAL_MAP[lv]
    raw = yf.Ticker(t).history(period=per, interval=itv)
    if lv == '4H' and not raw.empty:
        raw = raw.resample('4h').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min',
            'Close': 'last', 'Volume': 'sum'
        }).dropna()

    RAW_DF_CACHE[key] = raw
    return raw.copy()


def get_live_price(t):
    if t in LIVE_PRICE_CACHE:
        return LIVE_PRICE_CACHE[t]

    try:
        live = yf.Ticker(t).history(period='1d', interval='1m')
        price = float(live['Close'].iloc[-1]) if not live.empty else None
    except Exception:
        price = None

    LIVE_PRICE_CACHE[t] = price
    return price


# ==================== 長橋盤中資金流讀取 ====================

def load_longbridge_flow():
    """讀取 data/flow/intraday.json 並驗證時效性（僅採用 4 日內交易日數據）"""
    path = 'data/flow/intraday.json'
    if not os.path.exists(path):
        return None

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        trade_date_str = data.get('trade_date', '')
        if trade_date_str:
            td = datetime.strptime(trade_date_str, '%Y-%m-%d').date()
            today_hkt = datetime.now(timezone(timedelta(hours=8))).date()
            if (today_hkt - td).days > 4:
                return None

        flow_by_symbol = {}
        for item in data.get('qqq_core', []) + data.get('sectors', []):
            if item.get('status') == 'ok':
                flow_by_symbol[item['symbol']] = item

        return {
            'trade_date': trade_date_str,
            'qqq_core': data.get('qqq_core', []),
            'sectors': data.get('sectors', []),
            'by_symbol': flow_by_symbol,
        }
    except Exception as e:
        print(f"⚠️ 讀取長橋資金流失敗: {e}", flush=True)
        return None


def get_flow_resonance_tag(ticker, direction, lb_flow):
    """比對技術背離方向與長橋盤中真實資金流"""
    if not lb_flow:
        return ''
    flow_sym = ALL_TARGETS.get(ticker, {}).get('flow_etf')
    if not flow_sym:
        return ''
    item = lb_flow['by_symbol'].get(flow_sym)
    if not item:
        return ''

    net = float(item.get('main_net_inflow', 0))
    close_1h = float(item.get('net_inflow_close_1h', 0))
    thresh = 2.0e7 if flow_sym == 'QQQ' else 1.0e7

    if direction == '頂':
        if net <= -thresh or close_1h <= -thresh * 0.6:
            return f' [💰{flow_sym}資金流出共振]'
        elif net >= thresh * 1.5:
            return f' [⚠️{flow_sym}逆資金流慎防軋空]'
    elif direction == '底':
        if net >= thresh or close_1h >= thresh * 0.6:
            return f' [💰{flow_sym}資金流入共振]'
        elif net <= -thresh * 1.5:
            return f' [⚠️{flow_sym}資金仍在流出]'
    return ''


def fmt_money_short(v):
    abs_v = abs(v)
    sign = '+' if v >= 0 else '-'
    if abs_v >= 1e9:
        return f"{sign}${abs_v/1e9:.2f}B"
    if abs_v >= 1e6:
        return f"{sign}${abs_v/1e6:.1f}M"
    if abs_v >= 1e3:
        return f"{sign}${abs_v/1e3:.0f}K"
    return f"{sign}${abs_v:.0f}"


def build_longbridge_summary(lb_flow):
    if not lb_flow:
        return "💰 【長橋上日盤中資金流】：\n   (暫無最新有效資金流數據)"

    td = lb_flow.get('trade_date', '—')
    by_sym = lb_flow['by_symbol']
    lines = [f"💰 【長橋盤中資金流摘要 ({td})】："]

    qqq_item = by_sym.get('QQQ')
    if qqq_item:
        lines.append(
            f"   * QQQ 總流: {fmt_money_short(qqq_item['main_net_inflow'])} "
            f"(開盤 {fmt_money_short(qqq_item['net_inflow_open_1h'])} | 尾盤 {fmt_money_short(qqq_item['net_inflow_close_1h'])})"
        )

    mag7 = [by_sym[s] for s in ['NVDA', 'AAPL', 'MSFT', 'AMZN', 'META', 'GOOGL', 'TSLA'] if s in by_sym]
    if mag7:
        mag7_sorted = sorted(mag7, key=lambda x: x['main_net_inflow'], reverse=True)
        top_m = ", ".join(f"{x['symbol']}({fmt_money_short(x['main_net_inflow'])})" for x in mag7_sorted[:2])
        bot_m = ", ".join(f"{x['symbol']}({fmt_money_short(x['main_net_inflow'])})" for x in mag7_sorted[-2:])
        lines.append(f"   * 七巨頭吸金前二: {top_m}")
        lines.append(f"   * 七巨頭流出前二: {bot_m}")

    sectors = [s for s in lb_flow.get('sectors', []) if s.get('status') == 'ok']
    if sectors:
        sec_sorted = sorted(sectors, key=lambda x: x['main_net_inflow'], reverse=True)
        best_s = sec_sorted[0]
        worst_s = sec_sorted[-1]
        lines.append(
            f"   * 板塊最強/最弱: {best_s['name']}({best_s['symbol']} {fmt_money_short(best_s['main_net_inflow'])}) / "
            f"{worst_s['name']}({worst_s['symbol']} {fmt_money_short(worst_s['main_net_inflow'])})"
        )

    return "\n".join(lines)


# ==================== 運行模式與時間顯示 ====================

def is_dashboard_only():
    dispatch_mode = os.environ.get('DISPATCH_MODE', '').strip().lower()
    if dispatch_mode == 'dashboard':
        return True
    if dispatch_mode == 'full':
        return False

    schedule_cron = os.environ.get('EVENT_SCHEDULE', '').strip()
    if schedule_cron == '0 13 * * 1-5':
        return True
    if schedule_cron == '0 22 * * 1-5':
        return False

    now_hkt = datetime.now(timezone(timedelta(hours=8)))
    return 18 <= now_hkt.hour <= 23


def time_ago(dist, lv):
    if dist == 0:
        return '最新'
    if lv == 'M':
        return f'{dist} 個月前'
    if lv == 'W':
        return f'{dist} 週前'
    if lv == 'D':
        return f'{dist} 日前'
    if lv == '4H':
        hours = dist * 4
        if hours >= 24:
            return f'{hours // 24} 日前'
        return f'{hours} 小時前'
    return f'{dist} 根前'


def get_strength(ind_change_pct):
    abs_pct = abs(ind_change_pct)
    if abs_pct >= 50:
        return '強', '🔥🔥🔥'
    elif abs_pct >= 20:
        return '中', '🔥🔥'
    else:
        return '弱', '🔥'


# ==================== 指標計算 ====================

def calculate_custom_indicators(df):
    close = df['Close']
    high = df['High']
    low = df['Low']

    ema50   = close.ewm(span=50, adjust=False).mean()
    ema700  = close.ewm(span=700, adjust=False).mean() if len(df) >= 700 else pd.Series(index=df.index, dtype=float)
    ema800  = close.ewm(span=800, adjust=False).mean() if len(df) >= 800 else pd.Series(index=df.index, dtype=float)
    ema900  = close.ewm(span=900, adjust=False).mean() if len(df) >= 900 else pd.Series(index=df.index, dtype=float)
    ema1000 = close.ewm(span=1000, adjust=False).mean() if len(df) >= 1000 else pd.Series(index=df.index, dtype=float)
    ema3500 = close.ewm(span=3500, adjust=False).mean() if len(df) >= 3500 else pd.Series(index=df.index, dtype=float)

    ema5 = close.ewm(span=5, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema5 - ema26

    low9 = low.rolling(9).min()
    high9 = high.rolling(9).max()
    denom = (high9 - low9).replace(0, np.nan)
    rsv = ((close - low9) / denom * 100).fillna(50)
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d

    return pd.DataFrame({
        'Close': close, 'High': high, 'Low': low, 'DIF': dif, 'J': j,
        'EMA50': ema50, 'EMA700': ema700, 'EMA800': ema800,
        'EMA900': ema900, 'EMA1000': ema1000, 'EMA3500': ema3500
    })


def get_trend_context(last_close, last_ema50, direction):
    if pd.isna(last_ema50) or last_ema50 == 0:
        return ''
    above_ema50 = last_close >= last_ema50
    if direction == '頂':
        return '[⚠️逆勢摸頂]' if above_ema50 else '[✅順勢]'
    else:
        return '[✅順勢]' if above_ema50 else '[⚠️逆勢抄底]'


def get_qqq_impact_tag(ticker, direction):
    if ticker in MACRO_INVERSE_TICKERS:
        return '👉利空QQQ' if direction == '底' else '👉利好QQQ'
    return ''


# ==================== 舊邏輯：Pivot ====================

def scipy_pivots(series, prominence_pct=3.0, distance=2):
    if len(series) < 20:
        return [], []
    prominence = series.mean() * prominence_pct / 100
    highs, _ = find_peaks(series.values, prominence=prominence, distance=distance)
    lows, _ = find_peaks(-series.values, prominence=prominence, distance=distance)
    return list(highs), list(lows)


def check_pivot_divergence(p_s, i_s, highs, lows, last_idx, recent_window):
    top_div = None
    bot_div = None

    recent_highs = [h for h in highs if last_idx - h <= recent_window]
    if recent_highs:
        h2 = recent_highs[-1]
        prev_highs = [h for h in highs if h < h2]
        if prev_highs:
            h1 = max(prev_highs, key=lambda x: p_s.iloc[x])
            if p_s.iloc[h2] > p_s.iloc[h1] and i_s.iloc[h2] < i_s.iloc[h1]:
                top_div = {'dist': last_idx - h2}

    recent_lows = [l for l in lows if last_idx - l <= recent_window]
    if recent_lows:
        l2 = recent_lows[-1]
        prev_lows = [l for l in lows if l < l2]
        if prev_lows:
            l1 = min(prev_lows, key=lambda x: p_s.iloc[x])
            if p_s.iloc[l2] < p_s.iloc[l1] and i_s.iloc[l2] > i_s.iloc[l1]:
                bot_div = {'dist': last_idx - l2}

    if top_div and bot_div:
        return ('頂', top_div['dist']) if top_div['dist'] <= bot_div['dist'] else ('底', bot_div['dist'])
    if top_div:
        return ('頂', top_div['dist'])
    if bot_div:
        return ('底', bot_div['dist'])
    return None


# ==================== 新邏輯：雙重 Lookback ====================

def check_dual_lookback(price, indicator, short_lb=5, long_lb=20,
                        price_tol=0.005, ind_drop_min=0.05):
    if len(price) < long_lb + 2:
        return {'long': [], 'short': []}

    last_idx = len(price) - 1
    p_now = float(price.iloc[last_idx])
    i_now = float(indicator.iloc[last_idx])

    result = {'long': [], 'short': []}

    for label, lb in [('long', long_lb), ('short', short_lb)]:
        if last_idx - lb < 0:
            continue

        recent_price = price.iloc[last_idx - lb:last_idx]
        recent_ind = indicator.iloc[last_idx - lb:last_idx]
        if len(recent_price) == 0:
            continue

        prev_high_pos = int(np.argmax(recent_price.values))
        dist_high = lb - prev_high_pos
        prev_high_price = float(recent_price.iloc[prev_high_pos])
        prev_high_ind = float(recent_ind.iloc[prev_high_pos])

        if dist_high >= 2 and prev_high_price != 0 and prev_high_ind != 0:
            price_close = p_now >= prev_high_price * (1 - price_tol)
            ind_change = (i_now - prev_high_ind) / abs(prev_high_ind)

            if price_close and ind_change <= -ind_drop_min:
                is_new_high = p_now > prev_high_price
                result[label].append({
                    'type': '頂',
                    'tag': '新高' if is_new_high else '雙頂',
                    'current_price': p_now,
                    'prev_price': prev_high_price,
                    'current_ind': i_now,
                    'prev_ind': prev_high_ind,
                    'dist': dist_high,
                    'price_diff_pct': (p_now - prev_high_price) / prev_high_price * 100,
                    'ind_change_pct': ind_change * 100
                })
                continue

        prev_low_pos = int(np.argmin(recent_price.values))
        dist_low = lb - prev_low_pos
        prev_low_price = float(recent_price.iloc[prev_low_pos])
        prev_low_ind = float(recent_ind.iloc[prev_low_pos])

        if dist_low >= 2 and prev_low_price != 0 and prev_low_ind != 0:
            price_close_low = p_now <= prev_low_price * (1 + price_tol)
            ind_change = (i_now - prev_low_ind) / abs(prev_low_ind)

            if price_close_low and ind_change >= ind_drop_min:
                is_new_low = p_now < prev_low_price
                result[label].append({
                    'type': '底',
                    'tag': '新低' if is_new_low else '雙底',
                    'current_price': p_now,
                    'prev_price': prev_low_price,
                    'current_ind': i_now,
                    'prev_ind': prev_low_ind,
                    'dist': dist_low,
                    'price_diff_pct': (p_now - prev_low_price) / prev_low_price * 100,
                    'ind_change_pct': ind_change * 100
                })

    return result


# ==================== 參數 ====================

PIVOT_CONFIG = [
    ('M', '1mo', '5y',  60,  {'prominence_pct': 5.0, 'distance': 2, 'recent_window': 3}),
    ('W', '1wk', '3y',  100, {'prominence_pct': 3.0, 'distance': 2, 'recent_window': 4}),
]

DUAL_LB_CONFIG = {
    'M':  {'short': 3, 'long': 6,  'price_tol': 0.02,  'ind_drop': 0.05},
    'W':  {'short': 4, 'long': 10, 'price_tol': 0.015, 'ind_drop': 0.05},
    'D':  {'short': 5, 'long': 20, 'price_tol': 0.005, 'ind_drop': 0.05},
    '4H': {'short': 5, 'long': 20, 'price_tol': 0.003, 'ind_drop': 0.05},
}

INTERVAL_MAP = {
    'M':  ('1mo', '5y',  60),
    'W':  ('1wk', '3y',  100),
    'D':  ('1d',  '6mo', 30),
    '4H': ('1h',  '60d', 60),
}


# ==================== 掃描 ====================

def scan_pivot(t, info, lv, params):
    results = []
    try:
        raw_df = get_raw_df(t, lv)
        if len(raw_df) < 40:
            return results
        calc_df = calculate_custom_indicators(raw_df)
        p_s = calc_df['Close']
        last_idx = len(calc_df) - 1
        highs, lows = scipy_pivots(
            p_s, prominence_pct=params['prominence_pct'], distance=params['distance']
        )
        rw = params['recent_window']

        d = check_pivot_divergence(p_s, calc_df['DIF'], highs, lows, last_idx, rw)
        if d:
            results.append({'ind': 'DIF', 'dir': d[0], 'dist': d[1]})

        d = check_pivot_divergence(p_s, calc_df['J'], highs, lows, last_idx, rw)
        if d:
            curr_j = float(calc_df['J'].iloc[-1])
            if (d[0] == '頂' and curr_j > 70) or (d[0] == '底' and curr_j < 30):
                results.append({'ind': 'J', 'dir': d[0], 'dist': d[1]})
    except Exception as e:
        print(f"[scan_pivot] {t} {lv}: {e}", flush=True)
    return results


def scan_dual_lookback(t, info, lv, lb_flow=None):
    results = []
    try:
        raw_df = get_raw_df(t, lv)
        if len(raw_df) < 40:
            return results

        if lv in ['M', 'W']:
            raw_df = raw_df.iloc[:-1]

        if lv in ['D', '4H']:
            live_price = get_live_price(t)
            if live_price is not None:
                raw_df = raw_df.copy()
                raw_df.iloc[-1, raw_df.columns.get_loc('Close')] = live_price
                if live_price > raw_df.iloc[-1]['High']:
                    raw_df.iloc[-1, raw_df.columns.get_loc('High')] = live_price
                if live_price < raw_df.iloc[-1]['Low']:
                    raw_df.iloc[-1, raw_df.columns.get_loc('Low')] = live_price

        if len(raw_df) < 40:
            return results

        calc_df = calculate_custom_indicators(raw_df)
        p_s = calc_df['Close']
        last_close = float(p_s.iloc[-1])
        last_ema50 = float(calc_df['EMA50'].iloc[-1])
        params = DUAL_LB_CONFIG[lv]

        for ind_name in ['DIF', 'J']:
            r = check_dual_lookback(
                p_s, calc_df[ind_name],
                short_lb=params['short'], long_lb=params['long'],
                price_tol=params['price_tol'], ind_drop_min=params['ind_drop']
            )
            for lb_type in ['long', 'short']:
                for sig in r[lb_type]:
                    if lv in ['M', 'W']:
                        sig['dist'] += 1  # 補償切走未收盤根的 1 個週期偏移
                    sig['ind'] = ind_name
                    sig['lookback'] = lb_type
                    sig['trend_tag'] = get_trend_context(last_close, last_ema50, sig['type'])
                    sig['qqq_impact'] = get_qqq_impact_tag(t, sig['type'])
                    sig['flow_tag'] = get_flow_resonance_tag(t, sig['type'], lb_flow)
                    results.append(sig)

    except Exception as e:
        print(f"[scan_dual_lookback] {t} {lv}: {e}", flush=True)
    return results


def filter_by_win_rate(signals):
    """過濾歷史勝率低於 MIN_WIN_RATE 的雜訊訊號（無回測數據者保留）"""
    kept = []
    filtered_count = 0
    for s in signals:
        direction = s.get('type') or s.get('dir')
        wr, _ = get_win_info(s['ticker'], s['level'], direction)
        if wr is not None and wr < MIN_WIN_RATE:
            filtered_count += 1
            continue
        kept.append(s)
    return kept, filtered_count


def load_recent_mw_history():
    """讀取近 7 日已報過的 M/W 訊號，用於標記 [新觸發] 或 [持續中]"""
    seen = set()
    if not os.path.exists('history.csv'):
        return seen
    try:
        df = pd.read_csv('history.csv', encoding='utf-8-sig')
        if df.empty or '日期' not in df.columns:
            return seen
        hkt_tz = timezone(timedelta(hours=8))
        today_str = datetime.now(hkt_tz).strftime('%Y-%m-%d')
        cutoff_str = (datetime.now(hkt_tz) - timedelta(days=7)).strftime('%Y-%m-%d')

        df['日期_str'] = df['日期'].astype(str).str[:10]
        past = df[(df['日期_str'] >= cutoff_str) & (df['日期_str'] < today_str) & (df['週期'].isin(['M', 'W']))]
        for _, row in past.iterrows():
            seen.add((str(row['標的']), str(row['週期']), str(row['方向'])))
    except Exception:
        pass
    return seen


# ==================== QQQ 0DTE 綜合多空評分 ====================

def compute_qqq_0dte_score(dual_dh, dual_mw, new_mw_keys, lb_flow):
    """計算 -10 至 +10 的 QQQ 0DTE 方向淨分"""
    score = 0.0
    reasons = []

    # 聚合每個 (ticker, level, type) 的最高強度背離
    unique_events = {}
    for s in dual_dh:
        key = (s['ticker'], s['level'], s['type'])
        unique_events[key] = s
    for s in dual_mw:
        key = (s['ticker'], s['level'], s['type'])
        if key in new_mw_keys:
            unique_events[key] = s

    for (ticker, lv, direction), s in unique_events.items():
        beta = ALL_TARGETS.get(ticker, {}).get('qqq_beta', 0.0)
        if beta == 0:
            continue

        # 底背離 = +1，頂背離 = -1；乘以 qqq_beta 後自動反轉 ^TNX / DXY / VIX 方向
        dir_sign = 1.0 if direction == '底' else -1.0
        lv_mult = 1.2 if lv == 'W' else (1.0 if lv == 'D' else 0.7)
        pts = beta * dir_sign * lv_mult
        score += pts

        name = ALL_TARGETS.get(ticker, {}).get('name', ticker)
        reasons.append((abs(pts), f"{name}[{lv}{direction}]({pts:+.1f})"))

    # 加上長橋 QQQ 資金流微調
    if lb_flow and 'QQQ' in lb_flow['by_symbol']:
        qqq_net = float(lb_flow['by_symbol']['QQQ'].get('main_net_inflow', 0))
        if qqq_net >= 5.0e7:
            score += 1.0
            reasons.append((1.0, f"QQQ資金淨流入({fmt_money_short(qqq_net)})"))
        elif qqq_net <= -5.0e7:
            score -= 1.0
            reasons.append((1.0, f"QQQ資金淨流出({fmt_money_short(qqq_net)})"))

    score = max(-10.0, min(10.0, round(score, 1)))
    reasons.sort(key=lambda x: -x[0])
    top_drivers = "、".join(r[1] for r in reasons[:3]) if reasons else "暫無強驅動因子"

    if score >= 3.0:
        verdict = f"🟢 偏多主攻 ({score:+.1f} 分)｜回踩支撐優先做 Call，忌逆勢摸頂"
    elif score >= 1.0:
        verdict = f"🟢 震盪偏多 ({score:+.1f} 分)｜低吸 Call 為主，遇 R1 壓力分批止盈"
    elif score <= -3.0:
        verdict = f"🔴 偏空主攻 ({score:+.1f} 分)｜反彈阻力優先做 Put，忌盲目接飛刀"
    elif score <= -1.0:
        verdict = f"🔴 震盪偏空 ({score:+.1f} 分)｜逢高佈局 Put 為主，破位順勢追空"
    else:
        verdict = f"⚪ 多空拉鋸 ({score:+.1f} 分)｜區間高拋低吸，嚴守 5m EMA 帶突破跟單"

    return {
        'score': score,
        'verdict': verdict,
        'drivers': top_drivers,
    }


# ==================== 財經日曆（FMP 轉香港時間 HKT）====================

def get_fmp_calendar():
    if not FMP_API_KEY:
        return "📅 【今晚 0DTE 關鍵日曆】：\n   (未設定 FMP API key)"

    try:
        hkt_tz = timezone(timedelta(hours=8))
        now_hkt = datetime.now(hkt_tz)
        today_str = now_hkt.strftime('%Y-%m-%d')
        tomorrow_str = (now_hkt + timedelta(days=1)).strftime('%Y-%m-%d')

        url = (
            f"https://financialmodelingprep.com/api/v3/economic_calendar"
            f"?from={today_str}&to={tomorrow_str}&apikey={FMP_API_KEY}"
        )
        r = requests.get(url, timeout=15)
        data = r.json()

        if not isinstance(data, list) or len(data) == 0:
            return "📅 【今晚 0DTE 關鍵日曆】：\n   🟢 今日暫無重大經濟事件"

        # 篩選今日 08:00 HKT 至明日 07:00 HKT 之間（完整覆蓋今晚美股交易時段）的高影響事件
        window_start = now_hkt.replace(hour=8, minute=0, second=0, microsecond=0)
        window_end = window_start + timedelta(hours=23)

        high_impact = []
        for e in data:
            if e.get('impact') != 'High':
                continue
            event_name = e.get('event', '')
            if 'open' in event_name.lower() or '開盤' in event_name:
                continue

            raw_date = e.get('date', '')
            try:
                utc_dt = datetime.strptime(raw_date[:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                hkt_dt = utc_dt.astimezone(hkt_tz)
                if not (window_start <= hkt_dt <= window_end):
                    continue
                hkt_time_str = hkt_dt.strftime('%H:%M HKT')
            except Exception:
                hkt_time_str = raw_date[-8:-3] + ' UTC'

            high_impact.append((hkt_time_str, e))

        high_impact.sort(key=lambda x: x[0])

        lines = ["📅 【今晚 0DTE 關鍵日曆（高影響 · 香港時間）】："]
        if high_impact:
            for hkt_time_str, e in high_impact[:10]:
                event_name = e.get('event', 'Unknown')
                country = e.get('country', '')
                actual = e.get('actual')
                estimate = e.get('estimate')
                previous = e.get('previous')

                value_parts = []
                if actual is not None:
                    value_parts.append(f"實際 {actual}")
                if estimate is not None:
                    value_parts.append(f"預期 {estimate}")
                if previous is not None:
                    value_parts.append(f"前值 {previous}")

                value_str = " | ".join(value_parts)
                lines.append(f"   * {hkt_time_str} | {country} {event_name}")
                if value_str:
                    lines.append(f"     └─ {value_str}")
        else:
            lines.append("   🟢 今晚美股時段暫無高影響數據")

        lines.extend([
            "",
            "🛡️ 【0DTE 風控鐵律】：",
            "   1. 數據前 15 分鐘：平 15s/1m 末日短線倉",
            "   2. 數據後 15 分鐘：待 EMA 帶定型再入場"
        ])
        return "\n".join(lines)
    except Exception as e:
        return f"📅 【今晚 0DTE 關鍵日曆】：\n   (FMP API 失敗: {e})"


# ==================== 隔夜數據、NQ 與 QQQ 關鍵位 + VIX 預期波幅 ====================

def calc_atr14(df):
    if len(df) < 15:
        return 0.0
    high = df['High']
    low = df['Low']
    prev_close = df['Close'].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return float(tr.rolling(14).mean().iloc[-1])


def get_prev_completed_idx(df):
    """動態判斷昨日已收盤 K 線索引（避免 06:00 HKT 美期剛收盤時錯取前日）"""
    if len(df) < 2:
        return -1
    last_bar_date = df.index[-1].date()
    today_et = datetime.now(timezone(timedelta(hours=-5))).date()
    # 若最後一根就是美東當日（例如 06:00 HKT 剛結束昨日交易日），直接用 iloc[-1] 作昨收
    if last_bar_date >= today_et:
        return -1
    return -2


def get_market_levels_bundle():
    """一次抓取隔夜宏觀、NQ=F 關鍵位、QQQ 現貨關鍵位與 VIX 預期波幅"""
    try:
        def h(sym, per='20d'):
            return yf.Ticker(sym).history(period=per, interval='1d')

        nq = h('NQ=F', '20d')
        qqq = h('QQQ', '20d')
        es, ym = h('ES=F', '5d'), h('YM=F', '5d')
        vix, gc, cl = h('^VIX', '5d'), h('GC=F', '5d'), h('CL=F', '5d')
        dxy, tnx = h('DX-Y.NYB', '5d'), h('^TNX', '5d')

        def pct(a, b):
            return ((a - b) / b) * 100 if b != 0 else 0.0

        def c(x):
            return float(x['Close'].iloc[-1])

        def p(x):
            return float(x['Close'].iloc[-2]) if len(x) >= 2 else c(x)

        vix_now = c(vix)
        nq_now = c(nq)
        qqq_now = c(qqq)

        header = "\n".join([
            "🌐 隔夜與宏觀數據：",
            f"   * 指數: NQ {nq_now:,.1f} ({pct(nq_now,p(nq)):+.2f}%) | QQQ ${qqq_now:,.2f} ({pct(qqq_now,p(qqq)):+.2f}%) | ES {c(es):,.1f} ({pct(c(es),p(es)):+.2f}%) | VIX {vix_now:.1f} ({pct(vix_now,p(vix)):+.2f}%)",
            f"   * 大宗: 黃金 ${c(gc):,.1f} ({pct(c(gc),p(gc)):+.2f}%) | 原油 ${c(cl):.2f} ({pct(c(cl),p(cl)):+.2f}%)",
            f"   * 宏觀: 美指 {c(dxy):.2f} ({pct(c(dxy),p(dxy)):+.2f}%) | 10年美債 {c(tnx):.3f}% ({pct(c(tnx),p(tnx)):+.2f}%)"
        ])

        # NQ=F Pivot
        nq_idx = get_prev_completed_idx(nq)
        nq_h = float(nq['High'].iloc[nq_idx])
        nq_l = float(nq['Low'].iloc[nq_idx])
        nq_c = float(nq['Close'].iloc[nq_idx])
        nq_pivot = (nq_h + nq_l + nq_c) / 3.0
        nq_r1 = 2 * nq_pivot - nq_l
        nq_s1 = 2 * nq_pivot - nq_h
        nq_5d_h = float(nq['High'].tail(5).max())
        nq_5d_l = float(nq['Low'].tail(5).min())
        nq_atr = calc_atr14(nq)

        # QQQ 現貨 Pivot + VIX 預期波幅
        qqq_idx = get_prev_completed_idx(qqq)
        qqq_h = float(qqq['High'].iloc[qqq_idx])
        qqq_l = float(qqq['Low'].iloc[qqq_idx])
        qqq_c = float(qqq['Close'].iloc[qqq_idx])
        qqq_pivot = (qqq_h + qqq_l + qqq_c) / 3.0
        qqq_r1 = 2 * qqq_pivot - qqq_l
        qqq_s1 = 2 * qqq_pivot - qqq_h
        qqq_5d_h = float(qqq['High'].tail(5).max())
        qqq_5d_l = float(qqq['Low'].tail(5).min())
        qqq_atr = calc_atr14(qqq)

        # VIX 隱含單日理論預期波幅 (Expected Move = Price * (VIX/100) / sqrt(252))
        em_pct = (vix_now / 100.0) / math.sqrt(252.0)
        qqq_em = qqq_now * em_pct
        nq_em = nq_now * em_pct

        levels_text = "\n".join([
            "🎯 QQQ 今晚 0DTE 現貨戰術卡位（直接對照 Strike）：",
            f"   * 5日強阻力 : ${qqq_5d_h:,.2f}  |  R1 第一壓力: ${qqq_r1:,.2f}",
            f"   * Pivot 中軸 : ${qqq_pivot:,.2f}  (昨收: ${qqq_c:,.2f})",
            f"   * S1 第一支撐: ${qqq_s1:,.2f}  |  5日強支撐 : ${qqq_5d_l:,.2f}",
            f"   * 📏 VIX 預期波幅: ±${qqq_em:.2f} (±{em_pct*100:.2f}%) → 理論區間 ${qqq_now - qqq_em:,.2f} ~ ${qqq_now + qqq_em:,.2f} | 14D ATR: ${qqq_atr:.2f}",
            "",
            "📍 NQ=F 期貨對應卡位：",
            f"   * 5日高: {nq_5d_h:,.1f} | R1: {nq_r1:,.1f} | Pivot: {nq_pivot:,.1f} | S1: {nq_s1:,.1f} | 5日低: {nq_5d_l:,.1f}",
            f"   * 📏 NQ 預期波幅: ±{nq_em:.0f} 點 | 14D ATR: {nq_atr:.0f} 點"
        ])

        dashboard_nq = {
            'high': nq_5d_h,
            'low': nq_5d_l,
            'current': nq_now,
            'r1': nq_r1,
            'pivot': nq_pivot,
            's1': nq_s1,
            'qqq_current': qqq_now,
            'qqq_r1': qqq_r1,
            'qqq_pivot': qqq_pivot,
            'qqq_s1': qqq_s1,
            'qqq_em': round(qqq_em, 2),
        }

        return header, levels_text, dashboard_nq
    except Exception as e:
        print(f"[Market Levels] 失敗: {e}", flush=True)
        return "🌐 隔夜數據失敗", "📍 Key Levels 失敗", {'high': 0, 'low': 0, 'current': 0}


# ==================== NQ 5m EMA 帶（60d 數據令 EMA3500 更準確）====================

def get_nq_ema_bundle():
    try:
        raw_df = yf.Ticker('NQ=F').history(period='60d', interval='5m')
        if raw_df.empty or len(raw_df) < 100:
            return "NQ 5m 數據獲取失敗", None

        calc_df = calculate_custom_indicators(raw_df)
        last = calc_df.iloc[-1]
        price = float(last['Close'])

        lines = [
            "🛡️ 【NQ 5m EMA 700-1000 帶 & 3500 監測】：",
            f"   * 現價 : {price:,.1f}"
        ]

        band_vals = [float(v) for v in [last['EMA700'], last['EMA800'], last['EMA900'], last['EMA1000']] if not np.isnan(v)]
        if len(band_vals) >= 2:
            band_top, band_bot = max(band_vals), min(band_vals)
            w_pts = band_top - band_bot
            w_pct = (w_pts / price) * 100

            if w_pct < 0.15:
                status = f"🚨 【帶內極度黏合】({w_pts:.1f}點 / {w_pct:.2f}%)"
                hint = "籌碼極度集中！突破易爆單邊強趨勢。"
            elif w_pct > 0.60:
                status = f"⚠️ 【帶內寬幅發散】({w_pts:.1f}點 / {w_pct:.2f}%)"
                hint = "動能發散，留意背離見好即收。"
            else:
                status = f"🟢 【常態帶寬】({w_pts:.1f}點 / {w_pct:.2f}%)"
                hint = "按 15s/1m 貼身線與背離正常操作。"

            lines.append(f"   * 📍 5m EMA 700-1000 帶 : {band_bot:,.1f} - {band_top:,.1f}")
            lines.append(f"     └─ {status}")

            e3500 = float(last['EMA3500']) if not np.isnan(last['EMA3500']) else None
            if e3500 is not None:
                lines.append(f"   * 🏛️ 5m EMA 3500 : {e3500:,.1f}")
                if e3500 > band_top:
                    cross = "🚨 3500 在帶上方 (長線壓制)"
                elif e3500 < band_bot:
                    cross = "🟢 3500 在帶下方 (標準多頭)"
                else:
                    cross = "⚡ 3500 穿越/嵌入帶 (極易洗盤！)"
                lines.append(f"     └─ {cross}")
            else:
                lines.append("   * 🏛️ 5m EMA 3500 : 數據不足")
            lines.append(f"   🎯 {hint}")

            ema_dict = {
                'current': price,
                'band_top': band_top,
                'band_bot': band_bot,
                'ema3500': e3500,
            }
            return "\n".join(lines), ema_dict

        return "\n".join(lines), None
    except Exception as e:
        return f"5m 均線帶失敗: {e}", None


# ==================== 格式化 ====================

def cap_pct(pct):
    if pct > 100:
        return ">+100%"
    if pct < -100:
        return "<-100%"
    return f"{pct:+.2f}%"


def fmt_pivot_signal(sig):
    time_str = time_ago(sig['dist'], sig['level'])
    wr, cnt = get_win_info(sig['ticker'], sig['level'], sig['dir'])
    win_str = f" | 勝率 {wr*100:.1f}%{get_win_tag(wr, cnt)}" if wr is not None else ""
    impact = get_qqq_impact_tag(sig['ticker'], sig['dir'])
    impact_str = f" {impact}" if impact else ""
    return f"   ⚡ [已確認] [{sig['level']}][{sig['ind']}] {sig['dir']}背離 ({time_str}){win_str}{impact_str}"


def fmt_dual_signal_body(sig):
    label = sig.get('lookback', 'long')
    is_long = (label == 'long')

    icon = '🔥🔥' if is_long else '🔥'
    if sig['tag'] in ['雙頂', '雙底']:
        icon = '⚡⚡' if is_long else '⚡'

    label_str = '長' if is_long else '短'
    ind_name = sig['ind']
    lv = sig['level']
    time_str = time_ago(sig['dist'], lv)
    price_pct = cap_pct(sig['price_diff_pct'])
    ind_pct = cap_pct(sig['ind_change_pct'])
    strength, strength_icon = get_strength(sig['ind_change_pct'])

    wr, cnt = get_win_info(sig['ticker'], lv, sig['type'])
    win_tag = get_win_tag(wr, cnt)
    win_str = f" | 歷史勝率 {wr*100:.1f}%{win_tag}" if wr is not None else ""

    extra_tags = "".join(filter(None, [
        f" {sig.get('trend_tag', '')}" if sig.get('trend_tag') else "",
        sig.get('flow_tag', ''),
        f" {sig.get('qqq_impact', '')}" if sig.get('qqq_impact') else "",
    ]))

    return (
        f"      [{lv}][{ind_name}] {icon} {label_str}{sig['tag']} {strength_icon}{strength}："
        f"前{'高' if sig['type'] == '頂' else '低'} {sig['prev_price']:,.2f} ({time_str}){extra_tags}\n"
        f"            價: {price_pct} / {ind_name}: {ind_pct}{win_str}"
    )


def group_dual_by_ticker(signals):
    groups = {}
    for s in signals:
        groups.setdefault(s['ticker'], []).append(s)

    blocks = []
    for ticker, sigs in groups.items():
        info = ALL_TARGETS[ticker]
        top_sigs = [s for s in sigs if s['type'] == '頂']
        bot_sigs = [s for s in sigs if s['type'] == '底']

        current_price = sigs[0]['current_price']
        header = f"🚨 {info['name']} ({ticker}) (現價 {current_price:,.2f})"
        body_lines = []

        for label_title, sub_sigs in [("   🔴 頂背離", top_sigs), ("   🟢 底背離", bot_sigs)]:
            if not sub_sigs:
                continue
            body_lines.append(label_title)
            long_s = [s for s in sub_sigs if s.get('lookback') == 'long']
            short_s = [s for s in sub_sigs if s.get('lookback') == 'short']
            display = long_s if long_s else short_s
            display = sorted(display, key=lambda x: (0 if x['ind'] == 'DIF' else 1))
            for s in display:
                body_lines.append(fmt_dual_signal_body(s))
            if long_s and short_s:
                body_lines.append("      ⚡ 另有短訊號（未顯示）")

        if top_sigs and bot_sigs:
            body_lines.append("   ⚠️ 短長方向矛盾")

        blocks.append(header + "\n" + "\n".join(body_lines))

    return blocks


def build_macro_section(pivot_sigs, dual_mw, seen_mw_history):
    """大勢背景：新觸發展開詳情，過去 7 日已報過的 M/W 訊號壓縮成一行避免洗版"""
    new_tickers = set()
    ongoing_items = []

    for s in pivot_sigs:
        if s['level'] in ['M', 'W']:
            key = (s['ticker'], s['level'], s['dir'])
            if key in seen_mw_history:
                name = ALL_TARGETS.get(s['ticker'], {}).get('name', s['ticker'])
                ongoing_items.append(f"{name}({s['level']}{s['dir']})")
            else:
                new_tickers.add(s['ticker'])

    for s in dual_mw:
        if s['level'] in ['M', 'W']:
            key = (s['ticker'], s['level'], s['type'])
            if key in seen_mw_history:
                name = ALL_TARGETS.get(s['ticker'], {}).get('name', s['ticker'])
                wr, _ = get_win_info(s['ticker'], s['level'], s['type'])
                wr_txt = f" {wr*100:.0f}%" if wr is not None else ""
                ongoing_items.append(f"{name}({s['level']}{s['type']}{wr_txt})")
            else:
                new_tickers.add(s['ticker'])

    lines = []
    for ticker in sorted(new_tickers):
        info = ALL_TARGETS.get(ticker, {})
        lines.append(f"{info.get('sticker', '')} 🆕 {info.get('name', ticker)} ({ticker})")

        for s in pivot_sigs:
            if s['ticker'] == ticker and s['level'] in ['M', 'W']:
                if (ticker, s['level'], s['dir']) not in seen_mw_history:
                    lines.append(fmt_pivot_signal(s))

        d_sigs = [
            s for s in dual_mw
            if s['ticker'] == ticker and s['level'] in ['M', 'W']
            and (ticker, s['level'], s['type']) not in seen_mw_history
        ]
        if d_sigs:
            top_sigs = [s for s in d_sigs if s['type'] == '頂']
            bot_sigs = [s for s in d_sigs if s['type'] == '底']
            for title, sub in [("   🔴 頂背離", top_sigs), ("   🟢 底背離", bot_sigs)]:
                if not sub:
                    continue
                lines.append(title)
                long_s = [s for s in sub if s.get('lookback') == 'long']
                short_s = [s for s in sub if s.get('lookback') == 'short']
                display = sorted(long_s if long_s else short_s, key=lambda x: (0 if x['ind'] == 'DIF' else 1))
                for s in display:
                    lines.append(fmt_dual_signal_body(s))

        lines.append("")

    if ongoing_items:
        dedup_ongoing = sorted(set(ongoing_items))
        lines.append(f"🔄 持續中大週期（近7日已報）：{'、'.join(dedup_ongoing)}")

    return lines


def get_resonance(dual_mw, dual_dh):
    resonance = {}
    for s in dual_mw + dual_dh:
        key = (s['ticker'], s['type'])
        resonance.setdefault(key, set()).add(s['level'])

    results = []
    for (ticker, type_), levels in resonance.items():
        if len(levels) >= 2:
            name = ALL_TARGETS.get(ticker, {}).get('name', ticker)
            lvl_str = '+'.join(sorted(levels, key=lambda x: {'M': 1, 'W': 2, 'D': 3, '4H': 4}.get(x, 99)))
            stars = '⭐' * len(levels)
            impact = get_qqq_impact_tag(ticker, type_)
            results.append({
                'ticker': ticker, 'name': name, 'type': type_,
                'levels': lvl_str, 'count': len(levels), 'stars': stars,
                'impact': f" {impact}" if impact else ""
            })

    return sorted(results, key=lambda x: -x['count'])


# ==================== 歷史紀錄與 Dashboard 數據寫入 ====================

def save_history_and_dashboard(dual_mw, dual_dh, dashboard_nq, dashboard_ema, calendar_str, qqq_score_obj):
    today = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')

    grouped = {}
    for s in dual_mw + dual_dh:
        key = (s['ticker'], s['level'], s['type'])
        grouped.setdefault(key, []).append(s)

    rows = []
    for (ticker, level, direction), sigs in grouped.items():
        info = ALL_TARGETS.get(ticker, {})
        name = info.get('name', ticker)

        long_sigs = [s for s in sigs if s.get('lookback') == 'long']
        short_sigs = [s for s in sigs if s.get('lookback') == 'short']
        target_sigs = long_sigs if long_sigs else short_sigs
        if not target_sigs:
            continue

        dif_sig = next((s for s in target_sigs if s['ind'] == 'DIF'), None)
        j_sig = next((s for s in target_sigs if s['ind'] == 'J'), None)
        ref = dif_sig if dif_sig else j_sig

        strengths = []
        if dif_sig:
            strengths.append(get_strength(dif_sig['ind_change_pct'])[0])
        if j_sig:
            strengths.append(get_strength(j_sig['ind_change_pct'])[0])

        STRENGTH_RANK = {'弱': 1, '中': 2, '強': 3}
        RANK_TO_STRENGTH = {1: '弱', 2: '中', 3: '強'}
        base_rank = max(STRENGTH_RANK.get(s, 1) for s in strengths) if strengths else 1
        has_dif = dif_sig is not None
        has_j = j_sig is not None
        if has_dif and has_j:
            base_rank = min(base_rank + 1, 3)

        wr, _ = get_win_info(ticker, level, direction)
        win_rate_str = f"{wr*100:.1f}%" if wr is not None else ""

        rows.append({
            '日期': today,
            '標的': ticker,
            '中文名': name,
            '週期': level,
            '方向': direction,
            '前高/低': round(ref['prev_price'], 2),
            '現價': round(ref['current_price'], 2),
            '價變化%': round(ref['price_diff_pct'], 2),
            'DIF變化%': round(dif_sig['ind_change_pct'], 2) if dif_sig else '',
            'J變化%': round(j_sig['ind_change_pct'], 2) if j_sig else '',
            'DIF有冇': '有' if has_dif else '冇',
            'J有冇': '有' if has_j else '冇',
            '強度': RANK_TO_STRENGTH[base_rank],
            'lookback': 'long' if long_sigs else 'short',
            'tag': ref.get('tag', ''),
            '共振': '雙指標' if (has_dif and has_j) else '單指標',
            '歷史勝率': win_rate_str,
        })

    if rows:
        new_df = pd.DataFrame(rows)
        if os.path.exists('history.csv'):
            try:
                old_df = pd.read_csv('history.csv', encoding='utf-8-sig')
                if '日期' in old_df.columns:
                    old_df = old_df[old_df['日期'].astype(str) != today]
                combined = pd.concat([old_df, new_df], ignore_index=True)
            except Exception as e:
                print(f"⚠️ 讀舊 history.csv 失敗: {e}，直接覆蓋", flush=True)
                combined = new_df
        else:
            combined = new_df

        combined.to_csv('history.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 寫入 history.csv ({len(rows)} 行，總共 {len(combined)} 行)", flush=True)

    try:
        dashboard_data = {
            'nq_key_levels': dashboard_nq,
            'nq_ema': dashboard_ema,
            'fmp_calendar': calendar_str,
            'qqq_score': qqq_score_obj,
        }
        with open('dashboard_data.json', 'w', encoding='utf-8') as f:
            json.dump(dashboard_data, f, ensure_ascii=False, indent=2)
        print("✅ 寫入 dashboard_data.json", flush=True)
    except Exception as e:
        print(f"⚠️ 寫 dashboard_data.json 失敗: {e}", flush=True)


# ==================== Telegram 分段推送（防截斷）====================

def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] 未設定 token 或 chat_id，跳過", flush=True)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    chunks = []
    current = []
    curr_len = 0

    for line in text.split('\n'):
        if curr_len + len(line) + 1 > 3800 and current:
            chunks.append("\n".join(current))
            current = [line]
            curr_len = len(line)
        else:
            current.append(line)
            curr_len += len(line) + 1
    if current:
        chunks.append("\n".join(current))

    for idx, chunk in enumerate(chunks, 1):
        try:
            r = requests.post(url, json={
                'chat_id': TELEGRAM_CHAT_ID,
                'text': chunk,
                'disable_web_page_preview': True
            }, timeout=15)
            print(f"[Telegram 第{idx}/{len(chunks)}段] {r.status_code}", flush=True)
        except Exception as e:
            print(f"[Telegram 第{idx}段] 失敗: {e}", flush=True)


# ==================== 報告與手機版 HTML Email 組裝 ====================

def build_reports(pivot_sigs, dual_dh, dual_mw, filtered_total, seen_mw_history,
                  lb_flow, overnight_str, levels_str, nq_status, calendar_str, qqq_score_obj):
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    sep = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    L = [
        f"⚡ QQQ 0DTE 宏觀雷達 V21.0 | {now} HKT",
        sep,
        f"🎯 {qqq_score_obj['verdict']}",
        f"   └─ 核心驅動：{qqq_score_obj['drivers']}",
        sep,
        "🏛️ 大勢背景（月 / 週線）",
        sep,
    ]

    macro_lines = build_macro_section(pivot_sigs, dual_mw, seen_mw_history)
    if macro_lines:
        L.extend(macro_lines)
    else:
        L.append("   🟢 暫無")

    resonance = get_resonance(dual_mw, dual_dh)
    if resonance:
        L.extend([sep, "⭐ 多週期共振", sep])
        for r in resonance:
            L.append(f"   {r['stars']} {r['name']} ({r['ticker']}) | {r['levels']} {r['type']}背離{r['impact']}")

    L.extend([sep, "🚨 今晚即時（日 / 4H · 勝率≥50%）", sep])
    if dual_dh:
        for block in group_dual_by_ticker(dual_dh):
            L.append(block)
    else:
        L.append("   🟢 暫無高勝率背離訊號")

    L.extend([sep, "💰 盤中資金流", sep, build_longbridge_summary(lb_flow)])
    L.extend([sep, "📍 QQQ & NQ 戰術卡位", sep, levels_str])
    L.extend([sep, "📊 隔夜與宏觀", sep, overnight_str])
    L.extend([sep, "🛡️ 5m EMA 帶監測", sep, nq_status])
    L.extend([sep, calendar_str, sep])

    if filtered_total > 0:
        L.append(f"ℹ️ 已自動過濾 {filtered_total} 個歷史勝率低於 {int(MIN_WIN_RATE*100)}% 的雜訊訊號")

    plain_text = "\n".join(L)

    # 手機版響應式 HTML Email（避免等寬 pre 在手機螢幕折行變形）
    score_val = qqq_score_obj['score']
    banner_bg = "#163322" if score_val >= 1.0 else ("#3b1818" if score_val <= -1.0 else "#1e242c")
    banner_border = "#3fb950" if score_val >= 1.0 else ("#f85149" if score_val <= -1.0 else "#58a6ff")

    escaped_body = (
        plain_text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )

    html_email = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:12px;background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:14px;line-height:1.6;">
  <div style="max-width:680px;margin:0 auto;background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px;">
    <div style="background:{banner_bg};border-left:4px solid {banner_border};padding:12px;border-radius:6px;margin-bottom:14px;">
      <div style="font-size:16px;font-weight:bold;color:#ffffff;">{qqq_score_obj['verdict']}</div>
      <div style="font-size:12px;color:#8b949e;margin-top:4px;">驅動因子：{qqq_score_obj['drivers']}</div>
    </div>
    <div style="word-break:break-word;white-space:normal;">
      {escaped_body}
    </div>
  </div>
</body>
</html>"""

    return plain_text, html_email


# ==================== 主程式 ====================

def main():
    try:
        dashboard_only = is_dashboard_only()
        print(f"=== 模式: {'Dashboard Only (21:00)' if dashboard_only else 'Full (06:00)'} ===", flush=True)

        overnight_str, levels_str, dashboard_nq = get_market_levels_bundle()
        nq_status, dashboard_ema = get_nq_ema_bundle()
        calendar_str = get_fmp_calendar()

        if dashboard_only:
            print("=== 21:00 Dashboard 更新 ===", flush=True)
            prev_score = {}
            if os.path.exists('dashboard_data.json'):
                try:
                    with open('dashboard_data.json', 'r', encoding='utf-8') as f:
                        prev_score = json.load(f).get('qqq_score', {})
                except Exception:
                    pass

            save_history_and_dashboard([], [], dashboard_nq, dashboard_ema, calendar_str, prev_score)
            print("✅ 21:00 Dashboard 更新完成", flush=True)
            return

        print(f"=== 掃描 {len(ALL_TARGETS)} 個標的 ===", flush=True)
        lb_flow = load_longbridge_flow()
        seen_mw_history = load_recent_mw_history()

        raw_pivot = []
        raw_dual_mw = []
        raw_dual_dh = []

        for t, info in ALL_TARGETS.items():
            for lv, _, _, _, params in PIVOT_CONFIG:
                for r in scan_pivot(t, info, lv, params):
                    raw_pivot.append({**info, 'ticker': t, 'level': lv, **r})

            for lv in ['M', 'W']:
                for r in scan_dual_lookback(t, info, lv, lb_flow=lb_flow):
                    raw_dual_mw.append({**info, 'ticker': t, 'level': lv, **r})

            for lv in ['D', '4H']:
                for r in scan_dual_lookback(t, info, lv, lb_flow=lb_flow):
                    raw_dual_dh.append({**info, 'ticker': t, 'level': lv, **r})

        pivot_sigs, f1 = filter_by_win_rate(raw_pivot)
        dual_mw, f2 = filter_by_win_rate(raw_dual_mw)
        dual_dh, f3 = filter_by_win_rate(raw_dual_dh)
        filtered_total = f1 + f2 + f3

        print(
            f"有效訊號 -> Pivot: {len(pivot_sigs)} | M/W: {len(dual_mw)} | D/4H: {len(dual_dh)} (已過濾低勝率: {filtered_total})",
            flush=True
        )

        new_mw_keys = {
            (s['ticker'], s['level'], s['type'])
            for s in dual_mw
            if (s['ticker'], s['level'], s['type']) not in seen_mw_history
        }
        qqq_score_obj = compute_qqq_0dte_score(dual_dh, dual_mw, new_mw_keys, lb_flow)

        save_history_and_dashboard(dual_mw, dual_dh, dashboard_nq, dashboard_ema, calendar_str, qqq_score_obj)

        plain_text, html_email = build_reports(
            pivot_sigs, dual_dh, dual_mw, filtered_total, seen_mw_history,
            lb_flow, overnight_str, levels_str, nq_status, calendar_str, qqq_score_obj
        )

        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"⚡ [QQQ 0DTE V21.0] {qqq_score_obj['verdict'].split('｜')[0]} ({datetime.now(timezone(timedelta(hours=8))).strftime('%m/%d')})"
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = EMAIL_CONFIG['receiver_email']
        msg.attach(MIMEText(plain_text, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_email, 'html', 'utf-8'))

        s = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        s.starttls()
        s.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        s.send_message(msg)
        s.quit()
        print("✅ Email 已發送", flush=True)

        send_telegram(plain_text)

    except Exception as e:
        print(f"❌ 失敗: {e}", flush=True)
        traceback.print_exc()


if __name__ == '__main__':
    main()
