// assets/flow.js
const FLOW_COLORS = { inflow: '#16a34a', outflow: '#dc2626' };
let currentIntradayPeriod = 'all';
let intradayDataStore = [];
let intradayChartInstance = null;
let intradayTableInstance = null;

function isDarkMode() {
  return document.documentElement.getAttribute('data-theme') !== 'light';
}

// 自動注入 Tabulator 深淺色適配樣式（無需改 HTML CSS）
function injectTabulatorThemeStyle() {
  if (document.getElementById('tabulator-custom-theme')) return;
  const style = document.createElement('style');
  style.id = 'tabulator-custom-theme';
  style.textContent = `
    #intraday-flow-table.tabulator {
      background-color: var(--card);
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--text);
      font-size: 13px;
    }
    #intraday-flow-table .tabulator-header {
      background-color: var(--bg);
      color: var(--accent);
      border-bottom: 1px solid var(--border);
    }
    #intraday-flow-table .tabulator-header .tabulator-col {
      background-color: var(--bg);
      border-right: 1px solid var(--border);
    }
    #intraday-flow-table .tabulator-tableholder .tabulator-table {
      background-color: var(--card);
      color: var(--text);
    }
    #intraday-flow-table .tabulator-row {
      background-color: var(--card);
      color: var(--text);
      border-bottom: 1px solid var(--border);
    }
    #intraday-flow-table .tabulator-row.tabulator-row-even {
      background-color: rgba(128, 128, 128, 0.04);
    }
    #intraday-flow-table .tabulator-row:hover {
      background-color: rgba(88, 166, 255, 0.12) !important;
    }
    #intraday-flow-table .tabulator-cell {
      border-right: 1px solid var(--border);
    }
  `;
  document.head.appendChild(style);
}

function fmtMoney(v) {
  if (v == null || v === undefined || isNaN(v)) return '—';
  const abs = Math.abs(v);
  const sign = v >= 0 ? '+' : '-';
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function fmtHktTime(isoStr) {
  if (!isoStr) return '—';
  const d = new Date(isoStr);
  if (isNaN(d.getTime())) return isoStr;
  return d.toLocaleString('zh-HK', {
    timeZone: 'Asia/Hong_Kong',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }) + ' HKT';
}

function flowColorFormatter(cell) {
  const v = cell.getValue();
  if (v == null || isNaN(v)) return '—';
  const color = v >= 0 ? FLOW_COLORS.inflow : FLOW_COLORS.outflow;
  return `<span style="color:${color};font-weight:600;">${fmtMoney(v)}</span>`;
}

// ================= 即時數據區塊 =================
function renderIntradayChart(sorted, valueField) {
  const el = document.getElementById('intraday-flow-chart');
  if (!el) return;
  if (intradayChartInstance) intradayChartInstance.dispose();
  intradayChartInstance = echarts.init(el);

  const dark = isDarkMode();
  const textColor = dark ? '#c9d1d9' : '#1f2328';
  const gridColor = dark ? '#30363d' : '#d0d7de';

  const labels = sorted.map(s => `${s.symbol} ${s.name}`).reverse();
  const values = sorted.map(s => s[valueField] ?? 0).reverse();

  intradayChartInstance.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: dark ? '#161b22' : '#ffffff',
      borderColor: gridColor,
      textStyle: { color: textColor },
      formatter: p => `${p[0].name}<br/>淨流：<b>${fmtMoney(p[0].value)}</b>`,
    },
    grid: { left: 145, right: 75, top: 15, bottom: 28 },
    xAxis: {
      type: 'value',
      axisLabel: { formatter: v => fmtMoney(v), color: textColor, fontSize: 11 },
      splitLine: { lineStyle: { color: gridColor, type: 'dashed' } },
    },
    yAxis: {
      type: 'category',
      data: labels,
      axisLabel: { fontSize: 12, color: textColor },
      axisLine: { lineStyle: { color: gridColor } },
    },
    series: [{
      type: 'bar',
      barWidth: '60%',
      data: values.map(v => ({
        value: v,
        itemStyle: {
          color: v >= 0 ? FLOW_COLORS.inflow : FLOW_COLORS.outflow,
          borderRadius: v >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4],
        },
        label: {
          show: true,
          position: v >= 0 ? 'right' : 'left',
          formatter: () => fmtMoney(v),
          color: textColor,
          fontSize: 11,
        },
      })),
    }],
  });
}

function renderIntradayTable() {
  const fieldMap = {
    'all': 'main_net_inflow',
    'open_1h': 'net_inflow_open_1h',
    'mid': 'net_inflow_mid',
    'close_1h': 'net_inflow_close_1h',
  };
  const currentField = fieldMap[currentIntradayPeriod];
  const sorted = [...intradayDataStore].sort(
    (a, b) => (b[currentField] ?? -Infinity) - (a[currentField] ?? -Infinity)
  );

  if (intradayTableInstance) intradayTableInstance.destroy();
  intradayTableInstance = new Tabulator('#intraday-flow-table', {
    data: sorted,
    layout: 'fitColumns',
    columns: [
      { title: '#', formatter: 'rownum', width: 45, hozAlign: 'center', headerSort: false },
      { title: 'ETF', field: 'symbol', width: 68, formatter: c => `<strong>${c.getValue()}</strong>` },
      { title: '板塊', field: 'name', minWidth: 85 },
      { title: '淨流', field: currentField, hozAlign: 'right', formatter: flowColorFormatter, sorter: 'number' },
    ],
  });

  renderIntradayChart(sorted, currentField);
}

