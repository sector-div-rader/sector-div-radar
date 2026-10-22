// assets/flow.js
const FLOW_COLORS = { inflow: '#16a34a', outflow: '#dc2626' };
let currentIntradayPeriod = 'all';
let intradayDataStore = [];
let latestDataStore = [];

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

// ================= 1. 前一日數據區塊 =================
async function loadLatestFlow() {
  try {
    const res = await fetch('data/flow/latest.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    
    document.getElementById('latest-updated').textContent =
      `數據日 ${data.as_of || '—'} · 更新 ${data.updated_at || '—'} · 來源：${data.source_note || '—'}`;

    const sorted = [...data.sectors].sort((a, b) => (b.net_flow_1d ?? -Infinity) - (a.net_flow_1d ?? -Infinity));

    new Tabulator('#latest-flow-table', {
      data: sorted,
      layout: 'fitColumns',
      columns: [
        { title: '排名', formatter: 'rownum', width: 50, hozAlign: 'center' },
        { title: 'ETF', field: 'symbol', width: 70, formatter: c => `<strong>${c.getValue()}</strong>` },
        { title: '板塊', field: 'name', minWidth: 90 },
        { title: '當日淨流', field: 'net_flow_1d', hozAlign: 'right', formatter: flowColorFormatter, sorter: 'number' },
        { title: '5日累計', field: 'net_flow_5d', hozAlign: 'right', formatter: flowColorFormatter, sorter: 'number' },
        { title: '20日累計', field: 'net_flow_20d', hozAlign: 'right', formatter: flowColorFormatter, sorter: 'number' },
      ],
    });

    const el = document.getElementById('latest-flow-chart');
    if (el) {
      const chart = echarts.init(el);
      const labels = sorted.map(s => s.name).reverse();
      const values = sorted.map(s => s.net_flow_1d ?? 0).reverse();
      chart.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: p => `${p[0].name}<br/>${fmtMoney(p[0].value)}` },
        grid: { left: 100, right: 60, top: 20, bottom: 30 },
        xAxis: { type: 'value', axisLabel: { formatter: v => fmtMoney(v) } },
        yAxis: { type: 'category', data: labels, axisLabel: { fontSize: 12 } },
        series: [{ type: 'bar', data: values.map(v => ({ value: v, itemStyle: { color: v >= 0 ? FLOW_COLORS.inflow : FLOW_COLORS.outflow } })), barWidth: '60%', label: { show: true, position: 'right', formatter: p => fmtMoney(p.value), fontSize: 11 } }],
      });
      window.addEventListener('resize', () => chart.resize());
    }
  } catch (e) {
    document.getElementById('latest-updated').textContent = `⚠️ 無法載入前一日資金流數據：${e.message}`;
  }
}

// ================= 2. 即時數據區塊 =================
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
    generateSmartInsights(intradayDataStore);
    renderIntradayTable();
  } catch (e) {
    document.getElementById('intraday-updated').textContent = `⚠️ 無法載入即時資金流數據：${e.message}`;
  }
}

// ================= 3. 智能提示區塊 =================
function generateSmartInsights(data) {
  let alerts = [];
  
  data.forEach(s => {
    const total = s.main_net_inflow || 0;
    const open = s.net_inflow_open_1h || 0;
    const mid = s.net_inflow_mid || 0;
    const close = s.net_inflow_close_1h || 0;
    
    // 門檻：只理會超過 10 億美元嘅資金流動
    const threshold = 1e9; 
    
    if (Math.abs(total) < threshold) return;

    // 規則 1：尾盤大逆轉
    if (total > 0 && close < -threshold * 0.3) {
      alerts.push(`⚠️ <b>${s.name}</b>：全日淨流入，但尾盤出現大幅獲利回吐 (尾盤流出 ${fmtMoney(close)})，小心高位回落。`);
    } else if (total < 0 && close > threshold * 0.3) {
      alerts.push(`💡 <b>${s.name}</b>：全日淨流出，但尾盤有資金撈底 (尾盤流入 ${fmtMoney(close)})，可能見底。`);
    }
    
    // 規則 2：開盤爆量
    if (open > threshold && open > total * 0.6) {
      alerts.push(`🔥 <b>${s.name}</b>：開盤首小時已吸金 ${fmtMoney(open)}，佔全日極大比例，屬強勢開局。`);
    }

    // 規則 3：盤中突然發力
    if (mid > threshold && mid > Math.abs(total) * 0.8) {
      alerts.push(`📈 <b>${s.name}</b>：盤中時段資金突然大幅湧入 (${fmtMoney(mid)})，帶動全日趨勢。`);
    }
  });

  const insightEl = document.getElementById('flow-insights');
  if (!insightEl) return;

  if (alerts.length > 0) {
    insightEl.innerHTML = alerts.map(msg => `<div class="alert-item">${msg}</div>`).join('');
    insightEl.style.display = 'block';
  } else {
    insightEl.innerHTML = `<div style="color:var(--muted);font-size:13px;">目前未發現極端資金異動，板塊表現相對平穩。</div>`;
    insightEl.style.display = 'block';
  }
}

// ================= 啟動 =================
document.addEventListener('DOMContentLoaded', () => {
  loadLatestFlow();
  loadIntradayFlow();
});
