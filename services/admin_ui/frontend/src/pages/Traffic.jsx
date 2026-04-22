import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";

export function TrafficPage() {
  const [period, setPeriod] = useState("24h");
  const { data, loading, error } = useQuery(
    () => api.get(`/admin/traffic/nodes?period=${period}&limit=100`).catch((e) => {
      if (e.status === 404) return { items: [] };
      throw e;
    }),
    { interval: 30000, deps: [period] },
  );
  const items = data?.items || [];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Трафик</h1>
          <div className="page-subtitle">Сводный трафик по серверам</div>
        </div>
      </div>

      <div className="filter-row">
        <select className="input" value={period} onChange={(e) => setPeriod(e.target.value)}>
          <option value="1h">1 час</option>
          <option value="24h">24 часа</option>
          <option value="7d">7 дней</option>
          <option value="30d">30 дней</option>
        </select>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Нода</th>
              <th>Роль</th>
              <th>In</th>
              <th>Out</th>
              <th>Сессии</th>
            </tr>
          </thead>
          <tbody>
            {items.map((t, idx) => (
              <tr key={t.node_id || idx}>
                <td>{t.node_name || <span className="mono small">{String(t.node_id).slice(0, 12)}…</span>}</td>
                <td><span className="chip chip-muted">{t.role}</span></td>
                <td className="mono">{formatBytes(t.bytes_in)}</td>
                <td className="mono">{formatBytes(t.bytes_out)}</td>
                <td className="mono">{t.sessions ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Нет данных.</div>}
      </div>
    </div>
  );
}

function formatBytes(n) {
  if (!n) return "0";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0; let v = Number(n);
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}
