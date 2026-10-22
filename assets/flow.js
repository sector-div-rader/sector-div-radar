// assets/flow.js
const FLOW_COLORS = { inflow: '#16a34a', outflow: '#dc2626' };
let currentIntradayPeriod = 'all';
let intradayDataStore = [];

function fmtMoney(v) {
  if (v == null || v === undefined || isNaN(v)) return '—';
  const abs = Math.abs(v), sign = v >= 0 ? '+' : '-';
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function flowColorFormatter(cell) {
  const v = cell.getValue();
  if (v == null || isNaN(v)) return '—';
  const color = v >= 0 ? FLOW_COLORS.inflow : FLOW_COLORS.outflow;
  return `<span style="color:${color};font-weight:600;">${fmtMoney(v)}</span>`;
}

let intradayChartInstance = null;
function renderIntradayChart(sorted, valueField) {
  const el = document.getElementById('intraday-flow-chart');
  if (!el) return;
  if (intradayChartInstance) intradayChartInstance.dispose();
  intradayChartInstance = echarts.init(el);
  const labels = sorted.map(s => s.name).reverse();
  const values = sorted.map(s => s[valueField] ?? 0).reverse();
  intradayChartInstance.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: p => `${p[0].name}<br/>${fmtMoney(p[0].value)}` },
    grid: { left: 100, right: 60, top: 20, bottom: 30 },
    xAxis: { type: 'value', axisLabel: { formatter: v => fmtMoney(v) } },
    yAxis: { type: 'category', data: labels, axisLabel: { fontSize: 12 } },
    series: [{ type: 'bar', data: values.map(v => ({ value: v, itemStyle: { color: v >= 0 ? FLOW_COLORS.inflow : FLOW_COLORS.outflow } })), barWidth: '60%', label: { show: true, position: 'right', formatter: p => fmtMoney(p.value), fontSize: 11 } }],
  });
}

let intradayTableInstance = null;
function renderIntradayTable() {
  const fieldMap = { 'all': 'main_net_inflow', 'open_1h': 'net_inflow_open_1h', 'mid': 'net_inflow_mid', 'close_1h': 'net_inflow_close_1h' };
  const currentField = fieldMap[currentIntradayPeriod];
  const sorted = [...intradayDataStore].sort((a, b) => (b[currentField] ?? -Infinity) - (a[currentField] ?? -Infinity));
  if (intradayTableInstance) intradayTableInstance.destroy();
  intradayTableInstance = new Tabulator('#intraday-flow-table', {
    data: sorted, layout: 'fitColumns',
    columns: [
      { title: '排名', formatter: 'rownum', width: 50, hozAlign: 'center' },
      { title: 'ETF', field: 'symbol', width: 70, formatter: c => `<strong>${c.getValue()}</strong>` },
      { title: '板塊', field: 'name', minWidth: 90 },
      { title: '淨流', field: currentField, hozAlign: 'right', formatter: flowColorFormatter, sorter: 'number' },
    ],
  });
  renderIntradayChart(sorted, currentField);
}

function switchIntradayPeriod(period, btn) {
  currentIntradayPeriod = period;
  document.querySelectorAll('.controls .btn').forEach(b => {
    if (b.getAttribute('onclick') && b.getAttribute('onclick').includes('switchIntradayPeriod')) b.classList.remove('active');
  });
  if (btn) btn.classList.add('active');
  renderIntradayTable();
}

async function loadIntradayFlow() {
  try {
    const res = await fetch('data/flow/intraday.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    document.getElementById('intraday-updated').textContent = `更新時間：${data.updated_at || '—'} · 來源：${data.note || '盤中估算'}`;
    intradayDataStore = data.sectors;
    renderIntradayTable();
  } catch (e) {
    document.getElementById('intraday-updated').textContent = `⚠️ 無法載入即時資金流數據：${e.message}`;
  }
}

document.addEventListener('DOMContentLoaded', () => { loadIntradayFlow(); });