function switchIntradayPeriod(period, btn) {
  currentIntradayPeriod = period;
  document.querySelectorAll('#intraday-controls .btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderIntradayTable();
}

async function loadIntradayFlow() {
  try {
    const res = await fetch(`data/flow/intraday.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const hktUpdated = fmtHktTime(data.updated_at);
    const tradeDate = data.trade_date ? ` · 美股交易日：${data.trade_date}` : '';
    document.getElementById('intraday-updated').textContent =
      `更新時間：${hktUpdated}${tradeDate} · 來源：${data.note || 'Longbridge'}`;

    intradayDataStore = data.sectors || [];
    generateSmartInsights(intradayDataStore);
    renderIntradayTable();
  } catch (e) {
    document.getElementById('intraday-updated').textContent = `⚠️ 無法載入即時資金流數據：${e.message}`;
  }
}

// ================= 智能提示區塊 =================
function generateSmartInsights(data) {
  const insightEl = document.getElementById('flow-insights');
  if (!insightEl || !data || data.length === 0) return;

  // 動態計算門檻：取當日所有板塊絕對淨流入中位數的 1.5 倍，並設 $15M 底線
  const absTotals = data
    .map(s => Math.abs(s.main_net_inflow || 0))
    .filter(v => v > 0)
    .sort((a, b) => a - b);
  const medianFlow = absTotals.length > 0 ? absTotals[Math.floor(absTotals.length / 2)] : 0;
  const threshold = Math.max(1.5e7, medianFlow * 1.5);

  const alerts = [];

  data.forEach(s => {
    const total = s.main_net_inflow || 0;
    const open = s.net_inflow_open_1h || 0;
    const mid = s.net_inflow_mid || 0;
    const close = s.net_inflow_close_1h || 0;

    // 1. 高開低走（開盤大幅吸金但全日轉為淨流出）
    if (open > threshold && total < -threshold * 0.5) {
      alerts.push(`🔻 <b>${s.name} (${s.symbol})</b>：開盤首小時吸金 ${fmtMoney(open)}，但午後遭拋售轉為全日淨流出 ${fmtMoney(total)}，屬典型高開低走。`);
      return;
    }

    if (Math.abs(total) < threshold) return;

    // 2. 全日淨流入但尾盤回吐
    if (total > 0 && close < -threshold * 0.35) {
      alerts.push(`⚠️ <b>${s.name} (${s.symbol})</b>：全日淨流入 ${fmtMoney(total)}，但尾盤出現獲利回吐 (${fmtMoney(close)})，小心高位回落。`);
    }
    // 3. 全日淨流出但尾盤撈底
    else if (total < 0 && close > threshold * 0.35) {
      alerts.push(`💡 <b>${s.name} (${s.symbol})</b>：全日淨流出 ${fmtMoney(total)}，但尾盤有資金撈底 (${fmtMoney(close)})，留意短線止跌。`);
    }

    // 4. 開盤強勢吸金主導全日
    if (total > 0 && open > threshold && open > total * 0.6) {
      alerts.push(`🔥 <b>${s.name} (${s.symbol})</b>：開盤首小時已吸金 ${fmtMoney(open)}（佔全日主力），屬強勢開局。`);
    }

    // 5. 盤中資金突襲
    if (total > 0 && mid > threshold && mid > total * 0.75) {
      alerts.push(`📈 <b>${s.name} (${s.symbol})</b>：盤中時段資金大幅湧入 ${fmtMoney(mid)}，主導全日升勢。`);
    }
  });

  if (alerts.length > 0) {
    insightEl.innerHTML = alerts.map(msg => `<div class="alert-item" style="margin:3px 0;">${msg}</div>`).join('');
  } else {
    insightEl.innerHTML = `<div style="color:var(--muted);font-size:13px;">目前未發現極端資金異動（基準門檻：${fmtMoney(threshold)}），板塊表現相對平穩。</div>`;
  }
  insightEl.style.display = 'block';
}

// ================= 啟動與事件監聽 =================
document.addEventListener('DOMContentLoaded', () => {
  injectTabulatorThemeStyle();
  loadIntradayFlow();

  // 監聽主題切換，即時重繪 ECharts 配色
  const observer = new MutationObserver(() => {
    if (intradayDataStore.length > 0) renderIntradayTable();
  });
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  // 視窗尺寸改變時自動調整圖表寬度
  window.addEventListener('resize', () => {
    if (intradayChartInstance) intradayChartInstance.resize();
  });
});
