# backtest.py - 回測雷達（15 個標的）
# 用 10 年歷史數據，模擬每日雷達，計算成功率
# 輸出 backtest_results.json

import yfinance as yf
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from scipy.signal import find_peaks

yf.set_tz_cache_location("/tmp/yf_cache")

# ==================== 參數 ====================

TICKERS = [
    '^VIX', 'GC=F', 'CL=F', 'DX-Y.NYB', '^TNX',
    'SMH', 'IGV', 'XLC', 'XLY', 'XLF',
    'XLE', 'XLI', 'XLV', 'XLP', 'XLU',
]

LEVELS = ['M', 'W', 'D', '4H']

INTERVAL_MAP = {
    'M':  ('1mo', '10y', 30),
    'W':  ('1wk', '10y', 30),
    'D':  ('1d',  '10y', 30),
    '4H': ('1h',  '60d', 60),
}

DUAL_LB_CONFIG = {
    'M':  {'short': 3,  'long': 6,  'price_tol': 0.02,  'ind_drop': 0.05},
    'W':  {'short': 4,  'long': 10, 'price_tol': 0.015, 'ind_drop': 0.05},
    'D':  {'short': 5,  'long': 20, 'price_tol': 0.005, 'ind_drop': 0.05},
    '4H': {'short': 5,  'long': 20, 'price_tol': 0.003, 'ind_drop': 0.05},
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
    rsv = (df['Close'] - low) / (high - low) * 100
    rsv = rsv.fillna(50)
    k = rsv.ewm(com=m1-1, adjust=False).mean()
    d = k.ewm(com=m2-1, adjust=False).mean()
    j = 3 * k - 2 * d
    return j


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
        prev_high_price = float(recent_price.iloc[prev_high_pos])
        prev_high_ind = float(recent_ind.iloc[prev_high_pos])

        if prev_high_price != 0 and prev_high_ind != 0:
            price_close = p_now >= prev_high_price * (1 - price_tol)
            ind_change = (i_now - prev_high_ind) / abs(prev_high_ind)

            if price_close and ind_change <= -ind_drop_min:
                result[label].append({
                    'type': '頂',
                    'tag': '新高' if p_now > prev_high_price else '雙頂',
                    'ind_change_pct': ind_change * 100
                })
                continue

        prev_low_pos = int(np.argmin(recent_price.values))
        prev_low_price = float(recent_price.iloc[prev_low_pos])
        prev_low_ind = float(recent_ind.iloc[prev_low_pos])

        if prev_low_price != 0 and prev_low_ind != 0:
            price_close_low = p_now <= prev_low_price * (1 + price_tol)
            ind_change = (i_now - prev_low_ind) / abs(prev_low_ind)

            if price_close_low and ind_change >= ind_drop_min:
                result[label].append({
                    'type': '底',
                    'tag': '新低' if p_now < prev_low_price else '雙底',
                    'ind_change_pct': ind_change * 100
                })

    return result


def backtest_level(df, lv):
    calc_df = df.copy()
    calc_df['DIF'], _, _ = calculate_macd(calc_df['Close'])
    calc_df['J'] = calculate_kdj(calc_df)

    params = DUAL_LB_CONFIG[lv]
    signals = []

    for i in range(params['long'] + 5, len(calc_df) - 5):
        sub = calc_df.iloc[:i+1]

        for ind_name in ['DIF', 'J']:
            r = check_dual_lookback(
                sub['Close'], sub[ind_name],
                short_lb=params['short'], long_lb=params['long'],
                price_tol=params['price_tol'], ind_drop_min=params['ind_drop']
            )

            for sig in r['long']:
                signals.append({
                    'idx': i,
                    'date': sub.index[i],
                    'ind': ind_name,
                    'type': sig['type'],
                    'tag': sig['tag'],
                    'entry_price': float(sub['Close'].iloc[-1]),
                })

    return signals


def calc_stats(signals, df, direction, t_days):
    valid = []
    for s in signals:
        if s['type'] != direction:
            continue
        entry_idx = s['idx']
        if entry_idx + t_days >= len(df):
            continue

        entry = s['entry_price']
        exit_price = float(df['Close'].iloc[entry_idx + t_days])

        if direction == '頂':
            change = (exit_price - entry) / entry * 100
            win = change < 0
        else:
            change = (exit_price - entry) / entry * 100
            win = change > 0

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


def main():
    print(f"=== 雷達回測（15 個標的）===\n")

    all_results = {}

    for ticker in TICKERS:
        print(f"\n{'='*60}")
        print(f"回測 {ticker}")
        print(f"{'='*60}")

        all_results[ticker] = {}

        for lv in LEVELS:
            itv, per, _ = INTERVAL_MAP[lv]
            print(f"  下載 {ticker} {lv}（{per}）...")

            try:
                raw_df = yf.Ticker(ticker).history(period=per, interval=itv)

                if lv == '4H' and not raw_df.empty:
                    raw_df = raw_df.resample('4h').agg({
                        'Open': 'first', 'High': 'max', 'Low': 'min',
                        'Close': 'last', 'Volume': 'sum'
                    }).dropna()

                if len(raw_df) < 100:
                    print(f"    ⚠️ 數據不足，跳過")
                    continue

                print(f"    數據：{len(raw_df)} 根")

                signals = backtest_level(raw_df, lv)
                print(f"    訊號數：{len(signals)}")

                all_results[ticker][lv] = {}

                for direction in ['頂', '底']:
                    dir_signals = [s for s in signals if s['type'] == direction]
                    all_results[ticker][lv][direction] = {
                        'total': len(dir_signals),
                        'T+1': calc_stats(signals, raw_df, direction, 1),
                        'T+3': calc_stats(signals, raw_df, direction, 3),
                        'T+5': calc_stats(signals, raw_df, direction, 5),
                    }
            except Exception as e:
                print(f"    ⚠️ 失敗：{e}")

    # ===== 總結表 =====
    print("\n" + "=" * 60)
    print("回測結果總結")
    print("=" * 60)

    print("\n【底背離 T+5 成功率】")
    print(f"{'標的':<12} {'M':<10} {'W':<10} {'D':<10} {'4H':<10}")
    print("-" * 55)
    for ticker in TICKERS:
        row = f"{ticker:<12}"
        for lv in LEVELS:
            if ticker in all_results and lv in all_results[ticker] and '底' in all_results[ticker][lv]:
                s = all_results[ticker][lv]['底']['T+5']
                if s:
                    row += f" {s['winRate']:>6.1f}%  "
                else:
                    row += f" {'-':<8}"
            else:
                row += f" {'-':<8}"
        print(row)

    print("\n【頂背離 T+5 成功率】")
    print(f"{'標的':<12} {'M':<10} {'W':<10} {'D':<10} {'4H':<10}")
    print("-" * 55)
    for ticker in TICKERS:
        row = f"{ticker:<12}"
        for lv in LEVELS:
            if ticker in all_results and lv in all_results[ticker] and '頂' in all_results[ticker][lv]:
                s = all_results[ticker][lv]['頂']['T+5']
                if s:
                    row += f" {s['winRate']:>6.1f}%  "
                else:
                    row += f" {'-':<8}"
            else:
                row += f" {'-':<8}"
        print(row)

    # ===== 輸出 JSON =====
    with open('backtest_results.json', 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 寫入 backtest_results.json")


if __name__ == '__main__':
    main()
