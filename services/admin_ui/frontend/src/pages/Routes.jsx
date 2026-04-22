import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Topology } from "../components/Topology.jsx";
import { Icon } from "../components/Icon.jsx";
import { NodeDrawer } from "../components/NodeDrawer.jsx";
import { Modal } from "../components/Modal.jsx";
import { Field } from "../components/Field.jsx";
import { toast } from "../components/Toast.jsx";
import { Empty } from "../components/Empty.jsx";

const HEALTH_TONE = {
  healthy: "ok", warming_up: "warn", degraded: "warn", suspected: "warn", blocked: "bad",
};

export function RoutesPage() {
  const [view, setView] = useState("topology");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [drawerNode, setDrawerNode] = useState(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);

  const routes = useQuery(() => api.get("/routes?limit=500"), { interval: 15000 });
  const status = useQuery(() => api.get("/admin/status"), { interval: 15000 });
  const probes = useQuery(() => api.get("/probe/reports/recent?limit=200"), { interval: 15000 });

  const nodes = status.data?.nodes || [];
  const nodesById = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);
  const routesList = routes.data || [];

  const counts = useMemo(() => {
    const c = { healthy: 0, warn: 0, bad: 0, other: 0 };
    for (const r of routesList) {
      if (r.health_status === "healthy") c.healthy++;
      else if (r.health_status === "blocked") c.bad++;
      else if (r.health_status === "degraded" || r.health_status === "suspected") c.warn++;
      else c.other++;
    }
    return c;
  }, [routesList]);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Маршруты</h1>
          <div className="page-subtitle">
            {routesList.length} активных маршрутов{counts.bad ? ` · ${counts.bad} blocked` : ""}{counts.other ? ` · ${counts.other} warming up` : ""}
          </div>
        </div>
        <div className="page-head-actions">
          <div className="seg" style={{ minWidth: 160 }}>
            <button data-active={view === "topology"} onClick={() => setView("topology")}><Icon name="git-branch" size={12} /> Поток</button>
            <button data-active={view === "list"} onClick={() => setView("list")}><Icon name="list" size={12} /> Список</button>
          </div>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            <Icon name="plus" size={13} /> Создать маршрут
          </button>
        </div>
      </div>

      {routes.error && <div className="card card-bad">Ошибка: {routes.error.message}</div>}

      {view === "topology" ? (
        <Topology routes={routesList} nodes={nodes} probes={probes.data || []} onOpenNode={setDrawerNode} />
      ) : (
        <RoutesList
          routesList={routesList}
          nodesById={nodesById}
          search={search} setSearch={setSearch}
          statusFilter={statusFilter} setStatusFilter={setStatusFilter}
          loading={routes.loading}
          onOpenNode={setDrawerNode}
          onEdit={setEditing}
        />
      )}

      {drawerNode && <NodeDrawer node={drawerNode} onClose={() => setDrawerNode(null)} />}
      {creating && <RouteForm nodes={nodes} onClose={() => { setCreating(false); routes.refetch(); }} />}
      {editing && <RouteForm route={editing} nodes={nodes} onClose={() => { setEditing(null); routes.refetch(); }} />}
    </div>
  );
}

function RoutesList({ routesList, nodesById, search, setSearch, statusFilter, setStatusFilter, loading, onOpenNode, onEdit }) {
  const rows = useMemo(() => {
    let list = routesList;
    if (statusFilter) list = list.filter((r) => r.health_status === statusFilter);
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((r) => r.name.toLowerCase().includes(q) || r.id.includes(q));
    }
    return list;
  }, [routesList, search, statusFilter]);

  return (
    <>
      <div className="filterbar">
        <div className="input-search-wrap">
          <Icon name="search" size={13} className="input-search-icon" />
          <input className="input" placeholder="Поиск UUID / имя" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Любой статус</option>
          {Object.keys(HEALTH_TONE).map((h) => <option key={h} value={h}>{h}</option>)}
        </select>
        <div style={{ marginLeft: "auto" }}>
          <span className="muted text-xs">{rows.length} / {routesList.length}</span>
        </div>
      </div>

      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              <th>Маршрут</th>
              <th>Backend</th>
              <th>Entry</th>
              <th>Status</th>
              <th style={{ textAlign: "right" }}>Weight</th>
              <th>Active</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td style={{ fontWeight: 500 }}>{r.name}<div className="mono muted" style={{ fontSize: 11 }}>{r.id.slice(0, 8)}…</div></td>
                <td><span onClick={() => onOpenNode && onOpenNode(nodesById[r.node_id])} style={{ cursor: onOpenNode ? "pointer" : "default" }}>{nodeLabel(nodesById[r.node_id])}</span></td>
                <td>{r.entry_node_id ? <span onClick={() => onOpenNode && onOpenNode(nodesById[r.entry_node_id])} style={{ cursor: onOpenNode ? "pointer" : "default" }}>{nodeLabel(nodesById[r.entry_node_id])}</span> : <span className="muted">—</span>}</td>
                <td><span className={"pill " + (HEALTH_TONE[r.health_status] || "")}><span className={`status-dot ${HEALTH_TONE[r.health_status] || "muted"}`} /> {r.health_status}</span></td>
                <td className="tbl-num mono">{r.effective_weight}/{r.base_weight}</td>
                <td>{r.is_active ? <span className="pill ok">active</span> : <span className="pill">off</span>}</td>
                <td className="row-actions"><button className="row-btn" onClick={() => onEdit && onEdit(r)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {(loading && !rows.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!loading && !rows.length) && <Empty icon="route" title="Маршрутов нет" hint="Создайте маршрут, чтобы он попал в подписку юзеров." />}
      </div>
    </>
  );
}

