import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { useIsMobile } from "../hooks/useIsMobile.js";
import { Icon } from "../components/Icon.jsx";
import { nodeGeo } from "../lib/geo.js";

const DESIRED_TONE = { active: "ok", inactive: "" };
const APPLIED_TONE = { applied: "ok", pending: "warn", error: "bad" };

export function PlacementsPage() {
  const [desired, setDesired] = useState("");
  const [applied, setApplied] = useState("");
  const isMobile = useIsMobile();

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

  const counts = useMemo(() => {
    const list = placements.data || [];
    return {
      total: list.length,
      applied: list.filter((p) => p.applied_state === "applied").length,
      pending: list.filter((p) => p.applied_state === "pending").length,
      error: list.filter((p) => p.applied_state === "error").length,
    };
  }, [placements.data]);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Плейсменты</h1>
          <div className="page-subtitle">
            {counts.total} всего · {counts.applied} applied · {counts.pending} pending · {counts.error} error
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={placements.refetch}><Icon name="refresh" size={13} /> Обновить</button>
        </div>
      </div>

      <div className="filterbar">
        <select className="select" value={desired} onChange={(e) => setDesired(e.target.value)}>
          <option value="">Любой desired</option>
          <option value="active">active</option>
          <option value="inactive">inactive</option>
        </select>
        <select className="select" value={applied} onChange={(e) => setApplied(e.target.value)}>
          <option value="">Любой applied</option>
          <option value="applied">applied</option>
          <option value="pending">pending</option>
          <option value="error">error</option>
        </select>
        <div style={{ marginLeft: "auto" }}>
          <span className="muted text-xs">{rows.length} / {counts.total}</span>
        </div>
      </div>

      {isMobile ? (
        <div className="m-cardlist">
          {rows.map((p) => {
            const n = nodesById[p.backend_node_id];
            const geo = n ? nodeGeo(n.region) : null;
            return (
              <div key={p.id} className="m-card">
                <div className="m-card-head">
                  <div className="m-card-title">
                    <div className="m-card-name">
                      {geo && <span style={{ marginRight: 6 }}>{geo.flag}</span>}
                      {n?.name || <span className="mono">{String(p.backend_node_id).slice(0, 12)}…</span>}
                    </div>
                    <div className="mono muted m-card-id">key {String(p.key_id).slice(0, 12)}…</div>
                  </div>
                </div>
                <div className="m-card-meta">
                  <span className={"pill small " + (DESIRED_TONE[p.desired_state] || "")}>desired: {p.desired_state}</span>
                  <span className={"pill small " + (APPLIED_TONE[p.applied_state] || "")}>applied: {p.applied_state}</span>
                  <span className="mono small">v {p.applied_version}/{p.op_version}</span>
                </div>
                {p.last_migration_reason && (
                  <div className="m-card-body">
                    <div className="m-card-row">
                      <span className="m-card-label">Причина</span>
                      <span className="small muted">{p.last_migration_reason}</span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {(placements.loading && !rows.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
          {(!placements.loading && !rows.length) && <div className="muted" style={{ padding: 14 }}>Нет плейсментов.</div>}
        </div>
      ) : (
      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              <th>Key</th>
              <th>Backend</th>
              <th>Desired</th>
              <th>Applied</th>
              <th style={{ textAlign: "right" }}>Версия</th>
              <th>Причина</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const n = nodesById[p.backend_node_id];
              const geo = n ? nodeGeo(n.region) : null;
              return (
                <tr key={p.id}>
                  <td className="mono muted" style={{ fontSize: 11 }}>{String(p.key_id).slice(0, 12)}…</td>
                  <td>
                    {n ? (
                      <>
                        <span style={{ marginRight: 6 }}>{geo.flag}</span>
                        <span style={{ fontWeight: 500 }}>{n.name}</span>
                        <div className="mono muted" style={{ fontSize: 11 }}>{n.region}</div>
                      </>
                    ) : (
                      <span className="mono muted" style={{ fontSize: 11 }}>{String(p.backend_node_id).slice(0, 12)}…</span>
                    )}
                  </td>
                  <td><span className={"pill " + (DESIRED_TONE[p.desired_state] || "")}>{p.desired_state}</span></td>
                  <td><span className={"pill " + (APPLIED_TONE[p.applied_state] || "")}>{p.applied_state}</span></td>
                  <td className="tbl-num mono">{p.applied_version}/{p.op_version}</td>
                  <td className="small muted">{p.last_migration_reason || "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(placements.loading && !rows.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!placements.loading && !rows.length) && <div className="muted" style={{ padding: 14 }}>Нет плейсментов.</div>}
      </div>
      )}
    </div>
  );
}
