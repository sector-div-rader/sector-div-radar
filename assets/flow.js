// assets/flow.js
const FLOW_COLORS = { inflow: '#16a34a', outflow: '#dc2626' };
let currentIntradayPeriod = 'all';
let qqqCoreStore = [];
let sectorStore = [];

const chartInstances = {};
const tableInstances = {};

function isDarkMode() {
  return document.documentElement.getAttribute('data-theme') !== 'light';
}

function injectCustomStyles() {
  if (document.getElementById('flow-custom-theme')) return;
  const style = document.createElement('style');
  style.id = 'flow-custom-theme';
  style.textContent = `
    .flow-sub-title {
      font-size: 14px;
      font-weight: bold;
      color: var(--accent);
      margin: 14px 0 8px 0;
      padding-left: 8px;
      border-left: 3px solid var(--accent);
    }
    .flow-divider {
      border: 0;
      border-top: 1px dashed var(--border);
      margin: 18px 0;
    }
    .tabulator {
      background-color: var(--card);
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--text);
      font-size: 13px;
    }
    .tabulator .tabulator-header {
      background-color: var(--bg);
      color: var(--accent);
      border-bottom: 1px solid var(--border);
    }
    .tabulator .tabulator-header .tabulator-col {
      background-color: var(--bg);
      border-right: 1px solid var(--border);
    }
    .tabulator .tabulator-tableholder .tabulator-table {
      background-color: var(--card);
      color: var(--text);
    }
    .tabulator .tabulator-row {
      background-color: var(--card);
      color: var(--text);
      border-bottom: 1px solid var(--border);
    }
    .tabulator .tabulator-row.tabulator-row-even {
      background-color: rgba(128, 128, 128, 0.04);
    }
    .tabulator .tabulator-row:hover {
      background-color: rgba(88, 166, 255, 0.12) !important;
    }
    .tabulator .tabulator-cell {
      border-right: 1px solid var(--border);
    }
  `;
  document.head.appendChild(style);
}

