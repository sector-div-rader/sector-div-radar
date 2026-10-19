// assets/flow.js
const FLOW_COLORS = { inflow: '#16a34a', outflow: '#dc2626' };

function fmtMoney(v) {
  if (v == null || v === undefined) return '—';
  const abs = Math.abs(v), sign = v >= 0 ? '+' : '-';
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function flowColorFormatter(cell) {
  const v = cell.getValue();
  if (v == null) return '—';
  const color = v >= 0 ? FLOW_COLORS.inflow : FLOW_COLORS.outflow;
  return `<span style="color:${color};font-weight:600;">${fmtMoney(v)}</span>`;
}

async function loadSectorFlow() {
  let data;
  try {
    const res = await fetch('data/flow/latest.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (e) {
    document.getElementById('flow-updated').textContent =
      `⚠️ 無法載入資金流數據：${e.message}`;
    return;
  }

  document.getElementById('flow-updated').textContent =
    `數據日 ${data.as_of} · 更新 ${data.updated_at} · 來源：${data.source_note}`;

  const sorted = [...data.sectors].sort(
    (a, b) => (b.net_flow_1d ?? -Infinity) - (a.net_flow_1d ?? -Infinity)
  );

  // ── Tabulator 表格 ──
  new Tabulator('#flow-table', {
    data: sorted,
    layout: 'fitColumns',
    responsiveLayout: 'collapse',
    initialSort: [{ column: 'net_flow_1d', dir: 'desc' }],
    columns: [
      { title: '排名', formatter: 'rownum', width: 60, hozAlign: 'center' },
      {
        title: 'ETF', field: 'symbol', width: 90,
        formatter: c => `<strong>${c.getValue()}</strong>`,
      },
      { title: '板塊', field: 'name', minWidth: 120 },
      {
        title: '當日淨流', field: 'net_flow_1d', hozAlign: 'right',
        formatter: flowColorFormatter, sorter: 'number',
      },
      {
        title: '5日累計', field: 'net_flow_5d', hozAlign: 'right',
        formatter: flowColorFormatter, sorter: 'number',
      },
      {
        title: '20日累計', field: 'net_flow_20d', hozAlign: 'right',
        formatter: flowColorFormatter, sorter: 'number',
      },
      {
        title: '相對SPY', field: 'rs_vs_spy', hozAlign: 'right',
        formatter: flowColorFormatter, sorter: 'number',
      },
      {
        title: '數據', field: 'source', width: 100, hozAlign: 'center',
        formatter: c =>
          c.getValue() === 'eulerpool'
            ? '<span style="color:#2563eb;">🅴 機構</span>'
            : '<span style="color:#9ca3af;">🅿 代理</span>',
      },
    ],
  });

  // ── ECharts 水平柱狀圖 ──
  const chart = echarts.init(document.getElementById('flow-chart'));
  const labels = sorted.map(s => s.name).reverse();
  const values = sorted.map(s => s.net_flow_1d ?? 0).reverse();

  chart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: p => `${p[0].name}<br/>${fmtMoney(p[0].value)}`,
    },
    grid: { left: 100, right: 60, top: 20, bottom: 30 },
    xAxis: { type: 'value', axisLabel: { formatter: v => fmtMoney(v) } },
    yAxis: { type: 'category', data: labels, axisLabel: { fontSize: 12 } },
    series: [
      {
        type: 'bar',
        data: values.map(v => ({
          value: v,
          itemStyle: {
            color: v >= 0 ? FLOW_COLORS.inflow : FLOW_COLORS.outflow,
          },
        })),
        barWidth: '60%',
        label: {
          show: true,
          position: 'right',
          formatter: p => fmtMoney(p.value),
          fontSize: 11,
        },
      },
    ],
  });

  window.addEventListener('resize', () => chart.resize());
}

loadSectorFlow();
