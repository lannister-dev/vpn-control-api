import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";

const HEALTH_TONE = {
  healthy: "ok", warming_up: "warn", degraded: "warn", suspected: "warn", blocked: "bad",
};

export function RoutesPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const routes = useQuery(() => api.get("/routes?limit=500"), { interval: 15000 });
  const status = useQuery(() => api.get("/admin/status"), { interval: 15000 });

  const nodesById = useMemo(
    () => Object.fromEntries((status.data?.nodes || []).map((n) => [n.id, n])),
    [status.data],
  );

  const rows = useMemo(() => {
    let list = routes.data || [];
    if (statusFilter) list = list.filter((r) => r.health_status === statusFilter);
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((r) => r.name.toLowerCase().includes(q) || r.id.includes(q) || r.node_id.includes(q));
    }
    return list;
  }, [routes.data, search, statusFilter]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Маршруты</h1>
          <div className="page-subtitle">Маршруты трафика клиент → (entry) → backend</div>
        </div>
      </div>

      <div className="filter-row">
        <input className="input" placeholder="Поиск UUID / имя" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Любой статус</option>
          {Object.keys(HEALTH_TONE).map((h) => <option key={h} value={h}>{h}</option>)}
        </select>
      </div>

      {routes.error && <div className="card card-bad">Ошибка: {routes.error.message}</div>}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Маршрут</th>
              <th>Backend</th>
              <th>Entry</th>
              <th>Status</th>
              <th>Weight</th>
              <th>Активен</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td><strong>{r.name}</strong><div className="small mono">{r.id.slice(0, 8)}…</div></td>
                <td>{nodeLabel(nodesById[r.node_id]) || <span className="muted small">{r.node_id.slice(0, 8)}…</span>}</td>
                <td>{r.entry_node_id ? nodeLabel(nodesById[r.entry_node_id]) : <span className="muted">—</span>}</td>
                <td><span className={"chip chip-" + (HEALTH_TONE[r.health_status] || "muted")}>{r.health_status}</span></td>
                <td className="mono">{r.effective_weight}/{r.base_weight}</td>
                <td>{r.is_active ? <span className="chip chip-ok">active</span> : <span className="chip chip-muted">off</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(routes.loading && !rows.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!routes.loading && !rows.length) && <div className="muted" style={{ padding: 14 }}>Нет маршрутов под фильтр.</div>}
      </div>
    </div>
  );
}

function nodeLabel(n) {
  if (!n) return null;
  return <span>{n.name}<div className="small muted">{n.region}</div></span>;
}
