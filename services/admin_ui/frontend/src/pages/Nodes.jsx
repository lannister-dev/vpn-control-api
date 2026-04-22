import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { NodeDrawer } from "../components/NodeDrawer.jsx";

export function NodesPage() {
  const { data: status, loading, error } = useQuery(() => api.get("/admin/status"), { interval: 15000 });
  const nodes = status?.nodes || [];
  const [selected, setSelected] = useState(null);

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Серверы</h1>
        <div className="page-subtitle">Все ноды флота с их ролями, регионами и состоянием агента</div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Имя</th>
              <th>Роль</th>
              <th>Регион</th>
              <th>Зона</th>
              <th>Состояние</th>
              <th>Healthy</th>
              <th>Public IP</th>
            </tr>
          </thead>
          <tbody>
            {nodes.map((n) => (
              <tr key={n.id} style={{ cursor: "pointer" }} onClick={() => setSelected(n)}>
                <td><strong>{n.name}</strong><div className="mono muted small">{n.id.slice(0, 8)}…</div></td>
                <td>{n.role}</td>
                <td className="mono">{n.region}</td>
                <td className="mono">{n.zone || "—"}</td>
                <td>{stateBadge(n)}</td>
                <td>{healthyBadge(n.is_healthy)}</td>
                <td className="mono small">{n.public_domain || n.reality_ip || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && !nodes.length && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {!loading && !nodes.length && <div className="muted" style={{ padding: 14 }}>Нет нод.</div>}
      </div>

      {selected && <NodeDrawer node={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function stateBadge(n) {
  if (!n.is_enabled) return <span className="chip chip-bad">disabled</span>;
  if (n.is_draining) return <span className="chip chip-warn">draining</span>;
  return <span className="chip chip-ok">active</span>;
}
function healthyBadge(h) {
  return h ? <span className="chip chip-ok">OK</span> : <span className="chip chip-bad">FAIL</span>;
}
