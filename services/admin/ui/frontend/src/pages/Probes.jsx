import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { nodeGeo } from "../lib/geo.js";

const KIND_LABEL = { synthetic_vpn: "Synthetic", tcp_connect: "TCP" };

export function ProbesPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [kind, setKind] = useState("");
  const { data, loading, error, refetch } = useQuery(() => api.get("/probe/reports/recent?limit=200"), { interval: 10000 });
  const nodes = useQuery(() => api.get("/admin/status"), { interval: 30000 });
  const nodesById = useMemo(
    () => Object.fromEntries((nodes.data?.nodes || []).map((n) => [n.id, n])),
    [nodes.data],
  );

  const rows = useMemo(() => {
    let list = data || [];
    if (statusFilter === "ok") list = list.filter((p) => p.is_reachable);
    if (statusFilter === "failed") list = list.filter((p) => !p.is_reachable);
    if (kind) list = list.filter((p) => p.probe_kind === kind);
    return list;
  }, [data, statusFilter, kind]);

  const counts = useMemo(() => {
    const list = data || [];
    return {
      total: list.length,
      ok: list.filter((p) => p.is_reachable).length,
      fail: list.filter((p) => !p.is_reachable).length,
    };
  }, [data]);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Probes</h1>
          <div className="page-subtitle">
            {counts.total} сигналов · {counts.ok} OK · {counts.fail} FAIL
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={refetch}><Icon name="refresh" size={13} /> Обновить</button>
        </div>
      </div>

      <div className="filterbar">
        <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Любой статус</option>
          <option value="ok">OK</option>
          <option value="failed">FAIL</option>
        </select>
        <select className="select" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">Любой тип</option>
          <option value="synthetic_vpn">Synthetic</option>
          <option value="tcp_connect">TCP</option>
        </select>
        <div style={{ marginLeft: "auto" }}>
          <span className="muted text-xs">{rows.length} / {counts.total}</span>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              <th>Источник</th>
              <th>Нода</th>
              <th>Тип</th>
              <th>Статус</th>
              <th style={{ textAlign: "right" }}>Latency</th>
              <th>Ошибка</th>
              <th>Время</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const n = nodesById[p.node_id];
              const role = n && String(n.role || "").toLowerCase();
              const viaEntry = p.probe_kind === "synthetic_vpn" && (role === "entry" || role === "whitelist_entry");
              const kindLabel = p.probe_kind === "synthetic_vpn"
                ? `Synthetic · ${viaEntry ? "via entry" : "direct"}`
                : KIND_LABEL[p.probe_kind] || p.probe_kind;
              const geo = n ? nodeGeo(n.region) : null;
              const lat = p.latency_ms;
              const latColor = lat == null ? "var(--text-muted)" : lat > 200 ? "var(--bad)" : lat > 80 ? "var(--warn)" : "var(--text)";
              return (
                <tr key={p.id}>
                  <td><span className="pill">{p.source}</span></td>
                  <td>
                    {n ? (
                      <>
                        <span style={{ marginRight: 6 }}>{geo.flag}</span>
                        <span style={{ fontWeight: 500 }}>{n.name}</span>
                        <div className="mono muted" style={{ fontSize: 11 }}>{n.region}</div>
                      </>
                    ) : (
                      <span className="mono muted" style={{ fontSize: 11 }}>{String(p.node_id).slice(0, 12)}…</span>
                    )}
                  </td>
                  <td className="small">{kindLabel}</td>
                  <td>
                    {p.is_reachable
                      ? <span className="pill ok"><span className="status-dot ok" /> OK</span>
                      : <span className="pill bad"><span className="status-dot bad" /> FAIL</span>}
                  </td>
                  <td className="tbl-num mono" style={{ color: latColor }}>{lat != null ? `${lat}ms` : "—"}</td>
                  <td className="small muted" style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={p.error || ""}>{p.error || "—"}</td>
                  <td className="small muted mono">{p.checked_at ? new Date(p.checked_at).toLocaleTimeString() : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(loading && !rows.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!loading && !rows.length) && <div className="muted" style={{ padding: 14 }}>Нет probe-сигналов.</div>}
      </div>
    </div>
  );
}
