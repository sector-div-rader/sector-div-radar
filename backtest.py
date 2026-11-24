# backtest.py - 回測雷達（18 個標的，含三大期指）
# 用歷史數據模擬每日雷達，計算獨立事件成功率
# 輸出 backtest_results.json

import os
import json
import yfinance as yf
import pandas as pd
import numpy as np

os.makedirs("/tmp/yf_cache", exist_ok=True)
yf.set_tz_cache_location("/tmp/yf_cache")

# ==================== 參數（與 main.py 18 個標的完全對齊）====================

TICKERS = [
    'NQ=F', 'ES=F', 'YM=F',
    '^VIX', 'GC=F', 'CL=F', 'DX-Y.NYB', '^TNX',
    'SMH', 'IGV', 'XLC', 'XLY', 'XLF',
    'XLE', 'XLI', 'XLV', 'XLP', 'XLU',
]

LEVELS = ['M', 'W', 'D', '4H']

INTERVAL_MAP = {
    'M':  ('1mo', '10y'),
    'W':  ('1wk', '10y'),
    'D':  ('1d',  '10y'),
    '4H': ('1h',  '730d'),  # 1h 最長支援 730 日（約 2 年），比 60d 樣本更可靠
}

DUAL_LB_CONFIG = {
    'M':  {'short': 3,  'long': 6,  'price_tol': 0.02,  'ind_drop': 0.05},
    'W':  {'short': 4,  'long': 10, 'price_tol': 0.015, 'ind_drop': 0.05},
    'D':  {'short': 5,  'long': 20, 'price_tol': 0.005, 'ind_drop': 0.05},
    '4H': {'short': 5,  'long': 20, 'price_tol': 0.003, 'ind_drop': 0.05},
}

# 同一方向訊號冷卻期（避免連續幾根 K 線磨底/磨頂重複計算同一次事件）
COOLDOWN_BARS = {
    'M': 2,
    'W': 3,
    'D': 3,
    '4H': 4,
}

# ==================== 技術指標 ====================

def calculate_macd(close, fast=5, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = dif - dea
    return dif, dea, hist


def calculate_kdj(df, n=9, m1=3, m2=3):
    low = df['Low'].rolling(n).min()
    high = df['High'].rolling(n).max()
    denom = (high - low).replace(0, np.nan)
    rsv = ((df['Close'] - low) / denom * 100).fillna(50)
    k = rsv.ewm(com=m1 - 1, adjust=False).mean()
    d = k.ewm(com=m2 - 1, adjust=False).mean()
    j = 3 * k - 2 * d
    return j


def check_dual_lookback_fast(close_arr, ind_arr, last_idx, lb, price_tol, ind_drop_min):
    """高速 NumPy 版背離檢測（強制 dist >= 2 避免相鄰 K 線假訊號）"""
    if last_idx - lb < 0:
        return None

    p_now = close_arr[last_idx]
    i_now = ind_arr[last_idx]
    if np.isnan(p_now) or np.isnan(i_now):
        return None

    recent_price = close_arr[last_idx - lb:last_idx]
    recent_ind = ind_arr[last_idx - lb:last_idx]
    if len(recent_price) == 0:
        return None

    # 1. 檢查頂背離
    prev_high_pos = int(np.argmax(recent_price))
    dist_high = lb - prev_high_pos
    if dist_high >= 2:
        prev_high_price = recent_price[prev_high_pos]
        prev_high_ind = recent_ind[prev_high_pos]
        if prev_high_price != 0 and prev_high_ind != 0 and not np.isnan(prev_high_ind):
            price_close = p_now >= prev_high_price * (1.0 - price_tol)
            ind_change = (i_now - prev_high_ind) / abs(prev_high_ind)
            if price_close and ind_change <= -ind_drop_min:
                return {
                    'type': '頂',
                    'tag': '新高' if p_now > prev_high_price else '雙頂',
                    'ind_change_pct': float(ind_change * 100),
                }

    # 2. 檢查底背離
    prev_low_pos = int(np.argmin(recent_price))
    dist_low = lb - prev_low_pos
    if dist_low >= 2:
        prev_low_price = recent_price[prev_low_pos]
        prev_low_ind = recent_ind[prev_low_pos]
        if prev_low_price != 0 and prev_low_ind != 0 and not np.isnan(prev_low_ind):
            price_close_low = p_now <= prev_low_price * (1.0 + price_tol)
            ind_change = (i_now - prev_low_ind) / abs(prev_low_ind)
            if price_close_low and ind_change >= ind_drop_min:
                return {
                    'type': '底',
                    'tag': '新低' if p_now < prev_low_price else '雙底',
                    'ind_change_pct': float(ind_change * 100),
                }

    return None


def backtest_level(df, lv):
    calc_df = df.copy()
    calc_df['DIF'], _, _ = calculate_macd(calc_df['Close'])
    calc_df['J'] = calculate_kdj(calc_df)

    close_arr = calc_df['Close'].to_numpy(dtype=float)
    dif_arr = calc_df['DIF'].to_numpy(dtype=float)
    j_arr = calc_df['J'].to_numpy(dtype=float)

    params = DUAL_LB_CONFIG[lv]
    cooldown = COOLDOWN_BARS[lv]
    signals = []
    last_trigger_idx = {'頂': -999, '底': -999}

    start_idx = max(params['long'] + 5, 30)  # 等待 EMA26 穩定
    for i in range(start_idx, len(calc_df) - 5):
        dif_sig = check_dual_lookback_fast(
            close_arr, dif_arr, i, params['long'], params['price_tol'], params['ind_drop']
        )
        j_sig = check_dual_lookback_fast(
            close_arr, j_arr, i, params['long'], params['price_tol'], params['ind_drop']
        )

        # 同一根 K 線合併去重，對齊 main.py 每日每方向一條訊號的邏輯
        for direction in ['頂', '底']:
            has_dif = dif_sig is not None and dif_sig['type'] == direction
            has_j = j_sig is not None and j_sig['type'] == direction

            if not (has_dif or has_j):
                continue

            # 冷卻期過濾，避免連續幾根 K 線重複計數同一次事件
            if i - last_trigger_idx[direction] < cooldown:
                continue

            last_trigger_idx[direction] = i
            ref = dif_sig if has_dif else j_sig

            signals.append({
                'idx': i,
                'date': str(calc_df.index[i]),
                'type': direction,
                'tag': ref['tag'],
                'resonance': '雙指標' if (has_dif and has_j) else '單指標',
                'entry_price': float(close_arr[i]),
            })

    return signals


def calc_stats(signals, close_arr, direction, t_days):
    valid = []
    n_bars = len(close_arr)

    for s in signals:
        if s['type'] != direction:
            continue
        entry_idx = s['idx']
        if entry_idx + t_days >= n_bars:
            continue

        entry = s['entry_price']
        exit_price = float(close_arr[entry_idx + t_days])
        if entry == 0 or np.isnan(exit_price):
            continue

        change = (exit_price - entry) / entry * 100
        win = (change < 0) if direction == '頂' else (change > 0)
        valid.append({'change': change, 'win': win})

    if not valid:
        return None

    wins = sum(1 for v in valid if v['win'])
    avg = sum(v['change'] for v in valid) / len(valid)

    return {
        'count': len(valid),
        'winRate': round(wins / len(valid) * 100, 1),
        'avgChange': round(avg, 2),
    }


def fetch_history_with_fallback(ticker, lv):
    itv, per = INTERVAL_MAP[lv]
    raw_df = yf.Ticker(ticker).history(period=per, interval=itv)

    # 若個別標的不支援 730d 1h，自動降級至 60d
    if raw_df.empty and lv == '4H' and per == '730d':
        raw_df = yf.Ticker(ticker).history(period='60d', interval='1h')

    if lv == '4H' and not raw_df.empty:
        raw_df = raw_df.resample('4h').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min',
            'Close': 'last', 'Volume': 'sum'
        }).dropna()

    return raw_df


