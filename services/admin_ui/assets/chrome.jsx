// Sidebar, Topbar, Palette, Slideover, Tweaks — shared chrome
const { useState, useEffect, useRef, useMemo } = React;

// ─── Sparkline ───
function Spark({ data, color = 'currentColor', w = 90, h = 28, filled = true }) {
  const min = Math.min(...data), max = Math.max(...data);
  const pad = 2;
  const stepX = (w - pad * 2) / (data.length - 1);
  const norm = (v) => h - pad - ((v - min) / (max - min || 1)) * (h - pad * 2);
  const line = data.map((v, i) => `${i === 0 ? 'M' : 'L'} ${pad + i * stepX} ${norm(v)}`).join(' ');
  const fill = `${line} L ${w - pad} ${h} L ${pad} ${h} Z`;
  return (
    <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      {filled && <path d={fill} className="fill" fill={color} />}
      <path d={line} stroke={color} />
    </svg>
  );
}

// ─── Sidebar ───
function Sidebar({ activeTab, onTab, collapsed, onToggle, onOpenPalette }) {
  const groups = [
    { title: 'Мониторинг', items: [
      { id: 'overview', label: 'Главная', icon: 'layout-dashboard', badge: true },
      { id: 'probes', label: 'Probes', icon: 'radar', count: 14 },
      { id: 'traffic', label: 'Трафик', icon: 'bar-chart' },
    ]},
    { title: 'Инфраструктура', items: [
      { id: 'nodes', label: 'Серверы', icon: 'server', count: 9 },
      { id: 'routes', label: 'Маршруты', icon: 'route', count: 47 },
      { id: 'placements', label: 'Плейсменты', icon: 'map-pin' },
      { id: 'transport', label: 'Очередь', icon: 'activity' },
    ]},
    { title: 'Бизнес', items: [
      { id: 'users', label: 'Пользователи', icon: 'users', count: 2847 },
      { id: 'plans', label: 'Тарифы', icon: 'wallet' },
      { id: 'subscriptions', label: 'Подписки', icon: 'key' },
    ]},
    { title: 'Система', items: [
      { id: 'zones', label: 'Зоны', icon: 'globe' },
      { id: 'admin-users', label: 'Админы', icon: 'shield' },
      { id: 'ops', label: 'Операции', icon: 'wrench' },
    ]},
  ];

  return (
    <aside className="sidebar" data-collapsed={collapsed}>
      <div className="workspace" onClick={onToggle} title="Свернуть">
        <div className="workspace-logo">V</div>
        <div className="workspace-text">
          <div className="workspace-name">VPN Control</div>
          <div className="workspace-env">prod · v2.14.0</div>
        </div>
      </div>

      <div className="side-search">
        <button className="side-search-btn" onClick={onOpenPalette}>
          <Icon name="search" size={14} />
          <span>Поиск или команда</span>
          <span className="kbd-inline">
            <span className="kbd">⌘</span><span className="kbd">K</span>
          </span>
        </button>
      </div>

      <nav className="side-nav">
        {groups.map((g) => (
          <div key={g.title} className="side-group">
            <div className="side-group-title">{g.title}</div>
            {g.items.map((it) => (
              <button
                key={it.id}
                className="side-btn"
                data-active={activeTab === it.id}
                onClick={() => onTab(it.id)}
              >
                <Icon name={it.icon} size={15} />
                <span className="side-label">{it.label}</span>
                {it.badge && <span className="side-badge" title="Требуют внимания"></span>}
                {it.count != null && <span className="side-count">{it.count > 999 ? `${(it.count/1000).toFixed(1)}k` : it.count}</span>}
              </button>
            ))}
          </div>
        ))}
      </nav>

      <div className="side-footer">
        <div className="user-avatar">KS</div>
        <div className="side-footer-user">
          <div className="side-footer-name">k.shirokova</div>
          <div className="side-footer-status">
            <span className="side-footer-dot"></span>
            <span>admin</span>
          </div>
        </div>
        <button className="btn btn-ghost btn-icon" title="Настройки" style={{width: 24, height: 24}}>
          <Icon name="settings" size={14} />
        </button>
      </div>
    </aside>
  );
}

