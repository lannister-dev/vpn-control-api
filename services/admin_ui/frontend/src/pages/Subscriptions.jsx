import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";

export function SubscriptionsPage() {
  const [userId, setUserId] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);

  const query = userId ? `/subscriptions?user_id=${encodeURIComponent(userId)}&active_only=${activeOnly}` : null;
  const { data, loading, error } = useQuery(() => (query ? api.get(query) : Promise.resolve([])), {
    interval: 0,
    deps: [query],
  });
  const items = Array.isArray(data) ? data : (data?.items || []);

  const plans = useQuery(() => api.get("/plans"), { interval: 60000 });
  const plansById = Object.fromEntries((plans.data?.items || []).map((p) => [p.id, p]));

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Подписки</h1>
          <div className="page-subtitle">Поиск подписок пользователя по UUID</div>
        </div>
      </div>

      <div className="filter-row">
        <input className="input" placeholder="User UUID" value={userId} onChange={(e) => setUserId(e.target.value.trim())} />
        <label className="muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} /> Только активные
        </label>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Тариф</th>
              <th>Регион</th>
              <th>Устройств</th>
              <th>Истекает</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.id}>
                <td className="mono small">{String(s.id).slice(0, 12)}…</td>
                <td>{s.plan_id ? (plansById[s.plan_id]?.name || s.plan_id.slice(0, 8) + "…") : <span className="muted">—</span>}</td>
                <td className="mono">{s.preferred_region || "—"}</td>
                <td className="mono">{s.max_devices ?? "—"}</td>
                <td className="small muted">{s.expires_at ? new Date(s.expires_at).toLocaleDateString() : "—"}</td>
                <td>{s.is_active ? <span className="chip chip-ok">active</span> : <span className="chip chip-muted">inactive</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!userId && <div className="muted" style={{ padding: 14 }}>Введите User UUID для поиска.</div>}
        {userId && loading && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {userId && !loading && !items.length && <div className="muted" style={{ padding: 14 }}>У пользователя нет подписок.</div>}
      </div>
    </div>
  );
}
