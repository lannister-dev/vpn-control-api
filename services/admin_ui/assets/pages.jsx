// Pages — Overview (Dashboard), Nodes, Routes (topology-inclusive)

// ─── Overview ───
function OverviewPage({ onOpenNode, onGoto }) {
  const healthy = MOCK.NODES.filter(n => n.health === 'ok').length;
  const total = MOCK.NODES.length;
  const healthPct = Math.round((healthy / total) * 100);
  const ringLen = 2 * Math.PI * 28;
  const dash = ringLen * (healthPct / 100);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Fleet overview</h1>
          <div className="page-subtitle">Сводка по инфраструктуре и бизнесу · последние 24 часа</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost"><Icon name="download" size={13} /> Экспорт</button>
          <button className="btn"><Icon name="clock" size={13} /> 24 часа <Icon name="chevron-down" size={12} /></button>
          <button className="btn btn-primary"><Icon name="plus" size={13} /> Действие</button>
        </div>
      </div>

      {/* Hero KPI — 1 primary + 4 secondary */}
      <div className="sec">
        <div className="kpi-hero">
          <div className="kpi-cell primary">
            <div className="kpi-label"><Icon name="shield-check" size={12} /> Здоровье флота</div>
            <div className="health-ring">
              <svg className="ring-svg" viewBox="0 0 64 64">
                <circle className="ring-bg" cx="32" cy="32" r="28" fill="none" strokeWidth="5" />
                <circle className={`ring-fg ${healthPct < 70 ? 'bad' : healthPct < 90 ? 'warn' : ''}`} cx="32" cy="32" r="28" fill="none" strokeWidth="5"
                  strokeDasharray={`${dash} ${ringLen}`} transform="rotate(-90 32 32)" strokeLinecap="round" />
              </svg>
              <div className="health-main">
                <div className="kpi-value tnum">{healthPct}<span className="kpi-unit">%</span></div>
                <div className="health-sub">
                  <span><span className="status-dot ok"></span> {healthy} healthy</span>
                  <span><span className="status-dot warn"></span> 2 degraded</span>
                  <span><span className="status-dot bad"></span> 1 down</span>
                </div>
              </div>
            </div>
          </div>

          <KpiCell label="Активные подписки" value="2,847" delta="+34" deltaTone="up" icon="key" sparkSeed={13} sparkColor="var(--accent)" />
          <KpiCell label="Трафик сегодня" value="14.2" unit="TB" delta="+8.2%" deltaTone="up" icon="activity" sparkSeed={42} sparkColor="var(--ok)" />
          <KpiCell label="Средняя latency" value="28" unit="ms" delta="+4ms" deltaTone="down" icon="zap" sparkSeed={91} sparkColor="var(--warn)" />
          <KpiCell label="Probe success" value="98.4" unit="%" delta="−0.2%" deltaTone="down" icon="radar" sparkSeed={27} sparkColor="var(--info)" />
        </div>
      </div>

      {/* Two columns: Issues + Activity */}
      <div className="sec split-2">
        <div className="card">
          <div className="card-head">
            <Icon name="alert-triangle" size={14} style={{color: 'var(--warn)'}} />
            <div className="sec-title">Требуют внимания</div>
            <span className="pill warn">{MOCK.ISSUES.length}</span>
            <div className="sec-spacer"></div>
            <button className="btn btn-ghost btn-xs">Все инциденты <Icon name="arrow-up-right" size={11} /></button>
          </div>
          <div>
            {MOCK.ISSUES.map((is, i) => (
              <div key={i} className="issue" onClick={() => {
                if (is.kind === 'node') { const n = MOCK.NODES.find(n => n.id === is.target); if (n) onOpenNode(n); }
                else if (is.kind === 'route') onGoto('routes');
                else if (is.kind === 'subs') onGoto('subscriptions');
                else if (is.kind === 'transport') onGoto('transport');
              }}>
                <div className={`issue-icon ${is.severity}`}>
                  <Icon name={is.severity === 'bad' ? 'alert-circle' : is.severity === 'warn' ? 'alert-triangle' : 'info'} size={14} />
                </div>
                <div className="issue-main">
                  <div className="issue-title">{is.title}</div>
                  <div className="issue-sub">{is.sub}</div>
                </div>
                <div className="issue-time">{is.time}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <Icon name="activity" size={14} />
            <div className="sec-title">Последняя активность</div>
            <div className="sec-spacer"></div>
            <button className="btn btn-ghost btn-xs">Полный аудит <Icon name="arrow-up-right" size={11} /></button>
          </div>
          <div>
            {MOCK.ACTIVITY.map((a, i) => (
              <div key={i} className="activity">
                <div className={`activity-dot ${a.tone}`}></div>
                <div className="activity-main">
                  <div className="activity-text">{a.text}</div>
                  <div className="activity-meta">{a.meta}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Regions breakdown */}
      <div className="sec">
        <div className="sec-head">
          <div className="sec-title">Регионы</div>
          <div className="sec-sub">Нагрузка и трафик по зонам</div>
          <div className="sec-spacer"></div>
          <button className="btn btn-ghost btn-xs" onClick={() => onGoto('zones')}>Все зоны <Icon name="arrow-up-right" size={11} /></button>
        </div>
        <div className="card">
          <table className="tbl">
            <thead>
              <tr>
                <th>Зона</th><th>Серверов</th><th>Здоровье</th><th>Средняя нагрузка</th><th style={{textAlign: 'right'}}>Трафик 24h</th><th style={{textAlign: 'right'}}>Активные ключи</th><th style={{width: 120}}>Тренд</th>
              </tr>
            </thead>
            <tbody>
              {[
                {zone: '🇩🇪 eu-central · Frankfurt', cnt: 2, h: [2,0,0], load: 0.52, tf: '2.0 TB', keys: 842, seed: 11, tone: 'ok'},
                {zone: '🇳🇱 eu-west · Amsterdam', cnt: 2, h: [1,1,0], load: 0.72, tf: '5.5 TB', keys: 1204, seed: 23, tone: 'warn'},
                {zone: '🇸🇬 ap-southeast · Singapore', cnt: 2, h: [1,0,1], load: 0.23, tf: '850 GB', keys: 287, seed: 71, tone: 'bad'},
                {zone: '🇺🇸 us-east · New York', cnt: 2, h: [2,0,0], load: 0.65, tf: '4.5 TB', keys: 918, seed: 33, tone: 'ok'},
                {zone: '🇺🇸 us-west · Los Angeles', cnt: 1, h: [0,1,0], load: 0.81, tf: '1.4 TB', keys: 396, seed: 55, tone: 'warn'},
              ].map((r, i) => (
                <tr key={i}>
                  <td style={{fontWeight: 500}}>{r.zone}</td>
                  <td className="tbl-num">{r.cnt}</td>
                  <td>
                    <div style={{display: 'flex', gap: 4}}>
                      {r.h[0] > 0 && <span className="pill ok" style={{padding: '0 6px'}}>{r.h[0]}</span>}
                      {r.h[1] > 0 && <span className="pill warn" style={{padding: '0 6px'}}>{r.h[1]}</span>}
                      {r.h[2] > 0 && <span className="pill bad" style={{padding: '0 6px'}}>{r.h[2]}</span>}
                    </div>
                  </td>
                  <td><LoadBar v={r.load} /></td>
                  <td className="tbl-num">{r.tf}</td>
                  <td className="tbl-num">{r.keys}</td>
                  <td>
                    <Spark data={MOCK.spark(r.seed, 24, 50, 25)} color={`var(--${r.tone})`} w={100} h={24} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="sec" style={{paddingBottom: 40}}>
        <div className="sec-head">
          <div className="sec-title">Быстрые действия</div>
          <div className="sec-sub">Из командной палитры ⌘K или отсюда</div>
        </div>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10}}>
          {[
            { i: 'server', l: 'Добавить сервер', s: 'Новая нода и первичная конфигурация' },
            { i: 'route', l: 'Создать маршрут', s: 'Entry → Backend связка с весом' },
            { i: 'arrow-right', l: 'Мигрировать плейсменты', s: 'Перенести нагрузку между нодами' },
            { i: 'shield-check', l: 'Probe-политика', s: 'Dry run или применить' },
          ].map((a, i) => (
            <button key={i} className="card" style={{textAlign: 'left', border: '1px solid var(--border)', padding: 14, cursor: 'pointer', background: 'var(--surface)'}}>
              <Icon name={a.i} size={16} style={{color: 'var(--accent)', marginBottom: 8}} />
              <div style={{fontWeight: 500, fontSize: 13}}>{a.l}</div>
              <div className="muted text-xs mt-1">{a.s}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function KpiCell({ label, value, unit, delta, deltaTone, icon, sparkSeed, sparkColor }) {
  return (
    <div className="kpi-cell">
      <div className="kpi-label"><Icon name={icon} size={12} style={{flexShrink: 0}} /> <span>{label}</span></div>
      <div className="kpi-value-row">
        <div className="kpi-value tnum">{value}{unit && <span className="kpi-unit">{unit}</span>}</div>
        <div className="kpi-spark"><Spark data={MOCK.spark(sparkSeed, 22, 50, 25)} color={sparkColor} w={54} h={20} /></div>
      </div>
      <div className={`kpi-delta ${deltaTone}`}>
        <Icon name={deltaTone === 'up' ? 'trending-up' : deltaTone === 'down' ? 'trending-down' : 'arrow-right'} size={12} />
        <span>{delta}</span>
        <span className="muted" style={{marginLeft: 4}}>vs вчера</span>
      </div>
    </div>
  );
}

// ─── Nodes ───
function NodesPage({ onOpenNode }) {
  const [filter, setFilter] = useState('');
  const [health, setHealth] = useState('');
  const list = MOCK.NODES.filter(n => {
    if (filter && !(n.name + n.id + n.region).toLowerCase().includes(filter.toLowerCase())) return false;
    if (health && n.health !== health) return false;
    return true;
  });
  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Серверы</h1>
          <div className="page-subtitle">{MOCK.NODES.length} нод · 7 активных · 1 в draining</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost"><Icon name="filter" size={13} /> Фильтры</button>
          <button className="btn"><Icon name="download" size={13} /> Экспорт</button>
          <button className="btn btn-primary"><Icon name="plus" size={13} /> Добавить сервер</button>
        </div>
      </div>
      <div className="filterbar">
        <div className="input-search-wrap">
          <Icon name="search" size={13} className="input-search-icon" />
          <input className="input" placeholder="Имя, UUID, домен, IP…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
        <select className="select" value={health} onChange={(e) => setHealth(e.target.value)}>
          <option value="">Любое здоровье</option>
          <option value="ok">Healthy</option>
          <option value="warn">Degraded</option>
          <option value="bad">Down</option>
        </select>
        <select className="select"><option>Любая роль</option><option>Entry</option><option>Backend</option></select>
        <select className="select"><option>Все регионы</option></select>
        <div style={{marginLeft: 'auto', display: 'flex', gap: 4}}>
          <span className="muted text-xs">{list.length} / {MOCK.NODES.length}</span>
        </div>
      </div>
      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              <th>Сервер</th><th>Регион</th><th>Роль</th><th>Статус</th>
              <th style={{width: 180}}>Нагрузка</th>
              <th style={{textAlign: 'right'}}>CPU</th>
              <th style={{textAlign: 'right'}}>Маршруты</th>
              <th>Heartbeat</th>
              <th style={{width: 120}}>Трафик 24h</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {list.map((n) => (
              <tr key={n.id} onClick={() => onOpenNode(n)} style={{cursor: 'pointer'}}>
                <td>
                  <div style={{display: 'flex', alignItems: 'center', gap: 8}}>
                    <span className={`status-dot ${n.health} ${n.health === 'bad' ? 'pulse' : ''}`}></span>
                    <div>
                      <div style={{fontWeight: 500}}>{n.name}</div>
                      <div className="mono muted" style={{fontSize: 11}}>{n.id}</div>
                    </div>
                  </div>
                </td>
                <td>{n.flag} {n.region}</td>
                <td><span className="pill">{n.role}</span></td>
                <td>
                  <span className={`pill ${n.state === 'active' ? 'ok' : n.state === 'draining' ? 'warn' : 'muted'}`}>
                    {n.state}
                  </span>
                </td>
                <td><LoadBar v={n.load} /></td>
                <td className="tbl-num">{n.cpu}%</td>
                <td className="tbl-num">{n.routes}</td>
                <td className="mono" style={{color: n.hb.includes('s') && parseInt(n.hb) > 10 ? 'var(--bad)' : 'var(--text-secondary)'}}>{n.hb}</td>
                <td><Spark data={MOCK.spark(parseInt(n.id.slice(-4), 16) || 7, 20, 50, 30)} color="var(--accent)" w={90} h={22} /></td>
                <td className="row-actions">
                  <button className="btn btn-ghost btn-icon" onClick={(e) => e.stopPropagation()} style={{width: 24, height: 24}}>
                    <Icon name="more-horizontal" size={13} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Routes + Topology ───
function RoutesPage({ onOpenNode }) {
  const [view, setView] = useState('topology');
  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Маршруты</h1>
          <div className="page-subtitle">{MOCK.ROUTES.length} активных маршрутов · 1 blocked · 1 warming up</div>
        </div>
        <div className="page-head-actions">
          <div className="seg" style={{minWidth: 160}}>
            <button data-active={view === 'topology'} onClick={() => setView('topology')}><Icon name="git-branch" size={12} /> Поток</button>
            <button data-active={view === 'list'} onClick={() => setView('list')}><Icon name="list" size={12} /> Список</button>
          </div>
          <button className="btn btn-primary"><Icon name="plus" size={13} /> Создать маршрут</button>
        </div>
      </div>

      {view === 'topology' ? <TopologyView onOpenNode={onOpenNode} /> : <RoutesList />}
    </div>
  );
}

function RoutesMatrix({ onOpenNode }) {
  const entries = MOCK.NODES.filter(n => n.role === 'entry');
  const backends = MOCK.NODES.filter(n => n.role === 'backend');
  const [hover, setHover] = useState(null);
  const [selected, setSelected] = useState(null);

  // index routes by entry/backend pair
  const byPair = {};
  MOCK.ROUTES.forEach(r => { byPair[`${r.entry}|${r.backend}`] = r; });

  const statusClass = (s) => s === 'healthy' ? 'ok' : s === 'blocked' ? 'bad'
    : s === 'degraded' || s === 'suspected' ? 'warn' : s === 'warming_up' ? 'info' : 'muted';

  // Summary counts
  const counts = { healthy: 0, warn: 0, bad: 0, other: 0 };
  MOCK.ROUTES.forEach(r => {
    if (r.status === 'healthy') counts.healthy++;
    else if (r.status === 'blocked') counts.bad++;
    else if (r.status === 'degraded' || r.status === 'suspected') counts.warn++;
    else counts.other++;
  });

  return (
    <div>
      <div className="filterbar">
        <div className="matrix-summary">
          <span><span className="status-dot ok"></span> {counts.healthy} healthy</span>
          <span><span className="status-dot warn"></span> {counts.warn} degraded</span>
          <span><span className="status-dot bad"></span> {counts.bad} blocked</span>
          <span><span className="status-dot info"></span> {counts.other} warming up</span>
        </div>
        <div className="muted text-xs" style={{marginLeft: 'auto'}}>
          Клик по ячейке — детали маршрута · Клик по имени — открыть ноду
        </div>
      </div>

      <div className="card" style={{overflow: 'auto'}}>
        <div className="matrix-wrap">
          <table className="matrix">
            <thead>
              <tr>
                <th className="matrix-corner">
                  <div className="matrix-corner-inner">
                    <span className="muted text-xs" style={{writingMode: 'vertical-rl', transform: 'rotate(180deg)'}}>Entry</span>
                    <span className="muted text-xs" style={{marginLeft: 'auto'}}>Backend →</span>
                  </div>
                </th>
                {backends.map(b => (
                  <th key={b.id}
                      className={`matrix-col-head ${hover?.backend === b.name ? 'hl' : ''}`}
                      onClick={() => onOpenNode(b)}>
                    <div className="matrix-col-head-inner">
                      <span className="status-dot" data-health={b.health}></span>
                      <span className="flag">{b.flag}</span>
                      <span className="matrix-col-name">{b.name}</span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entries.map(e => (
                <tr key={e.id} className={hover?.entry === e.name ? 'hl' : ''}>
                  <th className={`matrix-row-head ${hover?.entry === e.name ? 'hl' : ''}`}
                      onClick={() => onOpenNode(e)}>
                    <span className="status-dot" data-health={e.health}></span>
                    <span className="flag">{e.flag}</span>
                    <span>{e.name}</span>
                    <span className="matrix-row-meta">{(e.load * 100)|0}%</span>
                  </th>
                  {backends.map(b => {
                    const r = byPair[`${e.name}|${b.name}`];
                    if (!r) {
                      return <td key={b.id} className="matrix-cell empty" onMouseEnter={() => setHover({entry: e.name, backend: b.name})} onMouseLeave={() => setHover(null)}></td>;
                    }
                    const sel = selected === r.id;
                    return (
                      <td key={b.id}
                          className={`matrix-cell ${statusClass(r.status)} ${sel ? 'sel' : ''}`}
                          title={`${r.id} · ${r.status} · ${r.latency != null ? r.latency + 'ms' : 'n/a'}`}
                          onMouseEnter={() => setHover({entry: e.name, backend: b.name})}
                          onMouseLeave={() => setHover(null)}
                          onClick={() => setSelected(sel ? null : r.id)}>
                        <div className="matrix-cell-inner">
                          <div className="matrix-cell-weight">{r.weight}</div>
                          <div className="matrix-cell-lat">
                            {r.latency != null ? `${r.latency}ms` : '—'}
                          </div>
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {selected && (() => {
        const r = MOCK.ROUTES.find(x => x.id === selected);
        if (!r) return null;
        return (
          <div className="card matrix-detail">
            <div className="matrix-detail-head">
              <div>
                <div className="matrix-detail-title">
                  <span className="mono">{r.id}</span>
                  <Icon name="arrow-right" size={12} style={{color: 'var(--text-muted)', margin: '0 4px'}} />
                  <span>{r.entry}</span>
                  <Icon name="arrow-right" size={11} style={{color: 'var(--text-faint)'}} />
                  <span>{r.backend}</span>
                </div>
                <div className="muted text-xs" style={{marginTop: 4}}>Выбран маршрут</div>
              </div>
              <div className="matrix-detail-actions">
                <RouteStatus s={r.status} />
                <button className="btn btn-xs"><Icon name="settings" size={11} /> Изменить</button>
                <button className="btn btn-ghost btn-icon btn-xs" onClick={() => setSelected(null)}><Icon name="x" size={12} /></button>
              </div>
            </div>
            <div className="matrix-detail-grid">
              <div><div className="muted text-xs">Вес</div><div className="mono" style={{fontSize: 15, marginTop: 2}}>{r.weight}</div></div>
              <div><div className="muted text-xs">Прогрев</div><div style={{marginTop: 4}}><LoadBar v={r.warmup/100} /></div></div>
              <div><div className="muted text-xs">Latency</div><div className="mono" style={{fontSize: 15, marginTop: 2, color: r.latency == null ? 'var(--bad)' : r.latency > 100 ? 'var(--warn)' : 'var(--text)'}}>{r.latency != null ? `${r.latency}ms` : '—'}</div></div>
              <div><div className="muted text-xs">Тренд latency (24ч)</div><div style={{marginTop: 2}}><Spark data={MOCK.spark(parseInt(r.id.slice(1)) || 7, 22, 60, 30)} color="var(--accent)" w={140} h={28} /></div></div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

function TopologyView({ onOpenNode }) {
  const entries = MOCK.NODES.filter(n => n.role === 'entry');
  const backends = MOCK.NODES.filter(n => n.role === 'backend');
  const canvasRef = useRef(null);
  const [edges, setEdges] = useState([]);
  const [focus, setFocus] = useState(null); // node name
  const [focusedRoute, setFocusedRoute] = useState(null);
  const [hoverEdge, setHoverEdge] = useState(null);
  const [onlyProblems, setOnlyProblems] = useState(false);

  // Sort backends by how they connect to entries, to minimize crossings
  const sortedEntries = useMemo(() => [...entries], [entries]);
  const sortedBackends = useMemo(() => {
    // For each backend, find avg index of connected entries — place it at that row
    const entryIndex = {};
    entries.forEach((e, i) => { entryIndex[e.name] = i; });
    return [...backends].sort((a, b) => {
      const ai = MOCK.ROUTES.filter(r => r.backend === a.name).map(r => entryIndex[r.entry] ?? 99);
      const bi = MOCK.ROUTES.filter(r => r.backend === b.name).map(r => entryIndex[r.entry] ?? 99);
      const avg = (xs) => xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : 99;
      return avg(ai) - avg(bi);
    });
  }, [entries, backends]);

  const recalc = () => {
    const c = canvasRef.current;
    if (!c) return;
    const rect = c.getBoundingClientRect();

    // Build per-node anchor points along the right/left edge, ordered by connected target's Y
    const nodesByName = {};
    c.querySelectorAll('[data-topo-id]').forEach(el => {
      nodesByName[el.getAttribute('data-topo-id')] = el.getBoundingClientRect();
    });

    // For each entry, rank its outgoing routes by the Y position of the target backend
    const entryOrder = {};
    const backendOrder = {};
    MOCK.NODES.filter(n => n.role === 'entry').forEach(en => {
      const outs = MOCK.ROUTES.filter(r => r.entry === en.name);
      // sort by backend Y
      outs.sort((a, b) => (nodesByName[a.backend]?.top ?? 0) - (nodesByName[b.backend]?.top ?? 0));
      outs.forEach((r, i) => { entryOrder[r.id] = { idx: i, total: outs.length }; });
    });
    MOCK.NODES.filter(n => n.role === 'backend').forEach(bn => {
      const ins = MOCK.ROUTES.filter(r => r.backend === bn.name);
      ins.sort((a, b) => (nodesByName[a.entry]?.top ?? 0) - (nodesByName[b.entry]?.top ?? 0));
      ins.forEach((r, i) => { backendOrder[r.id] = { idx: i, total: ins.length }; });
    });

    // Individual midpoint X per route, distributed in central strip
    const allRoutes = MOCK.ROUTES.slice().sort((a, b) => a.id.localeCompare(b.id));
    const xSlot = {};
    allRoutes.forEach((r, i) => { xSlot[r.id] = i; });
    const xSlotCount = Math.max(allRoutes.length, 1);

    const es = MOCK.ROUTES.map(r => {
      const a = nodesByName[r.entry];
      const b = nodesByName[r.backend];
      if (!a || !b) return null;

      // Anchor points along the vertical edge of each node
      const eo = entryOrder[r.id] || { idx: 0, total: 1 };
      const bo = backendOrder[r.id] || { idx: 0, total: 1 };

      const anchorY = (box, { idx, total }) => {
        if (total <= 1) return box.top + box.height / 2 - rect.top;
        // Use inset padding so anchors don't touch the corners
        const pad = 8;
        const top = box.top + pad - rect.top;
        const bot = box.top + box.height - pad - rect.top;
        return top + ((bot - top) * idx) / (total - 1);
      };

      const x1 = a.right - rect.left;
      const y1 = anchorY(a, eo);
      const x2 = b.left - rect.left;
      const y2 = anchorY(b, bo);

      // Stagger midX per route to avoid bundles of vertical lines at the same X
      const totalGap = Math.max(40, x2 - x1 - 80);
      const strip = totalGap;
      const midX = x1 + 40 + strip * ((xSlot[r.id] + 0.5) / xSlotCount);
      const clampedMidX = Math.min(x2 - 20, Math.max(x1 + 20, midX));

      const d = `M ${x1} ${y1}
                 L ${clampedMidX - 8} ${y1}
                 Q ${clampedMidX} ${y1}, ${clampedMidX} ${(y1+y2)/2}
                 Q ${clampedMidX} ${y2}, ${clampedMidX + 8} ${y2}
                 L ${x2} ${y2}`;
      const thickness = r.weight >= 80 ? 2.5 : r.weight >= 40 ? 1.8 : r.weight > 0 ? 1.3 : 1;
      return {
        id: r.id, entry: r.entry, backend: r.backend,
        d, x1, y1, x2, y2, midX: clampedMidX, midY: (y1 + y2) / 2,
        status: r.status, weight: r.weight, latency: r.latency, warmup: r.warmup,
        thickness,
      };
    }).filter(Boolean);
    setEdges(es);
  };

  useEffect(() => {
    recalc();
    const ro = new ResizeObserver(recalc);
    if (canvasRef.current) ro.observe(canvasRef.current);
    window.addEventListener('resize', recalc);
    return () => { ro.disconnect(); window.removeEventListener('resize', recalc); };
  }, []);

  const edgeStatusClass = (s) => s === 'healthy' ? 'active'
    : (s === 'degraded' || s === 'suspected') ? 'warn'
    : s === 'warming_up' ? 'info'
    : s === 'blocked' ? 'bad' : '';

  const isEdgeVisible = (e) => {
    if (onlyProblems && e.status === 'healthy') return false;
    return true;
  };
  const isEdgeFocused = (e) => {
    if (focusedRoute) return e.id === focusedRoute;
    if (focus) return e.entry === focus || e.backend === focus;
    return true;
  };
  const isNodeFocused = (name) => {
    if (focusedRoute) {
      const r = edges.find(e => e.id === focusedRoute);
      return r && (r.entry === name || r.backend === name);
    }
    if (!focus) return true;
    if (focus === name) return true;
    return edges.some(e => (e.entry === focus && e.backend === name) || (e.backend === focus && e.entry === name));
  };

  const selectedRoute = focusedRoute ? edges.find(e => e.id === focusedRoute) : null;

  // Per-node route counts (for badges)
  const nodeRouteStats = useMemo(() => {
    const m = {};
    MOCK.ROUTES.forEach(r => {
      if (!m[r.entry]) m[r.entry] = { total: 0, problems: 0 };
      if (!m[r.backend]) m[r.backend] = { total: 0, problems: 0 };
      m[r.entry].total++; m[r.backend].total++;
      if (r.status !== 'healthy') { m[r.entry].problems++; m[r.backend].problems++; }
    });
    return m;
  }, []);

  return (
    <div>
      <div className="filterbar">
        <label style={{display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--text-secondary)', cursor: 'pointer'}}>
          <input type="checkbox" checked={onlyProblems} onChange={e => setOnlyProblems(e.target.checked)} /> Только проблемные
        </label>
        {(focus || focusedRoute) && (
          <button className="btn btn-xs" onClick={() => { setFocus(null); setFocusedRoute(null); }}>
            <Icon name="x" size={11} /> Сбросить фокус
          </button>
        )}
        <div className="topo-summary-inline">
          <span><span className="status-dot ok"></span> {edges.filter(e => e.status === 'healthy').length} healthy</span>
          <span><span className="status-dot warn"></span> {edges.filter(e => e.status === 'degraded' || e.status === 'suspected').length} degraded</span>
          <span><span className="status-dot bad"></span> {edges.filter(e => e.status === 'blocked').length} blocked</span>
          <span><span className="status-dot info"></span> {edges.filter(e => e.status === 'warming_up').length} warming</span>
        </div>
        <div style={{display: 'flex', gap: 10, marginLeft: 'auto', fontSize: 11, alignItems: 'center'}}>
          <span className="muted">Толщина = вес маршрута · Анимация = healthy</span>
        </div>
      </div>
      <div className={`topo-v2 ${(focus || focusedRoute) ? 'has-focus' : ''}`} ref={canvasRef}>
        {/* Column headers */}
        <div className="topo-v2-header topo-v2-header-left">
          <Icon name="arrow-down-right" size={12} style={{color: 'var(--text-muted)', transform: 'rotate(-45deg)'}} />
          <span>Entry · точка входа</span>
        </div>
        <div className="topo-v2-header topo-v2-header-right">
          <span>Backend · обработка</span>
          <Icon name="arrow-right" size={12} style={{color: 'var(--text-muted)'}} />
        </div>

        {/* Left nodes */}
        <div className="topo-v2-nodes topo-v2-nodes-left">
          {sortedEntries.map(n => {
            const stats = nodeRouteStats[n.name] || { total: 0, problems: 0 };
            return (
              <div key={n.id} data-topo-id={n.name}
                   className={`topo-v2-node ${focus === n.name ? 'focused' : ''} ${!isNodeFocused(n.name) ? 'dim' : ''}`}
                   onClick={() => { setFocus(focus === n.name ? null : n.name); setFocusedRoute(null); }}
                   onDoubleClick={() => onOpenNode(n)}
                   title="Клик — фокус связей, двойной клик — открыть ноду">
                <div className="topo-v2-node-main">
                  <span className={`status-dot ${n.health}`}></span>
                  <span className="flag">{n.flag}</span>
                  <span className="topo-v2-node-name">{n.name}</span>
                </div>
                <div className="topo-v2-node-meta">
                  <span className="mono">{(n.load * 100) | 0}%</span>
                  <span className="topo-v2-node-routes">
                    {stats.total} <Icon name="route" size={10} />
                    {stats.problems > 0 && <span className="topo-v2-node-prob">{stats.problems}</span>}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Right nodes */}
        <div className="topo-v2-nodes topo-v2-nodes-right">
          {sortedBackends.map(n => {
            const stats = nodeRouteStats[n.name] || { total: 0, problems: 0 };
            return (
              <div key={n.id} data-topo-id={n.name}
                   className={`topo-v2-node ${focus === n.name ? 'focused' : ''} ${!isNodeFocused(n.name) ? 'dim' : ''}`}
                   onClick={() => { setFocus(focus === n.name ? null : n.name); setFocusedRoute(null); }}
                   onDoubleClick={() => onOpenNode(n)}
                   title="Клик — фокус связей, двойной клик — открыть ноду">
                <div className="topo-v2-node-main">
                  <span className={`status-dot ${n.health}`}></span>
                  <span className="flag">{n.flag}</span>
                  <span className="topo-v2-node-name">{n.name}</span>
                </div>
                <div className="topo-v2-node-meta">
                  <span className="mono">{(n.load * 100) | 0}%</span>
                  <span className="topo-v2-node-routes">
                    {stats.total} <Icon name="route" size={10} />
                    {stats.problems > 0 && <span className="topo-v2-node-prob">{stats.problems}</span>}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Edges */}
        <svg className="topo-v2-svg">
          {/* Invisible thick hit area for easier hover/click */}
          {edges.filter(isEdgeVisible).map(e => (
            <path key={`hit-${e.id}`} d={e.d}
                  className="topo-v2-edge-hit"
                  onMouseEnter={() => setHoverEdge(e.id)}
                  onMouseLeave={() => setHoverEdge(null)}
                  onClick={() => setFocusedRoute(focusedRoute === e.id ? null : e.id)} />
          ))}
          {/* Visible edges */}
          {edges.filter(isEdgeVisible).map(e => {
            const focused = isEdgeFocused(e);
            const hovered = hoverEdge === e.id;
            const isHealthy = e.status === 'healthy';
            return (
              <g key={e.id} className={`topo-v2-edge-group ${!focused ? 'dim' : ''} ${hovered || focusedRoute === e.id ? 'hot' : ''}`}>
                <path d={e.d}
                  className={`topo-v2-edge ${edgeStatusClass(e.status)}`}
                  style={{ strokeWidth: e.thickness + (hovered || focusedRoute === e.id ? 1.5 : 0) }} />
                {isHealthy && focused && (
                  <circle r="3" className="topo-v2-flow-dot">
                    <animateMotion dur={`${2.5 + (parseInt(e.id.slice(3)) % 3) * 0.5}s`} repeatCount="indefinite" path={e.d} rotate="auto" />
                  </circle>
                )}
                {(hovered || focusedRoute === e.id) && (
                  <g transform={`translate(${e.midX}, ${e.midY})`}>
                    <rect x="-48" y="-18" width="96" height="36" rx="6" className="topo-v2-edge-label-bg" />
                    <text x="0" y="-3" className="topo-v2-edge-label-id">{e.id}</text>
                    <text x="0" y="11" className="topo-v2-edge-label-lat">
                      {e.latency != null ? `${e.latency}ms · w${e.weight}` : `blocked · w${e.weight}`}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {selectedRoute && (() => {
        const r = MOCK.ROUTES.find(x => x.id === selectedRoute.id);
        if (!r) return null;
        return (
          <div className="card route-detail">
            <div className="route-detail-head">
              <div>
                <div className="route-detail-title">
                  <span className="mono">{r.id}</span>
                  <Icon name="arrow-right" size={12} style={{color: 'var(--text-muted)', margin: '0 4px'}} />
                  <span>{r.entry}</span>
                  <Icon name="arrow-right" size={11} style={{color: 'var(--text-faint)'}} />
                  <span>{r.backend}</span>
                </div>
                <div className="muted text-xs" style={{marginTop: 4}}>Маршрут выбран · клик по линии ещё раз — сбросить</div>
              </div>
              <div className="route-detail-actions">
                <RouteStatus s={r.status} />
                <button className="btn btn-xs"><Icon name="settings" size={11} /> Изменить</button>
                <button className="btn btn-ghost btn-icon btn-xs" onClick={() => setFocusedRoute(null)}><Icon name="x" size={12} /></button>
              </div>
            </div>
            <div className="route-detail-grid">
              <div><div className="muted text-xs">Вес</div><div className="mono" style={{fontSize: 15, marginTop: 2}}>{r.weight}</div></div>
              <div><div className="muted text-xs">Прогрев</div><div style={{marginTop: 4}}><LoadBar v={r.warmup/100} /></div></div>
              <div><div className="muted text-xs">Latency</div><div className="mono" style={{fontSize: 15, marginTop: 2, color: r.latency == null ? 'var(--bad)' : r.latency > 100 ? 'var(--warn)' : 'var(--text)'}}>{r.latency != null ? `${r.latency}ms` : '—'}</div></div>
              <div><div className="muted text-xs">Тренд latency (24ч)</div><div style={{marginTop: 2}}><Spark data={MOCK.spark(parseInt(r.id.slice(3)) || 7, 22, 60, 30)} color="var(--accent)" w={140} h={28} /></div></div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

function RoutesList() {
  return (
    <div className="card">
      <table className="tbl">
        <thead>
          <tr><th>ID</th><th>Entry</th><th>Backend</th><th>Статус</th><th style={{textAlign: 'right'}}>Вес</th><th style={{width: 140}}>Прогрев</th><th style={{textAlign: 'right'}}>Latency</th><th></th></tr>
        </thead>
        <tbody>
          {MOCK.ROUTES.map(r => (
            <tr key={r.id}>
              <td className="mono">{r.id}</td>
              <td>{r.entry}</td>
              <td>{r.backend}</td>
              <td><RouteStatus s={r.status} /></td>
              <td className="tbl-num">{r.weight}</td>
              <td><LoadBar v={r.warmup / 100} /></td>
              <td className="tbl-num" style={{color: r.latency == null ? 'var(--bad)' : r.latency > 100 ? 'var(--warn)' : 'var(--text)'}}>{r.latency != null ? `${r.latency}ms` : '—'}</td>
              <td className="row-actions">
                <button className="btn btn-ghost btn-icon" style={{width: 24, height: 24}}><Icon name="more-horizontal" size={13} /></button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Placeholder for non-detailed tabs ───
function PlaceholderPage({ tab }) {
  const titles = {
    probes: 'Probes', traffic: 'Трафик', placements: 'Плейсменты', transport: 'Очередь сообщений',
    users: 'Пользователи', plans: 'Тарифные планы', subscriptions: 'Подписки',
    zones: 'Зоны', 'admin-users': 'Админы', ops: 'Операции',
  };
  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">{titles[tab] || tab}</h1>
          <div className="page-subtitle">Раздел существует в реальной панели — в прототипе раскрыты Главная, Серверы, Маршруты</div>
        </div>
      </div>
      <div className="card" style={{padding: 40, textAlign: 'center'}}>
        <Icon name="layers" size={28} style={{color: 'var(--text-faint)', marginBottom: 10}} />
        <div style={{fontSize: 14, fontWeight: 500, marginBottom: 4}}>Раздел «{titles[tab] || tab}»</div>
        <div className="muted" style={{maxWidth: 420, margin: '0 auto'}}>
          Та же визуальная система применяется здесь: фильтр-бар, плотные таблицы с sparkline-трендами, slide-over для деталей, inline row-actions, ⌘K как основная точка входа.
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { OverviewPage, NodesPage, RoutesPage, PlaceholderPage });
