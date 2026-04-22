import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";

export function PlansPage() {
  const { data, loading, error } = useQuery(() => api.get("/plans"), { interval: 30000 });
  const items = data?.items || [];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Тарифы</h1>
          <div className="page-subtitle">Планы подписок, флаги умной маршрутизации и whitelist</div>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Название</th>
              <th>Трафик</th>
              <th>Сброс</th>
              <th>Устройства</th>
              <th>Длительность</th>
              <th>Флаги</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.id}>
                <td><strong>{p.name}</strong><div className="small muted">{p.description || ""}</div></td>
                <td className="mono">{formatBytes(p.traffic_limit_bytes)}</td>
                <td className="small">{p.reset_strategy}</td>
                <td className="mono">{p.included_devices}/{p.max_devices}</td>
                <td className="mono">{p.duration_days} дн.</td>
                <td>
                  {p.entry_relay_enabled && <span className="chip chip-ok" style={{ marginRight: 4 }}>Entry</span>}
                  {p.whitelist_enabled && <span className="chip chip-ok">WL</span>}
                </td>
                <td>{p.is_active ? <span className="chip chip-ok">active</span> : <span className="chip chip-muted">inactive</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Тарифов нет.</div>}
      </div>
    </div>
  );
}

function formatBytes(n) {
  if (!n) return "Unlimited";
  if (n >= 1024 * 1024 * 1024) return `${(n / 1024 / 1024 / 1024).toFixed(1)} GB`;
  return `${(n / 1024 / 1024).toFixed(0)} MB`;
}
