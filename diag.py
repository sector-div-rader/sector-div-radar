# diag.py - 診斷 script，唔會 send email
# 用途：睇下每個標的喺每個週期搵到幾多 pivot / 幾多背離

import yfinance as yf
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from main import (
    ALL_TARGETS, calculate_custom_indicators,
    fractal_atr_pivots, scipy_pivots, check_divergence
)

config = [
    ('M',  '1mo', '5y',  60, 'fractal', {'n':3, 'atr_mult':2.0, 'recent_window':2}),
    ('W',  '1wk', '3y',  100, 'fractal', {'n':3, 'atr_mult':1.5, 'recent_window':2}),
    ('D',  '1d',  '6mo', 30,  'scipy',   {'prominence_pct':1.5, 'distance':3, 'recent_window':5}),
    ('4H', '1h',  '60d', 60,  'scipy',   {'prominence_pct':0.8, 'distance':3, 'recent_window':5}),
]

total_sigs = 0

for t, info in ALL_TARGETS.items():
    print(f"\n{'='*60}")
    print(f"【{t}】{info['name']}")
    print(f"{'='*60}")
    for lv, itv, per, lb, method, params in config:
        try:
            raw_df = yf.Ticker(t).history(period=per, interval=itv)
            if lv == '4H' and not raw_df.empty:
                raw_df = raw_df.resample('4h').agg({
                    'Open':'first','High':'max','Low':'min',
                    'Close':'last','Volume':'sum'
                }).dropna()
            if len(raw_df) < 40:
                print(f"  {lv:>3}: 數據不足 ({len(raw_df)})")
                continue

            calc_df = calculate_custom_indicators(raw_df)
            p_s = calc_df['Close']
            last_idx = len(calc_df) - 1

            if method == 'fractal':
                highs, lows = fractal_atr_pivots(raw_df, n=params['n'], atr_mult=params['atr_mult'])
            else:
                highs, lows = scipy_pivots(
                    p_s,
                    prominence_pct=params['prominence_pct'],
                    distance=params['distance']
                )

            recent_window = params['recent_window']
            recent_highs = [h for h in highs if last_idx - h <= recent_window]
            recent_lows = [l for l in lows if last_idx - l <= recent_window]

            # 檢查背離
            d_dif = check_divergence(p_s, calc_df['DIF'], highs, lows, last_idx, recent_window)
            curr_j = calc_df['J'].iloc[-1]
            d_j = check_divergence(p_s, calc_df['J'], highs, lows, last_idx, recent_window)

            j_note = ""
            if d_j == '頂' and curr_j <= 75:
                j_note = f" (J={curr_j:.0f} 唔夠 75，filter 走)"
                d_j = None
            elif d_j == '底' and curr_j >= 25:
                j_note = f" (J={curr_j:.0f} 唔夠 25，filter 走)"
                d_j = None

            result = []
            if d_dif:
                result.append(f"DIF {d_dif}背離")
                total_sigs += 1
            if d_j:
                result.append(f"J {d_j}背離")
                total_sigs += 1

            print(f"  {lv:>3}: pivot H={len(highs):>2} L={len(lows):>2} | "
                  f"新鮮 H={len(recent_highs):>2} L={len(recent_lows):>2} | "
                  f"訊號: {', '.join(result) if result else '無'}{j_note}")

        except Exception as e:
            print(f"  {lv:>3}: 錯誤 {e}")

print(f"\n{'='*60}")
print(f"總共 {total_sigs} 個訊號")
print(f"{'='*60}")
