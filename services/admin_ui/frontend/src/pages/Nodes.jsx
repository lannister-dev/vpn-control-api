import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { Spark } from "../components/Spark.jsx";
import { nodeGeo, zoneFlag } from "../lib/geo.js";

function spark(seed, len = 20, base = 50, vol = 30) {
  let x = seed || 7;
  const out = [];
  for (let i = 0; i < len; i++) {
    x = (x * 9301 + 49297) % 233280;
    out.push(base + ((x / 233280) - 0.5) * vol * 2);
  }
  return out;
}

function relTime(iso) {
  if (!iso) return "—";
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h`;
}

function healthOf(n) {
  if (!n.is_enabled) return "bad";
  if (n.is_draining) return "warn";
  return n.is_healthy ? "ok" : "bad";
}

function stateOf(n) {
  if (!n.is_enabled) return "disabled";
  if (n.is_draining) return "draining";
  return "active";
}

function loadOf(n) {
  return Math.min(1, (n.placements_backend || 0) / Math.max(n.capacity || 50, 1));
}

export function NodesPage({ onOpenNode }) {
  const [filter, setFilter] = useState("");
  const [health, setHealth] = useState("");
  const [role, setRole] = useState("");

  const { data: status, loading, error, refetch } = useQuery(() => api.get("/admin/status"), { interval: 15000 });
  const zones = useQuery(() => api.get("/zones"), { interval: 60000 });
  const zoneByCode = useMemo(() => Object.fromEntries((zones.data?.items || []).map((z) => [z.code, z])), [zones.data]);

  const nodes = status?.nodes || [];
  const list = useMemo(() => {
    return nodes.filter((n) => {
      const h = healthOf(n);
      if (filter) {
        const q = filter.toLowerCase();
        if (!((n.name || "").toLowerCase().includes(q) || String(n.id).toLowerCase().includes(q) || (n.region || "").toLowerCase().includes(q) || (n.public_domain || "").toLowerCase().includes(q))) return false;
      }
      if (health && h !== health) return false;
      if (role && n.role !== role) return false;
      return true;
    });
  }, [nodes, filter, health, role]);

  const totalsLine = useMemo(() => {
    const total = nodes.length;
    const active = nodes.filter((n) => n.is_enabled && !n.is_draining).length;
    const draining = nodes.filter((n) => n.is_draining).length;
    return `${total} нод · ${active} активных${draining ? " · " + draining + " в draining" : ""}`;
  }, [nodes]);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Серверы</h1>
          <div className="page-subtitle">{totalsLine}</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={refetch}><Icon name="refresh" size={13} /> Обновить</button>
          <button className="btn"><Icon name="download" size={13} /> Экспорт</button>
          <button className="btn btn-primary"><Icon name="plus" size={13} /> Добавить сервер</button>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="filterbar">
        <div className="input-search-wrap">
          <Icon name="search" size={13} className="input-search-icon" />
          <input className="input" placeholder="Имя, UUID, домен, регион…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
        <select className="select" value={health} onChange={(e) => setHealth(e.target.value)}>
          <option value="">Любое здоровье</option>
          <option value="ok">Healthy</option>
          <option value="warn">Degraded</option>
          <option value="bad">Down</option>
        </select>
        <select className="select" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">Любая роль</option>
          <option value="entry">Entry</option>
          <option value="whitelist_entry">Whitelist entry</option>
          <option value="backend">Backend</option>
        </select>
        <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
          <span className="muted text-xs">{list.length} / {nodes.length}</span>
        </div>
      </div>

      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              <th>Сервер</th>
              <th>Регион</th>
              <th>Роль</th>
              <th>Статус</th>
              <th style={{ width: 180 }}>Нагрузка</th>
              <th style={{ textAlign: "right" }}>Capacity</th>
              <th style={{ textAlign: "right" }}>Маршруты</th>
              <th>Heartbeat</th>
              <th style={{ width: 120 }}>Трафик 24h</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {list.map((n) => {
              const h = healthOf(n);
              const st = stateOf(n);
              const load = loadOf(n);
              const seed = parseInt(String(n.id).replace(/-/g, "").slice(0, 6), 16) || 7;
              const flag = zoneFlag(zoneByCode, n.zone, n.region);
              const geo = nodeGeo(n.region);
              const hb = relTime(n.last_seen_at);
              const hbBad = /s$/.test(hb) && parseInt(hb) > 10;
              return (
                <tr key={n.id} onClick={() => onOpenNode && onOpenNode(n)} style={{ cursor: "pointer" }}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className={`status-dot ${h} ${h === "bad" ? "pulse" : ""}`} />
                      <div>
                        <div style={{ fontWeight: 500 }}>{n.name}</div>
                        <div className="mono muted" style={{ fontSize: 11 }}>{String(n.id).slice(0, 12)}…</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span style={{ marginRight: 6 }}>{flag}</span>
                    <span>{geo.country}</span>
                    <div className="mono muted" style={{ fontSize: 11 }}>{n.region}</div>
                  </td>
                  <td><span className="pill">{n.role}</span></td>
                  <td>
                    <span className={`pill ${st === "active" ? "ok" : st === "draining" ? "warn" : "muted"}`}>{st}</span>
                  </td>
                  <td><LoadBar v={load} /></td>
                  <td className="tbl-num">{n.capacity ?? "—"}</td>
                  <td className="tbl-num">{n.placements_backend ?? 0}</td>
                  <td className="mono" style={{ color: hbBad ? "var(--bad)" : "var(--text-secondary)" }}>{hb}</td>
                  <td><Spark data={spark(seed, 20, 50, 30)} color="var(--accent)" w={90} h={22} /></td>
                  <td className="row-actions">
                    <button className="btn btn-ghost btn-icon" onClick={(e) => e.stopPropagation()} style={{ width: 24, height: 24 }}>
                      <Icon name="more-horizontal" size={13} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {loading && !nodes.length && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {!loading && !list.length && <div className="muted" style={{ padding: 14 }}>Нет нод, подходящих под фильтр.</div>}
      </div>
    </div>
  );
}

function LoadBar({ v }) {
  const pct = Math.round(v * 100);
  const tone = pct > 80 ? "bad" : pct > 65 ? "warn" : "ok";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: "var(--surface-2)", borderRadius: 4, overflow: "hidden", maxWidth: 140 }}>
        <div style={{ width: `${pct}%`, height: "100%", background: `var(--${tone})` }} />
      </div>
      <span className="mono" style={{ color: `var(--${tone})`, fontWeight: 500 }}>{pct}%</span>
    </div>
  );
}
