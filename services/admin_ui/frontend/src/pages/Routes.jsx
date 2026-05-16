import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Topology } from "../components/Topology.jsx";
import { Icon } from "../components/Icon.jsx";
import { RouteForm } from "../components/RouteForm.jsx";
import { Empty } from "../components/Empty.jsx";

const HEALTH_TONE = {
  healthy: "ok", warming_up: "warn", degraded: "warn", suspected: "warn", blocked: "bad",
};

export function RoutesPage({ initialAction, onActionConsumed, onOpenNode }) {
  const [view, setView] = useState("topology");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);

  useEffect(() => {
    if (initialAction === "create") { setCreating(true); onActionConsumed?.(); }
  }, [initialAction, onActionConsumed]);

  const routes = useQuery(() => api.get("/routes?limit=500"), { interval: 15000 });
  const status = useQuery(() => api.get("/admin/status"), { interval: 15000 });
  const probes = useQuery(() => api.get("/probe/reports/recent?limit=200"), { interval: 15000 });
  const dist = useQuery(
    () => api.get("/subscriptions/route-assignments/distribution").catch(() => []),
    { interval: 30000 },
  );
  const loadByEntryId = useMemo(() => {
    const m = {};
    for (const r of (Array.isArray(dist.data) ? dist.data : [])) {
      m[r.entry_node_id] = r;
    }
    return m;
  }, [dist.data]);
  const routingState = useQuery(
    () => api.get("/admin/routing/entry/state").catch(() => null),
    { interval: 30000 },
  );

  const nodes = status.data?.nodes || [];
  const nodesById = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);
  const routesList = routes.data || [];

  const userCountByBackendName = useMemo(() => {
    const counts = {};
    for (const k of routingState.data?.keys || []) {
      const tag = k.effective_backend;
      if (!tag) continue;
      const name = tag.startsWith("backend-") ? tag.slice("backend-".length) : tag;
      counts[name] = (counts[name] || 0) + 1;
    }
    return counts;
  }, [routingState.data]);

  const liveByBackendName = useMemo(() => {
    const counts = {};
    for (const item of routingState.data?.live || []) {
      const name = item.tag?.startsWith("backend-") ? item.tag.slice("backend-".length) : item.tag;
      if (name) counts[name] = (counts[name] || 0) + (item.connections || 0);
    }
    return counts;
  }, [routingState.data]);

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
        <Topology
          routes={routesList}
          nodes={nodes}
          probes={probes.data || []}
          userCountByBackendName={userCountByBackendName}
          liveByBackendName={liveByBackendName}
          onOpenNode={onOpenNode}
        />
      ) : (
        <RoutesList
          routesList={routesList}
          nodesById={nodesById}
          loadByEntryId={loadByEntryId}
          search={search} setSearch={setSearch}
          statusFilter={statusFilter} setStatusFilter={setStatusFilter}
          loading={routes.loading}
          onOpenNode={onOpenNode}
          onEdit={setEditing}
        />
      )}

      {creating && <RouteForm nodes={nodes} onClose={() => { setCreating(false); routes.refetch(); }} />}
      {editing && <RouteForm route={editing} nodes={nodes} onClose={() => { setEditing(null); routes.refetch(); }} />}
    </div>
  );
}

function RoutesList({ routesList, nodesById, loadByEntryId = {}, search, setSearch, statusFilter, setStatusFilter, loading, onOpenNode, onEdit }) {
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
            {rows.map((r) => {
              const backendNode = nodesById[r.node_id];
              const entryNode = r.entry_node_id ? nodesById[r.entry_node_id] : null;
              const openInBackend = () => onOpenNode && backendNode && onOpenNode(backendNode, { initialTab: "routes", focusRouteId: r.id });
              const openInEntry = () => onOpenNode && entryNode && onOpenNode(entryNode, { initialTab: "routes", focusRouteId: r.id });
              const openEntryPool = (e) => {
                e.stopPropagation();
                if (onOpenNode && entryNode) onOpenNode(entryNode, { initialTab: "pool" });
              };
              return (
                <tr key={r.id} style={{ opacity: r.is_active ? 1 : 0.55 }}>
                  <td style={{ fontWeight: 500 }}>{r.name}<div className="mono muted" style={{ fontSize: 11 }}>{r.id.slice(0, 8)}…</div></td>
                  <td>
                    <span
                      onClick={openInBackend}
                      style={{ cursor: backendNode ? "pointer" : "default" }}
                      title={backendNode ? "Открыть ноду с фокусом на этот маршрут" : ""}
                    >
                      {nodeLabel(backendNode)}
                    </span>
                  </td>
                  <td>
                    {entryNode ? (
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                        <span
                          onClick={openInEntry}
                          style={{ cursor: "pointer" }}
                          title="Открыть entry-ноду"
                        >
                          {nodeLabel(entryNode)}
                        </span>
                        {(() => {
                          const d = loadByEntryId[entryNode.id];
                          if (!d) return null;
                          const tone = d.load_pct > 85 ? "var(--bad)" : d.load_pct > 65 ? "var(--warn)" : "var(--text-muted)";
                          return (
                            <span
                              className="pill small"
                              title={`${d.subscription_count} подписок · ${d.device_count} устройств · ${d.load_pct != null ? d.load_pct + "%" : "—"} от capacity`}
                              style={{ color: tone }}
                            >
                              👥 {d.subscription_count}
                              {d.load_pct != null && <span className="muted" style={{ marginLeft: 4 }}>{d.load_pct}%</span>}
                            </span>
                          );
                        })()}
                        <button
                          className="row-btn"
                          onClick={openEntryPool}
                          title="Открыть pool этой entry"
                          style={{ padding: "2px 6px", fontSize: 11 }}
                        >
                          Pool
                        </button>
                      </span>
                    ) : <span className="muted">—</span>}
                  </td>
                  <td>
                    {r.is_active
                      ? <span className={"pill " + (HEALTH_TONE[r.health_status] || "")}><span className={`status-dot ${HEALTH_TONE[r.health_status] || "muted"}`} /> {r.health_status}</span>
                      : <span className="pill muted">не активен</span>}
                  </td>
                  <td className="tbl-num mono">{r.effective_weight}/{r.base_weight}</td>
                  <td>{r.is_active ? <span className="pill ok">active</span> : <span className="pill muted">off</span>}</td>
                  <td className="row-actions">
                    {backendNode && (
                      <button
                        className="row-btn"
                        onClick={openInBackend}
                        title="Открыть в ноде"
                      >
                        <Icon name="arrow-right" size={11} /> Нода
                      </button>
                    )}
                    <button className="row-btn" onClick={() => onEdit && onEdit(r)}>Edit</button>
                  </td>
                </tr>
              );
            })}
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

