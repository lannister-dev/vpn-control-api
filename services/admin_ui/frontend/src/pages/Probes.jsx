import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";

const KIND_LABEL = { synthetic_vpn: "Synthetic", tcp_connect: "TCP" };

export function ProbesPage() {
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");
  const { data, loading, error } = useQuery(() => api.get("/probe/reports/recent?limit=80"), { interval: 10000 });
  const nodes = useQuery(() => api.get("/admin/status"), { interval: 30000 });
  const nodesById = useMemo(
    () => Object.fromEntries((nodes.data?.nodes || []).map((n) => [n.id, n])),
    [nodes.data],
  );

  const rows = useMemo(() => {
    let list = data || [];
    if (status === "ok") list = list.filter((p) => p.is_reachable);
    if (status === "failed") list = list.filter((p) => !p.is_reachable);
    if (kind) list = list.filter((p) => p.probe_kind === kind);
    return list;
  }, [data, status, kind]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Probes</h1>
          <div className="page-subtitle">Последние сигналы от probe-агентов (Timeweb РФ)</div>
        </div>
      </div>

      <div className="filter-row">
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Любой статус</option>
          <option value="ok">OK</option>
          <option value="failed">FAIL</option>
        </select>
        <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">Любой тип</option>
          <option value="synthetic_vpn">Synthetic</option>
          <option value="tcp_connect">TCP</option>
        </select>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Источник</th>
              <th>Нода</th>
              <th>Тип</th>
              <th>Статус</th>
              <th>Latency</th>
              <th>Ошибка</th>
              <th>Время</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const n = nodesById[p.node_id];
              const nodeRole = n && String(n.role || "").toLowerCase();
              const viaEntry = p.probe_kind === "synthetic_vpn" && (nodeRole === "entry" || nodeRole === "whitelist_entry");
              const kindLabel = p.probe_kind === "synthetic_vpn"
                ? `Synthetic · ${viaEntry ? "via entry" : "direct"}`
                : KIND_LABEL[p.probe_kind] || p.probe_kind;
              return (
                <tr key={p.id}>
                  <td><span className="chip chip-muted">{p.source}</span></td>
                  <td>{n ? <span>{n.name}<div className="small muted">{n.region}</div></span> : <span className="mono small">{p.node_id.slice(0, 12)}…</span>}</td>
                  <td>{kindLabel}</td>
                  <td>{p.is_reachable ? <span className="chip chip-ok">OK</span> : <span className="chip chip-bad">FAIL</span>}</td>
                  <td className="mono">{p.latency_ms != null ? `${p.latency_ms}ms` : "—"}</td>
                  <td className="small muted" style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={p.error || ""}>{p.error || "—"}</td>
                  <td className="small muted">{p.checked_at ? new Date(p.checked_at).toLocaleTimeString() : ""}</td>
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
