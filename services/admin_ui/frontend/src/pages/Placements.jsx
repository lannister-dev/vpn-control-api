import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";

const DESIRED_TONE = { active: "ok", inactive: "muted" };
const APPLIED_TONE = { applied: "ok", pending: "warn", error: "bad" };

export function PlacementsPage() {
  const [desired, setDesired] = useState("");
  const [applied, setApplied] = useState("");

  const placements = useQuery(() => api.get("/placements?limit=500"), { interval: 15000 });
  const status = useQuery(() => api.get("/admin/status"), { interval: 15000 });
  const nodesById = useMemo(
    () => Object.fromEntries((status.data?.nodes || []).map((n) => [n.id, n])),
    [status.data],
  );

  const rows = useMemo(() => {
    let list = placements.data || [];
    if (desired) list = list.filter((p) => p.desired_state === desired);
    if (applied) list = list.filter((p) => p.applied_state === applied);
    return list;
  }, [placements.data, desired, applied]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Плейсменты</h1>
          <div className="page-subtitle">Ключ → backend-нода, желаемое и применённое состояние</div>
        </div>
      </div>

      <div className="filter-row">
        <select className="input" value={desired} onChange={(e) => setDesired(e.target.value)}>
          <option value="">Любой desired</option>
          <option value="active">active</option>
          <option value="inactive">inactive</option>
        </select>
        <select className="input" value={applied} onChange={(e) => setApplied(e.target.value)}>
          <option value="">Любой applied</option>
          <option value="applied">applied</option>
          <option value="pending">pending</option>
          <option value="error">error</option>
        </select>
      </div>

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Key</th>
              <th>Backend</th>
              <th>Desired</th>
              <th>Applied</th>
              <th>Версия</th>
              <th>Причина</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const n = nodesById[p.backend_node_id];
              return (
                <tr key={p.id}>
                  <td className="mono small">{String(p.key_id).slice(0, 12)}…</td>
                  <td>{n ? <span>{n.name}<div className="small muted">{n.region}</div></span> : <span className="mono small">{String(p.backend_node_id).slice(0, 12)}…</span>}</td>
                  <td><span className={"chip chip-" + (DESIRED_TONE[p.desired_state] || "muted")}>{p.desired_state}</span></td>
                  <td><span className={"chip chip-" + (APPLIED_TONE[p.applied_state] || "muted")}>{p.applied_state}</span></td>
                  <td className="mono">{p.applied_version}/{p.op_version}</td>
                  <td className="small muted">{p.last_migration_reason || "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(placements.loading && !rows.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!placements.loading && !rows.length) && <div className="muted" style={{ padding: 14 }}>Нет плейсментов.</div>}
      </div>
    </div>
  );
}