def main():
    print(f"=== 雷達回測（{len(TICKERS)} 個標的）===\n", flush=True)

    all_results = {}

    for ticker in TICKERS:
        print(f"{'='*60}")
        print(f"回測 {ticker}", flush=True)
        all_results[ticker] = {}

        for lv in LEVELS:
            _, per = INTERVAL_MAP[lv]
            try:
                raw_df = fetch_history_with_fallback(ticker, lv)

                if len(raw_df) < 60:
                    print(f"  [{lv}] ⚠️ 數據不足 ({len(raw_df)} 根)，跳過", flush=True)
                    continue

                close_arr = raw_df['Close'].to_numpy(dtype=float)
                signals = backtest_level(raw_df, lv)
                print(f"  [{lv}] 數據: {len(raw_df)} 根 | 獨立事件訊號: {len(signals)}", flush=True)

                all_results[ticker][lv] = {}

                for direction in ['頂', '底']:
                    dir_signals = [s for s in signals if s['type'] == direction]
                    all_results[ticker][lv][direction] = {
                        'total': len(dir_signals),
                        'T+1': calc_stats(signals, close_arr, direction, 1),
                        'T+3': calc_stats(signals, close_arr, direction, 3),
                        'T+5': calc_stats(signals, close_arr, direction, 5),
                    }
            except Exception as e:
                print(f"  [{lv}] ⚠️ 失敗：{e}", flush=True)

    # ===== 總結表 =====
    print("\n" + "=" * 68)
    print("回測結果總結（T+5 勝率 / 獨立樣本數）")
    print("=" * 68)

    for direction, title in [('底', '【底背離 T+5 成功率】'), ('頂', '【頂背離 T+5 成功率】')]:
        print(f"\n{title}")
        print(f"{'標的':<11} {'M':<13} {'W':<13} {'D':<13} {'4H':<13}")
        print("-" * 68)
        for ticker in TICKERS:
            row = f"{ticker:<11}"
            for lv in LEVELS:
                s = all_results.get(ticker, {}).get(lv, {}).get(direction, {}).get('T+5')
                if s:
                    cell = f"{s['winRate']:.1f}%({s['count']})"
                    row += f" {cell:<12}"
                else:
                    row += f" {'-':<12}"
            print(row)

    # ===== 輸出 JSON =====
    with open('backtest_results.json', 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 寫入 backtest_results.json", flush=True)


if __name__ == '__main__':
    main()
