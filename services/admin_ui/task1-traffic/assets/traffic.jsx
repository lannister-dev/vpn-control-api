// Traffic page — stacked area chart, KPIs, per-region, top talkers, top nodes
const { useState, useEffect, useMemo, useRef } = React;

// ─── Helpers ───
function fmtBytes(b, digits = 1) {
  if (!b && b !== 0) return '—';
  const u = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let i = 0, n = b;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return n.toFixed(n >= 100 ? 0 : digits) + ' ' + u[i];
}
function fmtBitsRate(bytesPerSec) {
  const bps = bytesPerSec * 8;
  const u = ['bps', 'Kbps', 'Mbps', 'Gbps', 'Tbps'];
  let i = 0, n = bps;
  while (n >= 1000 && i < u.length - 1) { n /= 1000; i++; }
  return n.toFixed(n >= 100 ? 0 : 1) + ' ' + u[i];
}
function fmtNum(n) {
  return new Intl.NumberFormat('ru-RU').format(Math.round(n));
}
function fmtTime(t, period) {
  const d = new Date(t);
  if (period === '1h' || period === '24h') {
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' });
}

// ─── Region colors (deterministic, theme-friendly) ───
const REGION_COLORS = {
  'EU-Central':    'oklch(0.66 0.16 260)',
  'EU-West':       'oklch(0.70 0.16 200)',
  'EU-North':      'oklch(0.72 0.14 160)',
  'US-East':       'oklch(0.72 0.16 30)',
  'US-West':       'oklch(0.72 0.17 350)',
  'AP-South':      'oklch(0.78 0.15 90)',
  'AP-East':       'oklch(0.76 0.14 130)',
  'ME':            'oklch(0.74 0.15 60)',
};
function regionColor(r, i = 0) {
  if (REGION_COLORS[r]) return REGION_COLORS[r];
  const hues = [260, 200, 160, 30, 350, 90, 130, 60, 310, 240];
  return `oklch(0.72 0.15 ${hues[i % hues.length]})`;
}

// ─── Period toggle ───
function PeriodToggle({ value, onChange }) {
  const opts = [
    { id: '1h',  label: '1 ч' },
    { id: '24h', label: '24 ч' },
    { id: '7d',  label: '7 дн' },
    { id: '30d', label: '30 дн' },
  ];
  return (
    <div className="tf-period">
      {opts.map(o => (
        <button key={o.id}
          className="tf-period-btn"
          data-active={value === o.id}
          onClick={() => onChange(o.id)}>{o.label}</button>
      ))}
    </div>
  );
}

// ─── KPI hero ───
function KpiDelta({ pct }) {
  const tone = pct > 1 ? 'up' : pct < -1 ? 'down' : 'flat';
  const arrow = tone === 'up' ? '↑' : tone === 'down' ? '↓' : '→';
  return <div className={`kpi-delta ${tone}`}>{arrow} {Math.abs(pct).toFixed(1)}% vs prev</div>;
}

function TrafficKpis({ agg, period }) {
  return (
    <div className="kpi-hero">
      <div className="kpi-cell primary">
        <div className="kpi-label"><span>Совокупный трафик</span><span className="pill accent" style={{padding:'1px 6px',fontSize:10}}>{period}</span></div>
        <div className="kpi-value-row">
          <div className="kpi-value">{fmtBytes(agg.totalBytes, 2)}<span className="kpi-unit">за период</span></div>
          <Spark data={agg.sparkTotal} color="var(--accent)" w={120} h={34} />
        </div>
        <KpiDelta pct={agg.deltaPct} />
      </div>
      <div className="kpi-cell">
        <div className="kpi-label"><span>Входящий</span></div>
        <div className="kpi-value">{fmtBytes(agg.bytesIn, 1)}</div>
        <div className="kpi-delta flat">↓ из клиентов</div>
      </div>
      <div className="kpi-cell">
        <div className="kpi-label"><span>Исходящий</span></div>
        <div className="kpi-value">{fmtBytes(agg.bytesOut, 1)}</div>
        <div className="kpi-delta flat">↑ в клиенты</div>
      </div>
      <div className="kpi-cell">
        <div className="kpi-label"><span>Пик пропускной</span></div>
        <div className="kpi-value">{fmtBitsRate(agg.peakRate)}</div>
        <div className="kpi-delta flat">{fmtTime(agg.peakT, period)}</div>
      </div>
      <div className="kpi-cell">
        <div className="kpi-label"><span>Активные сессии</span></div>
        <div className="kpi-value">{fmtNum(agg.activeSessions)}</div>
        <div className="kpi-delta up">↑ {agg.sessionDelta}% за час</div>
      </div>
    </div>
  );
}

// ─── Stacked area chart ───
function StackedAreaChart({ timeseries, period, focusRegion, onFocusRegion }) {
  const { regions, series } = timeseries;
  const wrapRef = useRef(null);
  const [hover, setHover] = useState(null); // { i, x, y, t, values }
  const [size, setSize] = useState({ w: 900, h: 280 });

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        const cr = e.contentRect;
        setSize({ w: Math.max(400, cr.width), h: 280 });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const pad = { t: 16, r: 12, b: 28, l: 56 };
  const W = size.w, H = size.h;
  const innerW = W - pad.l - pad.r;
  const innerH = H - pad.t - pad.b;

  // Build stacked values per bucket
  const stacks = useMemo(() => series.map(pt => {
    let cum = 0;
    const layers = regions.map(r => {
      const v = pt.byRegion[r] || 0;
      const layer = { region: r, y0: cum, y1: cum + v, v };
      cum += v;
      return layer;
    });
    return { t: pt.t, total: cum, layers };
  }), [series, regions]);

  const maxY = Math.max(...stacks.map(s => s.total)) * 1.08;
  const xAt = i => pad.l + (i / (stacks.length - 1)) * innerW;
  const yAt = v => pad.t + innerH - (v / maxY) * innerH;

  // Build path per region
  const regionPaths = regions.map((r, ri) => {
    const top = stacks.map((s, i) => [xAt(i), yAt(s.layers[ri].y1)]);
    const bot = stacks.map((s, i) => [xAt(i), yAt(s.layers[ri].y0)]).reverse();
    const pts = [...top, ...bot];
    return 'M' + pts.map(p => p.map(n => n.toFixed(1)).join(',')).join('L') + 'Z';
  });

  // Y-grid ticks
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(f => ({
    y: yAt(maxY * f),
    label: fmtBitsRate(maxY * f),
  }));

  // X-axis labels (show ~6)
  const xTicks = useMemo(() => {
    const n = stacks.length;
    const count = Math.min(6, n);
    const step = Math.max(1, Math.floor(n / count));
    const arr = [];
    for (let i = 0; i < n; i += step) arr.push({ i, t: stacks[i].t });
    if (arr[arr.length - 1].i !== n - 1) arr.push({ i: n - 1, t: stacks[n - 1].t });
    return arr;
  }, [stacks]);

  const onMove = e => {
    const rect = wrapRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const rel = (x - pad.l) / innerW;
    const i = Math.max(0, Math.min(stacks.length - 1, Math.round(rel * (stacks.length - 1))));
    setHover({ i, stack: stacks[i] });
  };

  const hoverX = hover ? xAt(hover.i) : 0;

  return (
    <div className="tf-chart" ref={wrapRef}
      onMouseMove={onMove}
      onMouseLeave={() => setHover(null)}>
      <svg width={W} height={H} style={{ display: 'block' }}>
        <defs>
          {regions.map((r, i) => (
            <linearGradient key={r} id={`tf-grad-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor={regionColor(r, i)} stopOpacity="0.85" />
              <stop offset="100%" stopColor={regionColor(r, i)} stopOpacity="0.55" />
            </linearGradient>
          ))}
        </defs>
        {/* y-grid */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={pad.l} x2={W - pad.r} y1={t.y} y2={t.y}
              stroke="var(--border)" strokeDasharray={i === 0 ? '0' : '3 3'} />
            <text x={pad.l - 8} y={t.y + 3} textAnchor="end"
              fontSize="10.5" fill="var(--text-muted)" fontFamily="var(--font-mono)">{t.label}</text>
          </g>
        ))}
        {/* x-axis labels */}
        {xTicks.map((t, i) => (
          <text key={i} x={xAt(t.i)} y={H - 10} textAnchor="middle"
            fontSize="10.5" fill="var(--text-muted)" fontFamily="var(--font-mono)">
            {fmtTime(t.t, period)}
          </text>
        ))}
        {/* stacked areas */}
        {regions.map((r, i) => {
          const dim = focusRegion && focusRegion !== r;
          return (
            <path key={r} d={regionPaths[i]}
              fill={`url(#tf-grad-${i})`}
              stroke={regionColor(r, i)} strokeWidth="1"
              opacity={dim ? 0.15 : 1}
              style={{ transition: 'opacity 150ms ease', cursor: 'pointer' }}
              onClick={() => onFocusRegion(focusRegion === r ? null : r)} />
          );
        })}
        {/* hover crosshair */}
        {hover && (
          <g>
            <line x1={hoverX} x2={hoverX} y1={pad.t} y2={H - pad.b}
              stroke="var(--text)" strokeWidth="1" opacity="0.3" />
            <circle cx={hoverX} cy={yAt(hover.stack.total)} r="3.5"
              fill="var(--bg)" stroke="var(--text)" strokeWidth="1.5" />
          </g>
        )}
      </svg>
      {hover && (
        <div className="tf-tooltip" style={{
          left: Math.min(hoverX + 12, W - 220),
          top: 8,
        }}>
          <div className="tf-tip-time">{fmtTime(hover.stack.t, period)}</div>
          <div className="tf-tip-total">{fmtBitsRate(hover.stack.total)}</div>
          <div className="tf-tip-list">
            {hover.stack.layers.slice().reverse().map((l, i) => (
              <div key={l.region} className="tf-tip-row">
                <span className="tf-tip-swatch" style={{ background: regionColor(l.region, regions.indexOf(l.region)) }} />
                <span className="tf-tip-region">{l.region}</span>
                <span className="tf-tip-val mono">{fmtBitsRate(l.v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Region breakdown (horizontal stacked bar + legend/list) ───
function RegionBreakdown({ byRegion, total, focusRegion, onFocusRegion, regions }) {
  const sorted = regions.map(r => ({ region: r, v: byRegion[r] || 0 }))
    .sort((a, b) => b.v - a.v);
  return (
    <div className="tf-region-block">
      <div className="tf-region-bar">
        {sorted.map((s, i) => {
          const pct = total ? (s.v / total) * 100 : 0;
          return (
            <div key={s.region}
              className="tf-region-seg"
              data-focus={focusRegion === s.region}
              data-dim={focusRegion && focusRegion !== s.region}
              style={{ width: pct + '%', background: regionColor(s.region, regions.indexOf(s.region)) }}
              onClick={() => onFocusRegion(focusRegion === s.region ? null : s.region)}
              title={`${s.region} — ${pct.toFixed(1)}%`}>
              {pct > 8 && <span>{pct.toFixed(0)}%</span>}
            </div>
          );
        })}
      </div>
      <div className="tf-region-list">
        {sorted.map(s => {
          const pct = total ? (s.v / total) * 100 : 0;
          return (
            <div key={s.region} className="tf-region-row"
              data-focus={focusRegion === s.region}
              data-dim={focusRegion && focusRegion !== s.region}
              onClick={() => onFocusRegion(focusRegion === s.region ? null : s.region)}>
              <span className="tf-region-swatch" style={{ background: regionColor(s.region, regions.indexOf(s.region)) }} />
              <span className="tf-region-name">{s.region}</span>
              <span className="tf-region-pct mono">{pct.toFixed(1)}%</span>
              <span className="tf-region-val mono">{fmtBytes(s.v)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Top talkers (users) ───
function TopUsers({ users }) {
  const max = Math.max(...users.map(u => u.bytes));
  return (
    <table className="tbl tf-tbl">
      <thead>
        <tr>
          <th style={{width: 28}}>#</th>
          <th>Пользователь</th>
          <th>Тариф</th>
          <th style={{width: 220}}>Трафик</th>
          <th className="tbl-num" style={{width: 90}}>Сессии</th>
          <th className="tbl-num" style={{width: 90}}>Устройства</th>
        </tr>
      </thead>
      <tbody>
        {users.map((u, i) => (
          <tr key={u.uuid}>
            <td className="mono" style={{color: 'var(--text-muted)'}}>{i + 1}</td>
            <td>
              <div className="tf-user">
                <div className="tf-user-avatar">{u.tg.slice(1, 3).toUpperCase()}</div>
                <div>
                  <div className="tf-user-tg">{u.tg}</div>
                  <div className="tf-user-uuid mono">{u.uuid}</div>
                </div>
              </div>
            </td>
            <td><span className={`pill ${u.plan === 'Pro' ? 'accent' : u.plan === 'Plus' ? 'info' : ''}`}>{u.plan}</span></td>
            <td>
              <div className="tf-bar-cell">
                <div className="tf-bar-bg">
                  <div className="tf-bar-fill" style={{ width: ((u.bytes / max) * 100) + '%' }} />
                </div>
                <div className="tf-bar-val mono">{fmtBytes(u.bytes)}</div>
              </div>
            </td>
            <td className="tbl-num">{u.sessions}</td>
            <td className="tbl-num">{u.devices}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ─── Top nodes ───
function TopNodes({ nodes, onSelect }) {
  const max = Math.max(...nodes.map(n => n.bytes_in + n.bytes_out));
  return (
    <table className="tbl tf-tbl">
      <thead>
        <tr>
          <th>Узел</th>
          <th>Регион</th>
          <th>Роль</th>
          <th style={{width: 200}}>Трафик (in+out)</th>
          <th className="tbl-num">Сессии</th>
          <th style={{width: 96}}>Тренд</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {nodes.map(n => {
          const total = n.bytes_in + n.bytes_out;
          const spark = MOCK.spark(n.node_id.charCodeAt(3) * 9 + 11, 24, 50, 22);
          return (
            <tr key={n.node_id}>
              <td>
                <div className="tf-node">
                  <span className={`status-dot ${n.health === 'healthy' ? 'ok' : n.health === 'degraded' ? 'warn' : 'bad'}`} />
                  <span style={{fontWeight: 500}}>{n.node_name}</span>
                </div>
              </td>
              <td>
                <span className="tf-region-inline">
                  <span className="tf-region-swatch" style={{ background: regionColor(n.region) }} />
                  {n.region}
                </span>
              </td>
              <td><span className="pill">{n.role}</span></td>
              <td>
                <div className="tf-bar-cell">
                  <div className="tf-bar-bg tf-bar-split">
                    <div className="tf-bar-in" style={{ width: ((n.bytes_in / max) * 100) + '%' }} />
                    <div className="tf-bar-out" style={{ width: ((n.bytes_out / max) * 100) + '%' }} />
                  </div>
                  <div className="tf-bar-val mono">{fmtBytes(total)}</div>
                </div>
              </td>
              <td className="tbl-num">{fmtNum(n.sessions)}</td>
              <td><Spark data={spark} color="var(--accent)" w={80} h={22} /></td>
              <td className="row-actions">
                <button className="btn btn-xs" onClick={() => onSelect(n)}>Detail →</button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// ─── Page ───
function TrafficPage() {
  const [period, setPeriod] = useState(() => localStorage.getItem('tf.period') || '24h');
  const [focusRegion, setFocusRegion] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);

  useEffect(() => { localStorage.setItem('tf.period', period); }, [period]);

  const timeseries = useMemo(() => MOCK.trafficTimeseries(period), [period]);
  const byNode = useMemo(() => MOCK.trafficByPeriod(period), [period]);
  const users = useMemo(() => MOCK.trafficTopUsers(10), []);

  // Aggregates
  const agg = useMemo(() => {
    const bytesIn  = byNode.reduce((a, n) => a + n.bytes_in, 0);
    const bytesOut = byNode.reduce((a, n) => a + n.bytes_out, 0);
    const total = bytesIn + bytesOut;
    const sessions = byNode.reduce((a, n) => a + n.sessions, 0);
    const peakPoint = timeseries.series.reduce((best, p) => {
      const sum = Object.values(p.byRegion).reduce((a, b) => a + b, 0);
      return sum > best.sum ? { sum, t: p.t } : best;
    }, { sum: 0, t: timeseries.series[0].t });
    const sparkTotal = timeseries.series.map(p => Object.values(p.byRegion).reduce((a, b) => a + b, 0));
    return {
      totalBytes: total, bytesIn, bytesOut,
      peakRate: peakPoint.sum, peakT: peakPoint.t,
      activeSessions: sessions,
      sessionDelta: 4.2,
      sparkTotal,
      deltaPct: 6.8,
    };
  }, [byNode, timeseries]);

  // Region aggregates (by total bytes)
  const regionTotals = useMemo(() => {
    const agg = {};
    byNode.forEach(n => {
      agg[n.region] = (agg[n.region] || 0) + n.bytes_in + n.bytes_out;
    });
    return agg;
  }, [byNode]);

  // Filter nodes by focused region for "top nodes" table
  const topNodes = useMemo(() => {
    const list = focusRegion ? byNode.filter(n => n.region === focusRegion) : byNode;
    return list.sort((a, b) => (b.bytes_in + b.bytes_out) - (a.bytes_in + a.bytes_out)).slice(0, 12);
  }, [byNode, focusRegion]);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Трафик</h1>
          <div className="page-subtitle">Агрегированный трафик по узлам, регионам и пользователям · окно: {period}</div>
        </div>
        <div className="page-head-actions">
          <PeriodToggle value={period} onChange={setPeriod} />
          <button className="btn"><Icon k="download" /> Экспорт</button>
        </div>
      </div>

      <div className="sec">
        <TrafficKpis agg={agg} period={period} />
      </div>

      <div className="sec">
        <div className="card">
          <div className="card-head">
            <div className="sec-title">Пропускная способность</div>
            <div className="sec-sub">{focusRegion ? `фокус: ${focusRegion}` : 'стек по регионам'}</div>
            <div className="sec-spacer" />
            <div className="tf-legend">
              {timeseries.regions.map((r, i) => (
                <button key={r}
                  className="tf-legend-item"
                  data-active={!focusRegion || focusRegion === r}
                  onClick={() => setFocusRegion(focusRegion === r ? null : r)}>
                  <span className="tf-legend-sw" style={{ background: regionColor(r, i) }} />
                  {r}
                </button>
              ))}
            </div>
          </div>
          <div className="card-body" style={{ padding: 8 }}>
            <StackedAreaChart timeseries={timeseries} period={period}
              focusRegion={focusRegion} onFocusRegion={setFocusRegion} />
          </div>
        </div>
      </div>

      <div className="sec">
        <div className="card">
          <div className="card-head">
            <div className="sec-title">Распределение по регионам</div>
            <div className="sec-sub">{fmtBytes(agg.totalBytes)} за период</div>
          </div>
          <div className="card-body">
            <RegionBreakdown
              byRegion={regionTotals}
              total={Object.values(regionTotals).reduce((a, b) => a + b, 0)}
              regions={timeseries.regions}
              focusRegion={focusRegion}
              onFocusRegion={setFocusRegion} />
          </div>
        </div>
      </div>

      <div className="split-2">
        <div className="card">
          <div className="card-head">
            <div className="sec-title">Топ узлов</div>
            <div className="sec-sub">{focusRegion ? `регион ${focusRegion}` : 'по всему кластеру'}</div>
            <div className="sec-spacer" />
            <span className="pill">
              <span className="tf-bar-swatch in" /> in &nbsp;
              <span className="tf-bar-swatch out" /> out
            </span>
          </div>
          <TopNodes nodes={topNodes} onSelect={setSelectedNode} />
        </div>
        <div className="card">
          <div className="card-head">
            <div className="sec-title">Топ пользователей</div>
            <div className="sec-sub">по суммарному трафику</div>
            <div className="sec-spacer" />
            <button className="btn btn-xs">Все пользователи →</button>
          </div>
          <TopUsers users={users} />
        </div>
      </div>

      {selectedNode && (
        <NodeSlideover
          node={MOCK.NODES.find(n => n.id === selectedNode.node_id)}
          onClose={() => setSelectedNode(null)} />
      )}

      <div style={{ height: 40 }} />
    </div>
  );
}

window.TrafficPage = TrafficPage;
