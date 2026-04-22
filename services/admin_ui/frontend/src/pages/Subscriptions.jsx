import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { SubscriptionDrawer } from "../components/SubscriptionDrawer.jsx";
import { Icon } from "../components/Icon.jsx";

export function SubscriptionsPage() {
  const [userId, setUserId] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [selected, setSelected] = useState(null);

  const query = userId ? `/subscriptions/by-user/${encodeURIComponent(userId)}?active_only=${activeOnly}` : null;
  const { data, loading, error, refetch } = useQuery(() => (query ? api.get(query) : Promise.resolve([])), {
    interval: 0,
    deps: [query],
  });
  const items = Array.isArray(data) ? data : (data?.items || []);

  const plans = useQuery(() => api.get("/plans"), { interval: 60000 });
  const plansById = Object.fromEntries((plans.data?.items || []).map((p) => [p.id, p]));

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Подписки</h1>
          <div className="page-subtitle">Поиск подписок пользователя по UUID</div>
        </div>
      </div>

      <div className="filterbar">
        <div className="input-search-wrap">
          <Icon name="search" size={13} className="input-search-icon" />
          <input className="input" placeholder="User UUID" value={userId} onChange={(e) => setUserId(e.target.value.trim())} />
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "var(--text-secondary)", cursor: "pointer" }}>
          <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} /> Только активные
        </label>
        {userId && <span className="muted text-xs" style={{ marginLeft: "auto" }}>{items.length} записей</span>}
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              <th>ID</th>
              <th>Тариф</th>
              <th>Регион</th>
              <th style={{ textAlign: "right" }}>Устройств</th>
              <th>Истекает</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.id} style={{ cursor: "pointer" }} onClick={() => setSelected(s)}>
                <td className="mono muted" style={{ fontSize: 11 }}>{String(s.id).slice(0, 12)}…</td>
                <td style={{ fontWeight: 500 }}>{s.plan_id ? (plansById[s.plan_id]?.name || String(s.plan_id).slice(0, 8) + "…") : <span className="muted">—</span>}</td>
                <td className="mono">{s.preferred_region || "—"}</td>
                <td className="tbl-num mono">{s.max_devices ?? "—"}</td>
                <td className="small muted">{s.expires_at ? new Date(s.expires_at).toLocaleDateString() : "—"}</td>
                <td>{s.is_active ? <span className="pill ok">active</span> : <span className="pill">inactive</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!userId && <div className="muted" style={{ padding: 14 }}>Введите User UUID для поиска.</div>}
        {userId && loading && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {userId && !loading && !items.length && <div className="muted" style={{ padding: 14 }}>У пользователя нет подписок.</div>}
      </div>

      {selected && <SubscriptionDrawer subscription={selected} onClose={() => setSelected(null)} onChanged={refetch} />}
    </div>
  );
}