function nodeLabel(n) {
  if (!n) return <span className="muted small">—</span>;
  return <span>{n.name}<div className="small muted">{n.region}</div></span>;
}

function RouteForm({ route, nodes, onClose }) {
  const isEdit = !!route;
  const [name, setName] = useState(route?.name || "");
  const [nodeId, setNodeId] = useState(route?.node_id || "");
  const [entryNodeId, setEntryNodeId] = useState(route?.entry_node_id || "");
  const [tpId, setTpId] = useState(route?.transport_profile_id || "");
  const [baseWeight, setBaseWeight] = useState(route?.base_weight ?? 50);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const profiles = useQuery(() => api.get("/routes/transport-profiles?limit=200"), { interval: 0 });
  const profilesList = profiles.data || [];

  const backends = nodes.filter((n) => n.role === "backend");
  const entries = nodes.filter((n) => n.role === "entry" || n.role === "whitelist_entry");

  const save = async () => {
    setBusy(true); setErr("");
    try {
      if (isEdit) {
        const payload = {};
        if (name && name !== route.name) payload.name = name;
        if (nodeId && nodeId !== route.node_id) payload.node_id = nodeId;
        const newEntry = entryNodeId || null;
        if (newEntry !== (route.entry_node_id || null)) payload.entry_node_id = newEntry;
        const w = Number(baseWeight);
        if (!isNaN(w) && w !== route.base_weight) payload.base_weight = w;
        if (Object.keys(payload).length) await api.patch(`/routes/${route.id}`, payload);
      } else {
        if (!name) throw new Error("Имя обязательно");
        if (!nodeId) throw new Error("Backend обязателен");
        if (!tpId) throw new Error("Transport profile обязателен");
        const payload = { name, node_id: nodeId, transport_profile_id: tpId, base_weight: Number(baseWeight) || 50 };
        if (entryNodeId) payload.entry_node_id = entryNodeId;
        await api.post("/routes", payload);
      }
      toast.ok(isEdit ? "Маршрут обновлён" : "Маршрут создан");
      onClose();
    } catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  const deactivate = async () => {
    if (!confirm(`Деактивировать маршрут ${route.name}?`)) return;
    setBusy(true);
    try { await api.del(`/routes/${route.id}`); toast.ok("Маршрут деактивирован"); onClose(); }
    catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <Modal
      title={isEdit ? `Маршрут: ${route.name}` : "Новый маршрут"}
      onClose={onClose}
      footer={
        <>
          {isEdit && <button className="btn btn-danger" onClick={deactivate} disabled={busy} style={{ marginRight: "auto" }}>Деактивировать</button>}
          <button className="btn btn-ghost" onClick={onClose}>Отмена</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>{isEdit ? "Сохранить" : "Создать"}</button>
        </>
      }
    >
      {err && <div className="form-error">{err}</div>}
      <Field label="Имя"><input type="text" value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <Field label="Backend">
        <select value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
          <option value="">— выберите —</option>
          {backends.map((n) => <option key={n.id} value={n.id}>{n.name} · {n.region}</option>)}
        </select>
      </Field>
      <Field label="Entry" hint="опционально">
        <select value={entryNodeId} onChange={(e) => setEntryNodeId(e.target.value)}>
          <option value="">Без entry (direct)</option>
          {entries.map((n) => <option key={n.id} value={n.id}>{n.name} · {n.region} ({n.role})</option>)}
        </select>
      </Field>
      <Field label="Transport profile">
        <select value={tpId} onChange={(e) => setTpId(e.target.value)} disabled={isEdit}>
          <option value="">— выберите —</option>
          {profilesList.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.security}/{p.network})</option>)}
        </select>
      </Field>
      <Field label="Base weight" hint="0–100">
        <input type="number" min={0} max={100} value={baseWeight} onChange={(e) => setBaseWeight(e.target.value)} />
      </Field>
    </Modal>
  );
}
