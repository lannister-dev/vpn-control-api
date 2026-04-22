import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Drawer } from "./Drawer.jsx";
import { Modal } from "./Modal.jsx";
import { Field } from "./Field.jsx";
import { Icon } from "./Icon.jsx";
import { Spark } from "./Spark.jsx";
import { toast } from "./Toast.jsx";
import { nodeGeo } from "../lib/geo.js";

const isEntryRole = (n) => ["entry", "whitelist_entry"].includes(String(n?.role || "").toLowerCase());

function spark(seed, len = 48, base = 50, vol = 30) {
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

function healthTone(n) {
  if (!n.is_enabled) return "bad";
  if (n.is_draining) return "warn";
  return n.is_healthy ? "ok" : "bad";
}

function stateOf(n) {
  if (!n.is_enabled) return "disabled";
  if (n.is_draining) return "draining";
  return "active";
}

export function NodeDrawer({ node, onClose }) {
  const [tab, setTab] = useState("overview");
  const entryRole = isEntryRole(node);
  const routes = useQuery(() => api.get("/routes?limit=500"), { interval: 15000 });
  const routesCount = (routes.data || []).filter((r) => r.node_id === node.id || r.entry_node_id === node.id).length;

  const tabs = [
    { id: "overview", label: "Обзор" },
    { id: "routes", label: `Маршруты · ${routesCount}` },
    { id: "probes", label: "Probes" },
    { id: "transport", label: "Transport" },
    ...(entryRole ? [{ id: "pool", label: "Pool" }] : []),
  ];

  const geo = nodeGeo(node.region);
  const tone = healthTone(node);

  const head = (
    <>
      <span className={`status-dot ${tone} ${tone === "bad" ? "pulse" : ""}`} style={{ marginTop: 6 }} />
      <div className="slideover-title-main">
        <div className="slideover-title" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span>{geo.flag}</span>
          <span>{node.name}</span>
          <span className="pill">{node.role}</span>
        </div>
        <div className="slideover-sub">
          <span className="mono">{String(node.id).slice(0, 12)}</span> · {node.region} · heartbeat {relTime(node.last_seen_at)}
        </div>
      </div>
    </>
  );

  return (
    <Drawer
      head={head}
      onClose={onClose}
      tabs={tabs}
      activeTab={tab}
      onTab={setTab}
      actions={<button className="btn btn-ghost btn-icon" title="Действия"><Icon name="more-horizontal" size={15} /></button>}
    >
      {tab === "overview" && <NodeOverview node={node} routesCount={routesCount} />}
      {tab === "routes" && <NodeRoutes node={node} routes={routes.data || []} />}
      {tab === "probes" && <NodeProbes node={node} />}
      {tab === "transport" && <NodeTransport node={node} />}
      {tab === "pool" && entryRole && <NodePool node={node} />}
    </Drawer>
  );
}

function NodeOverview({ node, routesCount }) {
  const seed = parseInt(String(node.id).replace(/-/g, "").slice(0, 6), 16) || 11;
  const cpuValue = Math.min(95, Math.max(8, Math.round(((node.placements_backend || 0) / Math.max(node.capacity || 50, 1)) * 80 + (seed % 30))));
  const cpuSpark = spark(seed * 7, 48, cpuValue, 15);
  const netSpark = spark(seed * 11 + 3, 48, 50, 30);
  const loadPct = Math.min(100, Math.round(((node.placements_backend || 0) / Math.max(node.capacity || 50, 1)) * 100));

  const loadTone = loadPct > 80 ? "bad" : loadPct > 65 ? "warn" : "ok";
  const tone = healthTone(node);
  const st = stateOf(node);

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 20 }}>
        <div className="card">
          <div className="card-body" style={{ padding: 14 }}>
            <div className="kpi-label"><Icon name="cpu" size={12} /> CPU</div>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
              <div className="kpi-value" style={{ fontSize: 22 }}>{cpuValue}<span className="kpi-unit">%</span></div>
              <Spark data={cpuSpark} color="var(--accent)" w={110} h={32} />
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-body" style={{ padding: 14 }}>
            <div className="kpi-label"><Icon name="activity" size={12} /> Трафик 24h</div>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
              <div className="kpi-value" style={{ fontSize: 22 }}>—</div>
              <Spark data={netSpark} color="var(--ok)" w={110} h={32} />
            </div>
          </div>
        </div>
      </div>

      <div className="sec-head"><div className="sec-title">Параметры</div></div>
      <dl className="kv" style={{ marginBottom: 20 }}>
        <dt>UUID</dt><dd className="mono">{node.id}</dd>
        <dt>Регион</dt><dd>{nodeGeo(node.region).flag} {node.region}</dd>
        <dt>Зона</dt><dd>{node.zone || <span className="muted">—</span>}</dd>
        <dt>Роль</dt><dd>{node.role}</dd>
        <dt>Статус</dt><dd><span className={`pill ${st === "active" ? "ok" : st === "draining" ? "warn" : ""}`}>{st}</span></dd>
        <dt>Здоровье</dt><dd><span className={`pill ${tone}`}><span className={`status-dot ${tone}`} /> {tone === "ok" ? "healthy" : tone === "warn" ? "degraded" : "unhealthy"}</span></dd>
        <dt>Нагрузка</dt><dd>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ flex: 1, height: 6, background: "var(--surface-2)", borderRadius: 4, overflow: "hidden", maxWidth: 140 }}>
              <div style={{ width: `${loadPct}%`, height: "100%", background: `var(--${loadTone})` }} />
            </div>
            <span className="mono" style={{ color: `var(--${loadTone})`, fontWeight: 500 }}>{loadPct}%</span>
          </div>
        </dd>
        <dt>Capacity</dt><dd className="mono">{node.capacity ?? "—"}</dd>
        <dt>Heartbeat</dt><dd className="mono">{relTime(node.last_seen_at)} назад</dd>
        <dt>Маршрутов</dt><dd className="mono">{routesCount}</dd>
        <dt>Public domain</dt><dd className="mono small">{node.public_domain || "—"}</dd>
        <dt>Reality IP</dt><dd className="mono small">{node.reality_ip || "—"}</dd>
      </dl>

      <div className="sec-head"><div className="sec-title">Быстрые действия</div></div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <button className="btn" disabled={node.is_draining} title={node.is_draining ? "Уже в draining" : "Включить drain"}>
          <Icon name="pause" size={12} /> Drain
        </button>
        <button className="btn"><Icon name="arrow-right" size={12} /> Migrate</button>
        <button className="btn"><Icon name="refresh" size={12} /> Snapshot</button>
        <button className="btn"><Icon name="terminal" size={12} /> SSH</button>
        <button className="btn"><Icon name="edit" size={12} /> Редактировать</button>
      </div>
    </div>
  );
}

