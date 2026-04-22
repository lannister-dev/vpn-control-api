import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Drawer } from "./Drawer.jsx";
import { Modal } from "./Modal.jsx";
import { Field } from "./Field.jsx";

const isEntryRole = (n) => ["entry", "whitelist_entry"].includes(String(n?.role || "").toLowerCase());

export function NodeDrawer({ node, onClose }) {
  const [tab, setTab] = useState("overview");
  const entryRole = isEntryRole(node);
  const tabs = [
    { id: "overview", label: "Обзор" },
    { id: "routes", label: "Маршруты" },
    { id: "probes", label: "Probes" },
    ...(entryRole ? [{ id: "pool", label: "Pool" }] : []),
  ];

  return (
    <Drawer
      title={node.name}
      subtitle={`${node.role} · ${node.region}`}
      onClose={onClose}
      tabs={tabs}
      activeTab={tab}
      onTab={setTab}
    >
      {tab === "overview" && <NodeOverview node={node} />}
      {tab === "routes" && <NodeRoutes node={node} />}
      {tab === "probes" && <NodeProbes node={node} />}
      {tab === "pool" && entryRole && <NodePool node={node} />}
    </Drawer>
  );
}

function NodeOverview({ node }) {
  const kv = [
    ["ID", node.id],
    ["Роль", node.role],
    ["Регион", node.region],
    ["Зона", node.zone || "—"],
    ["Public domain", node.public_domain || "—"],
    ["Reality IP", node.reality_ip || "—"],
    ["Is enabled", String(node.is_enabled)],
    ["Is draining", String(node.is_draining)],
    ["Is healthy", String(node.is_healthy)],
    ["Capacity", node.capacity ?? "—"],
  ];
  return (
    <table className="kv-table">
      <tbody>
        {kv.map(([k, v]) => (
          <tr key={k}><th>{k}</th><td className="mono small">{v}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

function NodeRoutes({ node }) {
  const { data, loading } = useQuery(() => api.get("/routes?limit=500"), { interval: 15000 });
  const routes = (data || []).filter((r) => r.node_id === node.id || r.entry_node_id === node.id);
  if (loading && !routes.length) return <div className="muted">Загрузка…</div>;
  if (!routes.length) return <div className="muted">Маршрутов нет.</div>;
  return (
    <table className="data-table">
      <thead><tr><th>Маршрут</th><th>Направление</th><th>Status</th><th>Weight</th></tr></thead>
      <tbody>
        {routes.map((r) => (
          <tr key={r.id}>
            <td>{r.name}</td>
            <td className="small muted">{r.node_id === node.id ? "backend" : "entry"}</td>
            <td><span className={"chip chip-" + toneOf(r.health_status)}>{r.health_status}</span></td>
            <td className="mono">{r.effective_weight}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function NodeProbes({ node }) {
  const { data, loading } = useQuery(() => api.get("/probe/reports/recent?limit=80"), { interval: 10000 });
  const rows = (data || []).filter((p) => p.node_id === node.id);
  if (loading && !rows.length) return <div className="muted">Загрузка…</div>;
  if (!rows.length) return <div className="muted">Probe-сигналов нет.</div>;
  return (
    <table className="data-table">
      <thead><tr><th>Источник</th><th>Тип</th><th>Status</th><th>Latency</th><th>Время</th></tr></thead>
      <tbody>
        {rows.slice(0, 30).map((p) => (
          <tr key={p.id}>
            <td><span className="chip chip-muted">{p.source}</span></td>
            <td className="small">{p.probe_kind}</td>
            <td>{p.is_reachable ? <span className="chip chip-ok">OK</span> : <span className="chip chip-bad">FAIL</span>}</td>
            <td className="mono">{p.latency_ms ?? "—"}</td>
            <td className="small muted">{p.checked_at ? new Date(p.checked_at).toLocaleTimeString() : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
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
    try { await api.del(`/entry/${node.id}/assignments/${backendId}`); refetch(); }
    catch (e) { alert(e.message); }
  };

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div className="muted small">Backends, закреплённые за этой entry (HAProxy pool)</div>
        <button className="btn-primary" onClick={() => setAdding(true)}>+ Добавить</button>
      </div>
      {loading && !items.length && <div className="muted">Загрузка…</div>}
      {!loading && !items.length && <div className="muted">Пул пуст.</div>}
      {items.length > 0 && (
        <table className="data-table">
          <thead><tr><th>Backend</th><th>Вес</th><th>Rank</th><th>Enabled</th><th></th></tr></thead>
          <tbody>
            {items.map((a) => {
              const n = nodesById[a.backend_node_id];
              return (
                <tr key={a.backend_node_id}>
                  <td>{n ? <span>{n.name}<div className="small muted">{n.region}</div></span> : <span className="mono small">{String(a.backend_node_id).slice(0, 12)}…</span>}</td>
                  <td className="mono">{a.weight}</td>
                  <td className="mono">{a.rank}</td>
                  <td>{a.enabled ? <span className="chip chip-ok">enabled</span> : <span className="chip chip-muted">off</span>}</td>
                  <td>
                    <div className="row-actions">
                      <button className="row-btn" onClick={() => setEditing(a)}>Edit</button>
                      <button className="row-btn" onClick={() => remove(a.backend_node_id)}>Remove</button>
                    </div>
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
          <button className="btn-ghost" onClick={onClose}>Отмена</button>
          <button className="btn-primary" onClick={save} disabled={busy}>{isEdit ? "Сохранить" : "Добавить"}</button>
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
  return "muted";
}
