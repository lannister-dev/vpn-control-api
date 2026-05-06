import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { SubscriptionDrawer } from "../components/SubscriptionDrawer.jsx";
import { SubscriptionCreateModal } from "../components/SubscriptionCreateModal.jsx";
import { StatusPill, deriveSubStatus } from "../components/users/StatusPill.jsx";
import { TrafficBar } from "../components/users/TrafficBar.jsx";
import { DaysCountdown, daysLeft } from "../components/users/DaysCountdown.jsx";
import "../components/users/users.css";

export function SubscriptionsPage() {
  const [activeOnly, setActiveOnly] = useState(false);
  const [planFilter, setPlanFilter] = useState("");
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);

  const qs = new URLSearchParams({ limit: "100" });
  if (activeOnly) qs.set("active_only", "true");
  if (planFilter) qs.set("plan_id", planFilter);

  const q = useQuery(
    () => api.get(`/subscriptions?${qs.toString()}`),
    { interval: 30000, deps: [activeOnly, planFilter] },
  );
  const stats = useQuery(() => api.get("/subscriptions/stats").catch(() => null), { interval: 60000 });
  const plans = useQuery(() => api.get("/plans"), { interval: 60000 });
  const plansById = useMemo(
    () => Object.fromEntries((plans.data?.items || []).map((p) => [p.id, p])),
    [plans.data],
  );

  const items = q.data?.items || [];

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Подписки</h1>
          <div className="page-subtitle">{q.data?.total ?? 0} всего</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={q.refetch}><Icon name="refresh" size={13} /> Обновить</button>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            <Icon name="plus" size={13} /> Создать
          </button>
        </div>
      </div>

      {stats.data && (
        <div className="u-kpi-bar">
          <div className="u-kpi">
            <div className="u-kpi-label"><Icon name="key" size={11} /> Активные</div>
            <div className="u-kpi-val">{stats.data.active}</div>
          </div>
          <div className={"u-kpi" + (stats.data.expired ? " warn" : "")}>
            <div className="u-kpi-label"><Icon name="clock" size={11} /> Истекли</div>
            <div className="u-kpi-val">{stats.data.expired}</div>
          </div>
          <div className="u-kpi">
            <div className="u-kpi-label"><Icon name="bar-chart" size={11} /> Всего</div>
            <div className="u-kpi-val">{stats.data.total}</div>
          </div>
          <div className="u-kpi">
            <div className="u-kpi-label"><Icon name="wallet" size={11} /> Тарифы</div>
            <div className="u-kpi-val">{plans.data?.items?.length ?? 0}</div>
          </div>
        </div>
      )}

      <div className="u-filter-bar">
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "var(--text-secondary)", cursor: "pointer" }}>
          <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} /> Только активные
        </label>
        <select className="select" value={planFilter} onChange={(e) => setPlanFilter(e.target.value)}>
          <option value="">Любой тариф</option>
          {(plans.data?.items || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <div style={{ marginLeft: "auto" }}>
          <span className="muted text-xs">{items.length} / {q.data?.total ?? 0}</span>
        </div>
      </div>

      {q.error && <div className="card card-bad">Ошибка: {q.error.message}</div>}

      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              <th>ID</th>
              <th>Тариф</th>
              <th>Статус</th>
              <th>Трафик</th>
              <th>Осталось</th>
              <th>Регион</th>
              <th style={{ textAlign: "right" }}>Устройств</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => {
              const plan = s.plan_id ? plansById[s.plan_id] : null;
              const status = deriveSubStatus(s);
              const days = daysLeft(s.expires_at);
              const cap = plan?.traffic_limit_bytes || (plan?.traffic_limit_mb ? plan.traffic_limit_mb * 1024 * 1024 : null);
              return (
                <tr key={s.id} style={{ cursor: "pointer" }} onClick={() => setSelected(s)}>
                  <td className="mono muted" style={{ fontSize: 11 }}>{String(s.id).slice(0, 12)}…</td>
                  <td style={{ fontWeight: 500 }}>
                    {plan ? plan.name : (s.plan_name || <span className="muted">—</span>)}
                  </td>
                  <td><StatusPill status={status} /></td>
                  <td style={{ minWidth: 180 }}>
                    {cap ? (
                      <TrafficBar used={s.used_traffic_bytes || 0} cap={cap} />
                    ) : (
                      <span className="mono small muted">∞</span>
                    )}
                  </td>
                  <td><DaysCountdown days={days} /></td>
                  <td className="mono">{s.preferred_region || "—"}</td>
                  <td className="tbl-num mono">{s.max_devices ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(q.loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!q.loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Подписок нет.</div>}
      </div>

      {selected && <SubscriptionDrawer subscription={selected} onClose={() => setSelected(null)} onChanged={q.refetch} />}
      {creating && (
        <SubscriptionCreateModal
          plans={plans.data}
          onClose={() => setCreating(false)}
          onCreated={() => { setCreating(false); q.refetch(); stats.refetch(); }}
        />
      )}
    </div>
  );
}