function NodeRoutes({ node, routes }) {
  const list = routes.filter((r) => r.node_id === node.id || r.entry_node_id === node.id);
  if (!list.length) return <div className="muted" style={{ padding: 14 }}>Маршрутов нет.</div>;
  return (
    <table className="tbl">
      <thead>
        <tr><th>Маршрут</th><th>Направление</th><th>Status</th><th style={{ textAlign: "right" }}>Weight</th></tr>
      </thead>
      <tbody>
        {list.map((r) => (
          <tr key={r.id}>
            <td>{r.name}</td>
            <td className="small muted">{r.node_id === node.id ? "backend" : "entry"}</td>
            <td><span className={"pill " + toneOf(r.health_status)}>{r.health_status}</span></td>
            <td className="tbl-num mono">{r.effective_weight}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function NodeProbes({ node }) {
  const { data, loading } = useQuery(() => api.get("/probe/reports/recent?limit=80"), { interval: 10000 });
  const rows = (data || []).filter((p) => p.node_id === node.id);
  if (loading && !rows.length) return <div className="muted" style={{ padding: 14 }}>Загрузка…</div>;
  if (!rows.length) return <div className="muted" style={{ padding: 14 }}>Probe-сигналов нет.</div>;
  return (
    <table className="tbl">
      <thead>
        <tr><th>Источник</th><th>Тип</th><th>Status</th><th style={{ textAlign: "right" }}>Latency</th><th>Время</th></tr>
      </thead>
      <tbody>
        {rows.slice(0, 30).map((p) => (
          <tr key={p.id}>
            <td><span className="pill">{p.source}</span></td>
            <td className="small">{p.probe_kind}</td>
            <td>{p.is_reachable ? <span className="pill ok">OK</span> : <span className="pill bad">FAIL</span>}</td>
            <td className="tbl-num mono">{p.latency_ms ?? "—"}</td>
            <td className="small muted">{p.checked_at ? new Date(p.checked_at).toLocaleTimeString() : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function NodeTransport({ node }) {
  const { data, loading } = useQuery(() => api.get("/admin/transport/nodes"), { interval: 15000 });
  const row = (data?.items || []).find((t) => t.node_id === node.id);
  if (loading && !row) return <div className="muted" style={{ padding: 14 }}>Загрузка…</div>;
  if (!row) return <div className="muted" style={{ padding: 14 }}>Агент не зарегистрирован.</div>;
  const tone = { ok: "ok", lag: "warn", silent: "warn", dead: "bad" }[row.health_verdict] || "";
  return (
    <dl className="kv">
      <dt>Вердикт</dt><dd><span className={"pill " + tone}>{row.health_verdict || "—"}</span></dd>
      <dt>Эпоха</dt><dd className="mono">{row.current_epoch}</dd>
      <dt>Heartbeat</dt><dd className="small muted">{relTime(row.last_heartbeat_received_at)} назад</dd>
      <dt>Outbox pending</dt><dd className="mono">{row.outbox_pending || 0}</dd>
      <dt>Outbox failed</dt><dd className="mono">{row.outbox_failed || 0}</dd>
      <dt>Last sync</dt><dd className="small muted">{relTime(row.last_sync_report_received_at)} назад</dd>
    </dl>
  );
}

function NodePool({ node }) {
  const { data, loading, refetch } = useQuery(
    () => api.get(`/entry/${node.id}/assignments`),
    { interval: 20000, deps: [node.id] },
  );
  const status = useQuery(() => api.get("/admin/status"), { interval: 30000 });
  const nodesById = useMemo(
    () => Object.fromEntries((status.data?.nodes || []).map((n) => [n.id, n])),
    [status.data],
  );
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);

  const items = Array.isArray(data) ? data : (data?.items || []);

  const remove = async (backendId) => {
    if (!confirm("Убрать backend из пула этого entry?")) return;
    try { await api.del(`/entry/${node.id}/assignments/${backendId}`); toast.ok("Backend удалён из пула"); refetch(); }
    catch (e) { toast.bad(e.message); }
  };

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div className="muted small">Backends, закреплённые за этой entry (HAProxy pool)</div>
        <button className="btn btn-primary" onClick={() => setAdding(true)}><Icon name="plus" size={12} /> Добавить</button>
      </div>
      {loading && !items.length && <div className="muted">Загрузка…</div>}
      {!loading && !items.length && <div className="muted">Пул пуст.</div>}
      {items.length > 0 && (
        <table className="tbl">
          <thead>
            <tr><th>Backend</th><th style={{ textAlign: "right" }}>Вес</th><th style={{ textAlign: "right" }}>Rank</th><th>Enabled</th><th></th></tr>
          </thead>
          <tbody>
            {items.map((a) => {
              const n = nodesById[a.backend_node_id];
              return (
                <tr key={a.backend_node_id}>
                  <td>
                    {n ? (
                      <>
                        <span style={{ marginRight: 6 }}>{nodeGeo(n.region).flag}</span>
                        <span style={{ fontWeight: 500 }}>{n.name}</span>
                        <div className="mono muted" style={{ fontSize: 11 }}>{n.region}</div>
                      </>
                    ) : (
                      <span className="mono small">{String(a.backend_node_id).slice(0, 12)}…</span>
                    )}
                  </td>
                  <td className="tbl-num mono">{a.weight}</td>
                  <td className="tbl-num mono">{a.rank}</td>
                  <td>{a.enabled ? <span className="pill ok">enabled</span> : <span className="pill">off</span>}</td>
                  <td className="row-actions">
                    <button className="row-btn" onClick={() => setEditing(a)}>Edit</button>
                    <button className="row-btn" onClick={() => remove(a.backend_node_id)}>Remove</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {adding && <AssignmentForm entryId={node.id} existing={items} allNodes={status.data?.nodes || []} onClose={() => { setAdding(false); refetch(); }} />}
      {editing && <AssignmentForm entryId={node.id} assignment={editing} onClose={() => { setEditing(null); refetch(); }} />}
    </>
  );
}

function AssignmentForm({ entryId, assignment, existing = [], allNodes = [], onClose }) {
  const isEdit = !!assignment;
  const [backendId, setBackendId] = useState(assignment?.backend_node_id || "");
  const [weight, setWeight] = useState(assignment?.weight ?? 100);
  const [rank, setRank] = useState(assignment?.rank ?? 0);
  const [enabled, setEnabled] = useState(assignment?.enabled ?? true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const existingIds = new Set(existing.map((a) => a.backend_node_id));
  const candidates = allNodes.filter((n) => n.role === "backend" && !existingIds.has(n.id));

  const save = async () => {
    setBusy(true); setErr("");
    try {
      if (isEdit) {
        await api.patch(`/entry/${entryId}/assignments/${assignment.backend_node_id}`, { weight: Number(weight), rank: Number(rank), enabled: !!enabled });
      } else {
        if (!backendId) throw new Error("Выберите backend");
        await api.post(`/entry/${entryId}/assignments`, { backend_node_id: backendId, weight: Number(weight), rank: Number(rank), enabled: !!enabled });
      }
      onClose();
    } catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <Modal
      title={isEdit ? `Backend ${String(assignment.backend_node_id).slice(0, 8)}…` : "Добавить backend в пул"}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose}>Отмена</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>{isEdit ? "Сохранить" : "Добавить"}</button>
        </>
      }
    >
      {err && <div className="form-error">{err}</div>}
      {!isEdit && (
        <Field label="Backend">
          <select value={backendId} onChange={(e) => setBackendId(e.target.value)}>
            <option value="">— выберите —</option>
            {candidates.map((n) => (
              <option key={n.id} value={n.id}>{n.name} · {n.region}</option>
            ))}
          </select>
        </Field>
      )}
      <div className="form-row">
        <Field label="Вес"><input type="number" min={0} max={1000} value={weight} onChange={(e) => setWeight(e.target.value)} /></Field>
        <Field label="Rank"><input type="number" min={0} max={1000} value={rank} onChange={(e) => setRank(e.target.value)} /></Field>
      </div>
      <label className="form-check">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Enabled
      </label>
    </Modal>
  );
}

function toneOf(s) {
  if (s === "healthy") return "ok";
  if (s === "warming_up" || s === "degraded" || s === "suspected") return "warn";
  if (s === "blocked") return "bad";
  return "";
}