// ─── Topbar ───
function Topbar({ crumbs, onOpenPalette, onRefresh, lastSync, theme, onToggleTheme, notifCount = 3 }) {
  return (
    <header className="topbar">
      <div className="crumbs">
        {crumbs.map((c, i) => (
          <React.Fragment key={i}>
            {i > 0 && <Icon className="crumb-sep" name="chevron-right" size={13} />}
            <span className={`crumb ${i === crumbs.length - 1 ? 'current' : ''}`}>{c}</span>
          </React.Fragment>
        ))}
      </div>
      <div className="topbar-spacer"></div>
      <div className="topbar-actions">
        <span className="env-pill"><span className="status-dot ok pulse"></span> PROD</span>
        <span className="last-sync-label muted text-xs mono" style={{marginRight: 8, whiteSpace: 'nowrap'}}>Обновлено {lastSync}</span>
        <button className="btn btn-ghost btn-icon" onClick={onRefresh} title="Обновить">
          <Icon name="refresh" size={15} />
        </button>
        <button className="btn btn-ghost btn-icon" title="Уведомления" style={{position: 'relative'}}>
          <Icon name="bell" size={15} />
          {notifCount > 0 && <span style={{position:'absolute',top:4,right:4,width:6,height:6,borderRadius:'50%',background:'var(--bad)'}}></span>}
        </button>
        <button className="btn btn-ghost btn-icon" onClick={onToggleTheme} title="Переключить тему">
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={15} />
        </button>
        <button className="btn btn-ghost" onClick={onOpenPalette}>
          <Icon name="command" size={13} />
          <span>Команды</span>
          <span className="kbd">K</span>
        </button>
      </div>
    </header>
  );
}

