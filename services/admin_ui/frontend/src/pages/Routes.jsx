import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Topology } from "../components/Topology.jsx";
import { Icon } from "../components/Icon.jsx";

const HEALTH_TONE = {
  healthy: "ok", warming_up: "warn", degraded: "warn", suspected: "warn", blocked: "bad",
};

export function RoutesPage() {
  const [view, setView] = useState("topology");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

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
            {counts.healthy} healthy · {counts.warn} degraded · {counts.bad} blocked · {counts.other} warming/other
          </div>
        </div>
        <div className="page-head-actions">
          <div className="seg" style={{ minWidth: 160 }}>
            <button data-active={view === "topology"} onClick={() => setView("topology")}>Поток</button>
            <button data-active={view === "list"} onClick={() => setView("list")}>Список</button>
          </div>
        </div>
      </div>

      {routes.error && <div className="card card-bad">Ошибка: {routes.error.message}</div>}

      {view === "topology" ? (
        <Topology routes={routesList} nodes={nodes} probes={probes.data || []} />
      ) : (
        <RoutesList routesList={routesList} nodesById={nodesById} search={search} setSearch={setSearch} statusFilter={statusFilter} setStatusFilter={setStatusFilter} loading={routes.loading} />
      )}
    </div>
  );
}

function RoutesList({ routesList, nodesById, search, setSearch, statusFilter, setStatusFilter, loading }) {
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
      <div className="filter-row">
        <input className="input" placeholder="Поиск UUID / имя" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Любой статус</option>
          {Object.keys(HEALTH_TONE).map((h) => <option key={h} value={h}>{h}</option>)}
        </select>
      </div>

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Маршрут</th>
              <th>Backend</th>
              <th>Entry</th>
              <th>Status</th>
              <th>Weight</th>
              <th>Active</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td><strong>{r.name}</strong><div className="small mono">{r.id.slice(0, 8)}…</div></td>
                <td>{nodeLabel(nodesById[r.node_id])}</td>
                <td>{r.entry_node_id ? nodeLabel(nodesById[r.entry_node_id]) : <span className="muted">—</span>}</td>
                <td><span className={"chip chip-" + (HEALTH_TONE[r.health_status] || "muted")}>{r.health_status}</span></td>
                <td className="mono">{r.effective_weight}/{r.base_weight}</td>
                <td>{r.is_active ? <span className="chip chip-ok">active</span> : <span className="chip chip-muted">off</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(loading && !rows.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!loading && !rows.length) && <div className="muted" style={{ padding: 14 }}>Нет маршрутов.</div>}
      </div>
    </>
  );
}

function nodeLabel(n) {
  if (!n) return <span className="muted small">—</span>;
  return <span>{n.name}<div className="small muted">{n.region}</div></span>;
}
