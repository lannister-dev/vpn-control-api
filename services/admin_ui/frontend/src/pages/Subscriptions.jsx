import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { SubscriptionDrawer } from "../components/SubscriptionDrawer.jsx";

function fmtBytes(b) {
  if (!b) return "0";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, n = Number(b);
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return n.toFixed(n >= 100 || i === 0 ? 0 : 1) + " " + u[i];
}

function fmtDate(s) {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("ru-RU"); } catch { return s; }
}

function expiresStatus(expires_at) {
  if (!expires_at) return { label: "бессрочно", tone: "" };
  const d = new Date(expires_at).getTime();
  const now = Date.now();
  if (d < now) return { label: "истекла", tone: "bad" };
  const days = Math.floor((d - now) / 86400000);
  if (days < 3) return { label: `через ${days}д`, tone: "warn" };
  if (days < 7) return { label: `через ${days}д`, tone: "warn" };
  return { label: fmtDate(expires_at), tone: "" };
}

export function SubscriptionsPage() {
  const [activeOnly, setActiveOnly] = useState(false);
  const [planFilter, setPlanFilter] = useState("");
  const [selected, setSelected] = useState(null);

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
          <div className="page-subtitle">
            {stats.data ? `${stats.data.active} активных · ${stats.data.expired} истёкших · ${stats.data.total} всего` : "загрузка…"}
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={q.refetch}><Icon name="refresh" size={13} /> Обновить</button>
        </div>
      </div>

      {stats.data && (
        <div className="sec">
          <div className="kpi-hero">
            <Kpi icon="key" label="Активные" value={stats.data.active} tone="up" />
            <Kpi icon="clock" label="Истекли" value={stats.data.expired} tone={stats.data.expired ? "down" : "flat"} />
            <Kpi icon="bar-chart" label="Всего" value={stats.data.total} tone="flat" />
            <Kpi icon="wallet" label="Тарифы" value={plans.data?.items?.length ?? 0} tone="flat" />
          </div>
        </div>
      )}

      <div className="filterbar">
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
              <th style={{ textAlign: "right" }}>Устройств</th>
              <th>Регион</th>
              <th>Трафик</th>
              <th>Истекает</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => {
              const plan = s.plan_id ? plansById[s.plan_id] : null;
              const exp = expiresStatus(s.expires_at);
              const limitBytes = plan?.traffic_limit_bytes || 0;
              const used = s.used_traffic_bytes || 0;
              const pct = limitBytes > 0 ? Math.min(100, Math.round((used / limitBytes) * 100)) : 0;
              return (
                <tr key={s.id} style={{ cursor: "pointer" }} onClick={() => setSelected(s)}>
                  <td className="mono muted" style={{ fontSize: 11 }}>{String(s.id).slice(0, 12)}…</td>
                  <td style={{ fontWeight: 500 }}>
                    {plan ? plan.name : <span className="muted">—</span>}
                    {s.plan_name && !plan && <span>{s.plan_name}</span>}
                  </td>
                  <td className="tbl-num mono">{s.max_devices ?? "—"}</td>
                  <td className="mono">{s.preferred_region || "—"}</td>
                  <td>
                    {limitBytes > 0 ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 160 }}>
                        <div style={{ flex: 1, height: 5, background: "var(--surface-2)", borderRadius: 3, overflow: "hidden", maxWidth: 120 }}>
                          <div style={{ width: `${pct}%`, height: "100%", background: `var(--${pct > 90 ? "bad" : pct > 70 ? "warn" : "ok"})` }} />
                        </div>
                        <span className="mono small">{fmtBytes(used)} / {fmtBytes(limitBytes)}</span>
                      </div>
                    ) : (
                      <span className="mono small">{fmtBytes(used)} <span className="muted">∞</span></span>
                    )}
                  </td>
                  <td>
                    <span className={`pill ${exp.tone}`}>{exp.label}</span>
                  </td>
                  <td>{s.is_active ? <span className="pill ok">active</span> : <span className="pill">inactive</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(q.loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!q.loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Подписок нет.</div>}
      </div>

      {selected && <SubscriptionDrawer subscription={selected} onClose={() => setSelected(null)} onChanged={q.refetch} />}
    </div>
  );
}

function Kpi({ icon, label, value, unit, tone }) {
  return (
    <div className="kpi-cell">
      <div className="kpi-label"><Icon name={icon} size={12} /> <span>{label}</span></div>
      <div className="kpi-value-row">
        <div className="kpi-value tnum">{value}{unit && <span className="kpi-unit">{unit}</span>}</div>
      </div>
    </div>
  );
}
