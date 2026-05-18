import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { useIsMobile } from "../hooks/useIsMobile.js";
import { Icon } from "../components/Icon.jsx";
import { SubscriptionDrawer } from "../components/SubscriptionDrawer.jsx";
import { SubscriptionCreateModal } from "../components/SubscriptionCreateModal.jsx";
import { StatusPill, deriveSubStatus } from "../components/users/StatusPill.jsx";
import { TrafficBar } from "../components/users/TrafficBar.jsx";
import { DaysCountdown, daysLeft } from "../components/users/DaysCountdown.jsx";
import { FilterPresets } from "../components/users/FilterChip.jsx";
import "../components/users/users.css";

const PRESETS = [
  { id: "all", label: "Все" },
  { id: "active", label: "Активные", icon: "check" },
  { id: "expiring", label: "Истекают (7д)", icon: "clock" },
  { id: "expired", label: "Истекшие", icon: "alert-circle" },
];

function applyPreset(preset, params) {
  switch (preset) {
    case "active": params.set("active_only", "true"); break;
    case "expiring": params.set("expiring_within_days", "7"); break;
    case "expired": params.set("expired_only", "true"); break;
  }
}

function fmtDate(s) {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("ru-RU"); } catch { return s; }
}

export function SubscriptionsPage() {
  const [preset, setPreset] = useState("all");
  const [planFilter, setPlanFilter] = useState("");
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);
  const isMobile = useIsMobile();

  const qs = new URLSearchParams({ limit: "100" });
  if (planFilter) qs.set("plan_id", planFilter);
  applyPreset(preset, qs);

  const q = useQuery(
    () => api.get(`/subscriptions?${qs.toString()}`),
    { interval: 30000, deps: [planFilter, preset] },
  );
  const stats = useQuery(
    () => api.get("/subscriptions/stats").catch(() => null),
    { interval: 60000 },
  );
  const plans = useQuery(() => api.get("/plans"), { interval: 60000 });
  const plansById = useMemo(
    () => Object.fromEntries((plans.data?.items || []).map((p) => [p.id, p])),
    [plans.data],
  );

  const items = q.data?.items || [];
  const total = q.data?.total ?? 0;

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Подписки</h1>
          <div className="page-subtitle">{total.toLocaleString("ru-RU")} всего</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={q.refetch}>
            <Icon name="refresh" size={13} /> Обновить
          </button>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            <Icon name="plus" size={13} /> Создать
          </button>
        </div>
      </div>

      {stats.data && (
        <div className="u-kpi-bar">
          <Kpi icon="key" label="Активных" value={stats.data.active} />
          <Kpi icon="clock" label="Истекшие" value={stats.data.expired} tone={stats.data.expired ? "warn" : ""} />
          <Kpi icon="bar-chart" label="Всего" value={stats.data.total} />
          <Kpi icon="package" label="Тарифов" value={plans.data?.items?.length ?? 0} />
        </div>
      )}

      <div className="u-filter-bar">
        <FilterPresets items={PRESETS} value={preset} onPick={setPreset} />
        <select
          className="select"
          value={planFilter}
          onChange={(e) => setPlanFilter(e.target.value)}
          style={{ marginLeft: "auto" }}
        >
          <option value="">Любой тариф</option>
          {(plans.data?.items || []).map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      {q.error && <div className="card card-bad">Ошибка: {q.error.message}</div>}

      {q.loading && !items.length ? (
        <SubsSkeleton />
      ) : !items.length ? (
        <SubsEmpty
          hasFilters={Boolean(planFilter || preset !== "all")}
          onReset={() => { setPlanFilter(""); setPreset("all"); }}
        />
      ) : isMobile ? (
        <div className="m-cardlist">
          {items.map((s) => (
            <SubMobileCard
              key={s.id}
              s={s}
              plan={s.plan_id ? plansById[s.plan_id] : null}
              onOpen={() => setSelected(s)}
            />
          ))}
        </div>
      ) : (
        <div className="card">
          <table className="tbl u-tbl">
            <thead>
              <tr>
                <th>Подписка</th>
                <th>Статус</th>
                <th>Трафик</th>
                <th>Осталось</th>
                <th>Регион</th>
                <th style={{ textAlign: "right" }}>Устройств</th>
                <th>Создана</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <SubRow
                  key={s.id}
                  s={s}
                  plan={s.plan_id ? plansById[s.plan_id] : null}
                  onOpen={() => setSelected(s)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <SubscriptionDrawer
          subscription={selected}
          onClose={() => setSelected(null)}
          onChanged={q.refetch}
        />
      )}
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

function Kpi({ icon, label, value, tone }) {
  return (
    <div className={"u-kpi" + (tone ? ` ${tone}` : "")}>
      <div className="u-kpi-label"><Icon name={icon} size={11} /> {label}</div>
      <div className="u-kpi-val">{value}</div>
    </div>
  );
}

function SubMobileCard({ s, plan, onOpen }) {
  const status = deriveSubStatus(s);
  const days = daysLeft(s.expires_at);
  const cap = plan?.traffic_limit_bytes
    ?? (plan?.traffic_limit_mb ? plan.traffic_limit_mb * 1024 * 1024 : null);
  const planName = plan?.name || s.plan_name || "—";
  return (
    <div className="m-card" onClick={onOpen}>
      <div className="m-card-head">
        <div className="m-card-title">
          <div className="m-card-name">{planName}</div>
          <div className="mono muted m-card-id">{String(s.id).slice(0, 8)}…</div>
        </div>
        <StatusPill status={status} />
      </div>
      <div className="m-card-body">
        <div className="m-card-row">
          <span className="m-card-label">Трафик</span>
          <div style={{ flex: 1 }}>
            {cap
              ? <TrafficBar used={s.used_traffic_bytes || 0} cap={cap} />
              : <span className="mono small muted">∞</span>}
          </div>
        </div>
        <div className="m-card-row">
          <span className="m-card-label">Осталось</span>
          <DaysCountdown days={days} />
        </div>
        <div className="m-card-row">
          <span className="m-card-label">Регион</span>
          <span className="mono small">{s.preferred_region || "—"}</span>
        </div>
        <div className="m-card-row">
          <span className="m-card-label">Устройства</span>
          <span className="mono">{s.max_devices != null ? `${s.paid_device_slots ?? 0}/${s.max_devices}` : "—"}</span>
        </div>
        <div className="m-card-row">
          <span className="m-card-label">Создана</span>
          <span className="small muted">{fmtDate(s.created_at)}</span>
        </div>
      </div>
    </div>
  );
}

function SubRow({ s, plan, onOpen }) {
  const status = deriveSubStatus(s);
  const days = daysLeft(s.expires_at);
  const cap = plan?.traffic_limit_bytes
    ?? (plan?.traffic_limit_mb ? plan.traffic_limit_mb * 1024 * 1024 : null);
  const planName = plan?.name || s.plan_name || "—";

  return (
    <tr style={{ cursor: "pointer" }} onClick={onOpen}>
      <td style={{ minWidth: 220 }}>
        <div style={{ fontWeight: 500 }}>{planName}</div>
        <div className="mono muted" style={{ fontSize: 11 }}>
          {String(s.id).slice(0, 8)}…
        </div>
      </td>
      <td><StatusPill status={status} /></td>
      <td style={{ minWidth: 180 }}>
        {cap
          ? <TrafficBar used={s.used_traffic_bytes || 0} cap={cap} />
          : <span className="mono small muted">∞</span>}
      </td>
      <td><DaysCountdown days={days} /></td>
      <td className="mono small">{s.preferred_region || "—"}</td>
      <td className="tbl-num mono">
        {s.max_devices != null ? `${s.paid_device_slots ?? 0}/${s.max_devices}` : "—"}
      </td>
      <td className="small muted">{fmtDate(s.created_at)}</td>
      <td style={{ width: 32, textAlign: "right", paddingRight: 12 }}>
        <Icon name="chevron-right" size={14} className="muted" />
      </td>
    </tr>
  );
}

function SubsSkeleton() {
  return (
    <div className="card">
      <table className="tbl u-tbl">
        <thead>
          <tr>
            <th>Подписка</th><th>Статус</th><th>Трафик</th><th>Осталось</th>
            <th>Регион</th><th>Устройств</th><th>Создана</th><th></th>
          </tr>
        </thead>
        <tbody>
          {[0,1,2,3,4,5].map((i) => (
            <tr key={i}>
              <td>
                <div className="u-skel" style={{ width: 140, height: 12, marginBottom: 4 }}></div>
                <div className="u-skel" style={{ width: 80, height: 9 }}></div>
              </td>
              <td><div className="u-skel" style={{ width: 80, height: 18, borderRadius: 6 }}></div></td>
              <td><div className="u-skel" style={{ width: 160, height: 26 }}></div></td>
              <td><div className="u-skel" style={{ width: 60, height: 14 }}></div></td>
              <td><div className="u-skel" style={{ width: 40, height: 12 }}></div></td>
              <td><div className="u-skel" style={{ width: 40, height: 12 }}></div></td>
              <td><div className="u-skel" style={{ width: 70, height: 12 }}></div></td>
              <td></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SubsEmpty({ hasFilters, onReset }) {
  return (
    <div className="card">
      <div className="u-empty">
        <div className="u-empty-art"><Icon name="key" size={36} /></div>
        <div className="u-empty-title">
          {hasFilters ? "Нет подписок под фильтры" : "Пока нет подписок"}
        </div>
        <div className="u-empty-text">
          {hasFilters
            ? "Попробуйте смягчить условия — другой тариф или сбросьте пресеты."
            : "Подписки появляются после первой оплаты пользователя или ручного создания."}
        </div>
        {hasFilters && (
          <div className="u-empty-actions">
            <button className="btn btn-ghost" onClick={onReset}>
              <Icon name="x" size={13} /> Сбросить фильтры
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