// 自動在現有板塊區塊上方插入「QQQ & 七巨頭」雙欄容器，無需改動 build_site.py
function ensureQqqCoreContainers() {
  if (document.getElementById('qqq-core-table')) return;
  const sectorTableEl = document.getElementById('intraday-flow-table');
  if (!sectorTableEl) return;
  const sectorGrid = sectorTableEl.closest('.grid-2');
  if (!sectorGrid || !sectorGrid.parentNode) return;

  const qqqWrapper = document.createElement('div');
  qqqWrapper.id = 'qqq-core-wrapper';
  qqqWrapper.innerHTML = `
    <div class="flow-sub-title">🎯 QQQ & 七巨頭核心權重資金流</div>
    <div class="grid-2">
      <div><div id="qqq-core-table"></div></div>
      <div><div id="qqq-core-chart" style="height:290px;"></div></div>
    </div>
    <hr class="flow-divider">
    <div class="flow-sub-title">📊 11 大板塊 ETF 資金流</div>
  `;
  sectorGrid.parentNode.insertBefore(qqqWrapper, sectorGrid);
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

function renderBarChart(domId, sorted, valueField) {
  const el = document.getElementById(domId);
  if (!el) return;
  if (chartInstances[domId]) chartInstances[domId].dispose();
  const chart = echarts.init(el);
  chartInstances[domId] = chart;

  const dark = isDarkMode();
  const textColor = dark ? '#c9d1d9' : '#1f2328';
  const gridColor = dark ? '#30363d' : '#d0d7de';

  const labels = sorted.map(s => `${s.symbol} ${s.name}`).reverse();
  const values = sorted.map(s => s[valueField] ?? 0).reverse();

  chart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: dark ? '#161b22' : '#ffffff',
      borderColor: gridColor,
      textStyle: { color: textColor },
      formatter: p => `${p[0].name}<br/>淨流：<b>${fmtMoney(p[0].value)}</b>`,
    },
    grid: { left: 145, right: 75, top: 12, bottom: 26 },
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
      barWidth: '58%',
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

function renderGroupWidget(tableSelector, chartDomId, rawData, nameColTitle) {
  const fieldMap = {
    'all': 'main_net_inflow',
    'open_1h': 'net_inflow_open_1h',
    'mid': 'net_inflow_mid',
    'close_1h': 'net_inflow_close_1h',
  };
  const currentField = fieldMap[currentIntradayPeriod];
  const sorted = [...rawData].sort(
    (a, b) => (b[currentField] ?? -Infinity) - (a[currentField] ?? -Infinity)
  );

  if (tableInstances[tableSelector]) tableInstances[tableSelector].destroy();
  tableInstances[tableSelector] = new Tabulator(tableSelector, {
    data: sorted,
    layout: 'fitColumns',
    columns: [
      { title: '#', formatter: 'rownum', width: 42, hozAlign: 'center', headerSort: false },
      { title: '代號', field: 'symbol', width: 70, formatter: c => `<strong>${c.getValue()}</strong>` },
      { title: nameColTitle, field: 'name', minWidth: 85 },
      { title: '淨流', field: currentField, hozAlign: 'right', formatter: flowColorFormatter, sorter: 'number' },
    ],
  });

  renderBarChart(chartDomId, sorted, currentField);
}

function renderAllFlows() {
  if (qqqCoreStore.length > 0) {
    ensureQqqCoreContainers();
    renderGroupWidget('#qqq-core-table', 'qqq-core-chart', qqqCoreStore, '名稱');
  }
  if (sectorStore.length > 0) {
    renderGroupWidget('#intraday-flow-table', 'intraday-flow-chart', sectorStore, '板塊');
  }
}

function switchIntradayPeriod(period, btn) {
  currentIntradayPeriod = period;
  document.querySelectorAll('#intraday-controls .btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderAllFlows();
}

function detectAlertsForList(items, minFloor, groupTag) {
  const absTotals = items
    .map(s => Math.abs(s.main_net_inflow || 0))
    .filter(v => v > 0)
    .sort((a, b) => a - b);
  const medianFlow = absTotals.length > 0 ? absTotals[Math.floor(absTotals.length / 2)] : 0;
  const threshold = Math.max(minFloor, medianFlow * 1.4);

  const alerts = [];
  items.forEach(s => {
    const total = s.main_net_inflow || 0;
    const open = s.net_inflow_open_1h || 0;
    const mid = s.net_inflow_mid || 0;
    const close = s.net_inflow_close_1h || 0;
    const label = `${groupTag}<b>${s.name} (${s.symbol})</b>`;

    if (open > threshold && total < -threshold * 0.4) {
      alerts.push(`🔻 ${label}：開盤首小時吸金 ${fmtMoney(open)}，但午後轉為全日淨流出 ${fmtMoney(total)}（高開低走）。`);
      return;
    }

    if (Math.abs(total) < threshold) return;

    if (total > 0 && close < -threshold * 0.35) {
      alerts.push(`⚠️ ${label}：全日淨流入 ${fmtMoney(total)}，但尾盤出現回吐 (${fmtMoney(close)})，小心高位回落。`);
    } else if (total < 0 && close > threshold * 0.35) {
      alerts.push(`💡 ${label}：全日淨流出 ${fmtMoney(total)}，但尾盤有資金撈底 (${fmtMoney(close)})，留意短線止跌。`);
    }

    if (total > 0 && open > threshold && open > total * 0.6) {
      alerts.push(`🔥 ${label}：開盤首小時已吸金 ${fmtMoney(open)}（主導全日升勢），屬強勢開局。`);
    } else if (total > 0 && mid > threshold && mid > total * 0.75) {
      alerts.push(`📈 ${label}：盤中時段資金大幅湧入 ${fmtMoney(mid)}，帶動全日趨勢。`);
    }
  });

  return { alerts, threshold };
}

function generateSmartInsights(qqqCore, sectors) {
  const insightEl = document.getElementById('flow-insights');
  if (!insightEl) return;

  const qRes = detectAlertsForList(qqqCore, 3.0e7, '[權重] ');
  const sRes = detectAlertsForList(sectors, 1.5e7, '[板塊] ');
  const allAlerts = [...qRes.alerts, ...sRes.alerts];

  if (allAlerts.length > 0) {
    insightEl.innerHTML = allAlerts.map(msg => `<div class="alert-item" style="margin:3px 0;">${msg}</div>`).join('');
  } else {
    insightEl.innerHTML = `<div style="color:var(--muted);font-size:13px;">目前未發現極端資金異動（權重門檻 ${fmtMoney(qRes.threshold)} / 板塊門檻 ${fmtMoney(sRes.threshold)}），整體相對平穩。</div>`;
  }
  insightEl.style.display = 'block';
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

    qqqCoreStore = data.qqq_core || [];
    sectorStore = data.sectors || [];
    generateSmartInsights(qqqCoreStore, sectorStore);
    renderAllFlows();
  } catch (e) {
    document.getElementById('intraday-updated').textContent = `⚠️ 無法載入即時資金流數據：${e.message}`;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  injectCustomStyles();
  loadIntradayFlow();

  const observer = new MutationObserver(() => {
    renderAllFlows();
  });
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  window.addEventListener('resize', () => {
    Object.values(chartInstances).forEach(chart => {
      if (chart) chart.resize();
    });
  });
});
