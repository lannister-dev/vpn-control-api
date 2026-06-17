import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";

export const AUDIT_ACTION_META = {
  balance_credit:      { icon: "plus",          tone: "ok",     label: "Пополнение баланса" },
  balance_debit:       { icon: "minus",         tone: "bad",    label: "Списание баланса" },
  subscription_extend: { icon: "calendar",      tone: "info",   label: "Продление подписки" },
  migrate_backend:     { icon: "arrow-right",   tone: "info",   label: "Миграция" },
  set_route_health:    { icon: "shield",        tone: "warn",   label: "Route health" },
  probe_policy_update: { icon: "sliders",       tone: "info",   label: "Policy" },
};

const ACTION_FILTERS = [
  { value: "", label: "Все действия" },
  { value: "balance_debit", label: "Списания баланса" },
  { value: "balance_credit", label: "Пополнения баланса" },
  { value: "subscription_extend", label: "Продления подписок" },
  { value: "migrate_backend", label: "Миграции" },
];

function relTime(iso) {
  if (!iso) return "—";
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}с`;
  if (s < 3600) return `${Math.floor(s / 60)}м`;
  if (s < 86400) return `${Math.floor(s / 3600)}ч`;
  return `${Math.floor(s / 86400)}д`;
}

export function AuditRow({ r }) {
  const meta = AUDIT_ACTION_META[r.action] || { icon: "activity", tone: "", label: r.action };
  return (
    <div className="activity" style={{ borderBottom: "1px solid var(--border)" }}>
      <div className={`activity-dot ${meta.tone}`} />
      <div className="activity-main">
        <div className="activity-text">
          <span className={`pill ${meta.tone}`} style={{ marginRight: 8 }}>
            <Icon name={meta.icon} size={11} /> {meta.label}
          </span>
          {r.summary || r.action}
        </div>
        <div className="activity-meta">
          <strong>{r.actor}</strong>
          {r.target && <> · <span className="mono">{String(r.target).slice(0, 8)}…</span></>}
          {" · "}{new Date(r.created_at).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
          {" · "}{relTime(r.created_at)} назад
        </div>
      </div>
    </div>
  );
}

export function AuditPage() {
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const q = useQuery(() => {
    const p = new URLSearchParams({ limit: "100" });
    if (action) p.set("action", action);
    if (actor.trim()) p.set("actor", actor.trim());
    return api.get(`/admin/audit?${p.toString()}`);
  }, { interval: 20000, deps: [action, actor] });
  const items = q.data?.items || [];

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Журнал действий</h1>
          <div className="page-subtitle">Аудит чувствительных операций админов · {q.data?.total ?? 0} записей</div>
        </div>
      </div>

      <div className="sec">
        <div className="card">
          <div className="fin-filterbar" style={{ display: "flex", gap: 8, alignItems: "center", padding: 10, flexWrap: "wrap" }}>
            <select className="select" value={action} onChange={(e) => setAction(e.target.value)} style={{ minWidth: 180 }}>
              {ACTION_FILTERS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>
            <input className="input" placeholder="Админ (actor)…" value={actor} onChange={(e) => setActor(e.target.value)} style={{ minWidth: 180 }} />
            <div className="sec-spacer" />
            <button className="btn btn-ghost btn-sm" onClick={() => q.refetch()}><Icon name="refresh" size={13} /> Обновить</button>
          </div>
          {q.loading && !items.length && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
          {!q.loading && !items.length && <div className="muted" style={{ padding: 14 }}>Нет записей.</div>}
          {items.map((r) => <AuditRow key={r.id} r={r} />)}
        </div>
      </div>
    </div>
  );
}
