# radar_v11_index.py - 加中文板塊名

#... 上面 INDICES / SECTORS / FUTURES 不變...

def merge_signals(all_signals):
    grouped = {}
    for s in all_signals:
        key = (s['ticker'], s['dir'])
        grouped.setdefault(key, []).append(s)
    
    final_msgs = []
    level_order = {'4H':1, 'W':2, 'M':3}
    
    for (ticker, direction), sigs in grouped.items():
        sigs_sorted = sorted(sigs, key=lambda x: level_order[x['level']])
        levels = [s['level'] for s in sigs_sorted]
        if not levels: continue
        
        sticker = sigs[0]['sticker']
        name = sigs[0]['name'] # 加返中文名
        weight = max([s.get('weight',1) for s in sigs if s['level']=='M'], default=0)
        days = max([s.get('days',1) for s in sigs if s['level']=='M'], default=1)
        
        level_str = '+'.join(levels)
        icon = '🗓️' if 'M' in levels else '⚠️'
        weight_str = f" [{weight}分]" if 'M' in levels and weight>0 else ""
        days_str = f" 第{days}日" if 'M' in levels else ""
        name_str = f" - {name}" # 新增：中文板塊名
        
        final_msgs.append(f"{icon} {sticker} {ticker} {level_str}{direction}背離{weight_str}{days_str}{name_str}")
    
    return final_msgs

#... 其他 function 不變...

def main():
    #... 上面不變...
    
    if not all_signals:
        message = f"Radar V11 {now_str}\n\n今日無背離信號\n風險分數: 0/20"
        title = "Radar - No Signal"
        pri = "low"
    else:
        risk_score, tech_score, cycle_score, index_score, risk_tickers, advice = analyze_risk(all_signals)
        final_msgs = merge_signals(all_signals)
        
        header = []
        if risk_score >= 13:
            header.append(f"💀 末日級別 總分{risk_score} 科技{tech_score} 週期{cycle_score} 指數{index_score}")
        elif risk_score >= 8:
            header.append(f"🚨 系統風險 總分{risk_score} 科技{tech_score} 週期{cycle_score} 指數{index_score}")
        elif risk_score >= 5:
            header.append(f"⚠️ 高風險 總分{risk_score} 科技{tech_score} 週期{cycle_score} 指數{index_score}")
        else:
            header.append(f"📊 風險分數 總分{risk_score} 科技{tech_score} 週期{cycle_score} 指數{index_score}")
        
        if risk_tickers:
            # 月線觸發加中文名
            all_assets = {**INDICES, **SECTORS, **FUTURES}
            risk_names = [f"{t}({all_assets[t]['name']})" for t in risk_tickers]
            header.append(f"月線觸發：{', '.join(risk_names)}")
        header += advice
        
        message = f"Radar V11 {now_str}\n\n" + "\n\n".join(header + [""] + final_msgs)
        title = f"Risk:{risk_score} T{tech_score}C{cycle_score}I{index_score}"
        pri = "high" if risk_score >= 8 else "default"

    #... 下面不變...