// ─── Command Palette ───
function Palette({ open, onClose, onSelect, theme, density }) {
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);

  useEffect(() => {
    if (open) {
      setQ(''); setActive(0);
      setTimeout(() => inputRef.current?.focus(), 40);
    }
  }, [open]);

  const filtered = useMemo(() => {
    if (!MOCK.COMMANDS) return [];
    if (!q.trim()) return MOCK.COMMANDS;
    const needle = q.toLowerCase();
    return MOCK.COMMANDS.map(g => ({
      ...g,
      items: g.items.filter(it => it.label.toLowerCase().includes(needle) || (it.sub || '').toLowerCase().includes(needle))
    })).filter(g => g.items.length);
  }, [q]);

  const flat = filtered.flatMap(g => g.items);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose(); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, flat.length - 1)); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); }
      else if (e.key === 'Enter') { e.preventDefault(); if (flat[active]) onSelect(flat[active]); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, flat, active, onSelect, onClose]);

  if (!open) return null;
  let idx = -1;
  return (
    <div className="palette-backdrop" onClick={onClose}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        <div className="palette-input-wrap">
          <Icon name="search" size={16} />
          <input
            ref={inputRef}
            className="palette-input"
            placeholder="Поиск или команда · попробуйте: migrate, sgp, warmup…"
            value={q}
            onChange={(e) => { setQ(e.target.value); setActive(0); }}
          />
          <span className="palette-hint"><span className="kbd">esc</span></span>
        </div>
        <div className="palette-list">
          {filtered.length === 0 && <div className="empty">Ничего не найдено</div>}
          {filtered.map((g) => (
            <div key={g.group}>
              <div className="palette-group-title">{g.group}</div>
              {g.items.map((it) => {
                idx++;
                const thisIdx = idx;
                return (
                  <div
                    key={it.label}
                    className="palette-item"
                    data-active={thisIdx === active}
                    onMouseEnter={() => setActive(thisIdx)}
                    onClick={() => onSelect(it)}
                  >
                    <div className="palette-item-icon"><Icon name={it.icon} size={13} /></div>
                    <div className="palette-item-main">
                      <div className="palette-item-label">{it.label}</div>
                      {it.sub && <div className="palette-item-sub">{it.sub}</div>}
                    </div>
                    {it.kbd && (
                      <div className="palette-item-kbd">
                        {it.kbd.map((k, i) => <span key={i} className="kbd">{k}</span>)}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <div className="palette-footer">
          <div className="palette-footer-item"><span className="kbd">↑</span><span className="kbd">↓</span> навигация</div>
          <div className="palette-footer-item"><span className="kbd">↵</span> выбрать</div>
          <div className="palette-footer-item" style={{marginLeft: 'auto'}}>
            <Icon name="sparkles" size={12} />
            <span>Можно выполнять действия</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Tweaks ───
function TweaksPanel({ theme, density, accent, onTheme, onDensity, onAccent, onClose }) {
  const accents = [
    { id: 'indigo', c: 'oklch(0.56 0.14 260)' },
    { id: 'teal', c: 'oklch(0.58 0.13 190)' },
    { id: 'amber', c: 'oklch(0.68 0.15 70)' },
    { id: 'rose', c: 'oklch(0.60 0.17 20)' },
    { id: 'mono', c: 'oklch(0.35 0 0)' },
  ];
  return (
    <div className="tweaks">
      <div className="tweaks-head">
        <Icon name="sliders" size={14} />
        <span>Tweaks</span>
        <div style={{marginLeft: 'auto', display: 'flex', gap: 4}}>
          <button className="btn btn-ghost btn-icon" onClick={onClose} style={{width: 22, height: 22}}>
            <Icon name="x" size={13} />
          </button>
        </div>
      </div>
      <div className="tweaks-body">
        <div>
          <div className="tweak-group-label">Тема</div>
          <div className="seg">
            <button data-active={theme === 'light'} onClick={() => onTheme('light')}>Light</button>
            <button data-active={theme === 'dark'} onClick={() => onTheme('dark')}>Dark</button>
          </div>
        </div>
        <div>
          <div className="tweak-group-label">Плотность</div>
          <div className="seg">
            <button data-active={density === 'compact'} onClick={() => onDensity('compact')}>Compact</button>
            <button data-active={density === 'comfortable'} onClick={() => onDensity('comfortable')}>Comfort</button>
            <button data-active={density === 'spacious'} onClick={() => onDensity('spacious')}>Spacious</button>
          </div>
        </div>
        <div>
          <div className="tweak-group-label">Акцент</div>
          <div className="accent-swatches">
            {accents.map((a) => (
              <button
                key={a.id}
                className="accent-swatch"
                data-active={accent === a.id}
                style={{ background: a.c }}
                onClick={() => onAccent(a.id)}
                title={a.id}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Slideover (Node Detail) ───
function NodeSlideover({ node, onClose, onJumpRoutes }) {
  const [tab, setTab] = useState('overview');
  if (!node) return null;
  return (
    <>
      <div className="slideover-backdrop" onClick={onClose}></div>
      <div className="slideover">
        <div className="slideover-head">
          <div className={`status-dot ${node.health}`}></div>
          <div className="slideover-title-main">
            <div className="slideover-title">
              {node.flag} {node.name}
              <span className="pill">{node.role}</span>
            </div>
            <div className="slideover-sub">
              <span className="mono">{node.id}</span> · {node.region} · heartbeat {node.hb}
            </div>
          </div>
          <button className="btn btn-ghost btn-icon" title="Действия"><Icon name="more-horizontal" size={15} /></button>
          <button className="btn btn-ghost btn-icon" onClick={onClose}><Icon name="x" size={15} /></button>
        </div>
        <div className="slideover-tabs">
          {['overview', 'routes', 'placements', 'probes', 'transport'].map((t) => (
            <button key={t} className="slideover-tab" data-active={tab === t} onClick={() => setTab(t)}>
              {{overview:'Обзор', routes:`Маршруты · ${node.routes}`, placements:'Плейсменты', probes:'Probes', transport:'Transport'}[t]}
            </button>
          ))}
        </div>
        <div className="slideover-body">
          {tab === 'overview' && <NodeOverview node={node} />}
          {tab === 'routes' && <NodeRoutes node={node} onJumpRoutes={onJumpRoutes} />}
          {tab !== 'overview' && tab !== 'routes' && (
            <div className="empty">
              <Icon name="layers" size={24} style={{opacity: 0.4, marginBottom: 8}} />
              <div>Содержимое вкладки «{tab}» в прототипе не раскрыто</div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function NodeOverview({ node }) {
  const cpuSpark = MOCK.spark(node.cpu * 7, 48, node.cpu, 15);
  const netSpark = MOCK.spark(node.cpu * 11 + 3, 48, 50, 30);
  return (
    <div>
      <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20}}>
        <div className="card">
          <div className="card-body" style={{padding: 14}}>
            <div className="kpi-label"><Icon name="cpu" size={12} /> CPU</div>
            <div style={{display: 'flex', alignItems: 'baseline', justifyContent: 'space-between'}}>
              <div className="kpi-value" style={{fontSize: 22}}>{node.cpu}<span className="kpi-unit">%</span></div>
              <Spark data={cpuSpark} color="var(--accent)" w={110} h={32} />
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-body" style={{padding: 14}}>
            <div className="kpi-label"><Icon name="activity" size={12} /> Трафик 24h</div>
            <div style={{display: 'flex', alignItems: 'baseline', justifyContent: 'space-between'}}>
              <div className="kpi-value" style={{fontSize: 22}}>{node.traffic}</div>
              <Spark data={netSpark} color="var(--ok)" w={110} h={32} />
            </div>
          </div>
        </div>
      </div>

      <div className="sec-head"><div className="sec-title">Параметры</div></div>
      <dl className="kv" style={{marginBottom: 20}}>
        <dt>UUID</dt><dd className="mono">{node.id}</dd>
        <dt>Регион</dt><dd>{node.flag} {node.region}</dd>
        <dt>Роль</dt><dd>{node.role}</dd>
        <dt>Статус</dt><dd><span className={`pill ${node.state === 'active' ? 'ok' : 'warn'}`}>{node.state}</span></dd>
        <dt>Здоровье</dt><dd><span className={`pill ${node.health}`}><span className={`status-dot ${node.health}`}></span> {node.health === 'ok' ? 'healthy' : node.health === 'warn' ? 'degraded' : 'unhealthy'}</span></dd>
        <dt>Нагрузка</dt><dd><LoadBar v={node.load} /></dd>
        <dt>Heartbeat</dt><dd className="mono">{node.hb} назад</dd>
        <dt>Маршрутов</dt><dd>{node.routes}</dd>
      </dl>

      <div className="sec-head"><div className="sec-title">Быстрые действия</div></div>
      <div style={{display: 'flex', gap: 6, flexWrap: 'wrap'}}>
        <button className="btn"><Icon name="pause" size={12} /> Drain</button>
        <button className="btn"><Icon name="arrow-right" size={12} /> Migrate</button>
        <button className="btn"><Icon name="refresh" size={12} /> Snapshot</button>
        <button className="btn"><Icon name="terminal" size={12} /> SSH</button>
        <button className="btn"><Icon name="edit" size={12} /> Редактировать</button>
      </div>
    </div>
  );
}
function LoadBar({ v }) {
  const pct = Math.round(v * 100);
  const tone = pct > 80 ? 'bad' : pct > 65 ? 'warn' : 'ok';
  return (
    <div style={{display: 'flex', alignItems: 'center', gap: 8}}>
      <div style={{flex: 1, height: 6, background: 'var(--surface-2)', borderRadius: 4, overflow: 'hidden', maxWidth: 140}}>
        <div style={{width: `${pct}%`, height: '100%', background: `var(--${tone})`}}></div>
      </div>
      <span className="mono" style={{color: `var(--${tone})`, fontWeight: 500}}>{pct}%</span>
    </div>
  );
}
function NodeRoutes({ node, onJumpRoutes }) {
  const rts = MOCK.ROUTES.filter(r => r.entry === node.name || r.backend === node.name);
  return (
    <div>
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10}}>
        <div className="muted">Маршруты с участием этого сервера</div>
        <button className="btn btn-xs" onClick={onJumpRoutes}>Открыть раздел <Icon name="arrow-up-right" size={12} /></button>
      </div>
      <table className="tbl">
        <thead><tr><th>ID</th><th>Направление</th><th>Статус</th><th style={{textAlign: 'right'}}>Latency</th></tr></thead>
        <tbody>
          {rts.map(r => (
            <tr key={r.id}>
              <td className="mono">{r.id}</td>
              <td className="truncate" style={{maxWidth: 220}}>{r.entry} → {r.backend}</td>
              <td><RouteStatus s={r.status} /></td>
              <td className="tbl-num">{r.latency != null ? `${r.latency}ms` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RouteStatus({ s }) {
  const map = {
    healthy: { tone: 'ok', label: 'healthy' },
    degraded: { tone: 'warn', label: 'degraded' },
    suspected: { tone: 'warn', label: 'suspected' },
    blocked: { tone: 'bad', label: 'blocked' },
    warming_up: { tone: 'info', label: 'warming up' },
  };
  const m = map[s] || { tone: 'muted', label: s };
  return <span className={`pill ${m.tone}`}><span className={`status-dot ${m.tone}`}></span> {m.label}</span>;
}

Object.assign(window, { Spark, Sidebar, Topbar, Palette, TweaksPanel, NodeSlideover, RouteStatus, LoadBar });
