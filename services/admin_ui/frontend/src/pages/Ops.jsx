import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Field } from "../components/Field.jsx";
import { Icon } from "../components/Icon.jsx";
import { toast } from "../components/Toast.jsx";
import { nodeGeo } from "../lib/geo.js";

const ACTION_META = {
  set_healthy:   { label: "Вернуть healthy",  icon: "check",            tone: "ok"   },
  set_suspected: { label: "Suspected",        icon: "alert-triangle",   tone: "warn" },
  set_degraded:  { label: "Degraded",         icon: "alert-triangle",   tone: "warn" },
  block:         { label: "Block",            icon: "alert-circle",     tone: "bad"  },
  recover:       { label: "Recover",          icon: "refresh",          tone: "info" },
};

const ROUTE_HEALTH_TONE = {
  healthy: "ok", warming_up: "info", degraded: "warn", suspected: "warn", blocked: "bad",
};

function relTime(iso) {
  if (!iso) return "—";
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

export function OpsPage() {
  const status = useQuery(() => api.get("/admin/status"), { interval: 30000 });
  const routes = useQuery(() => api.get("/routes?limit=500"), { interval: 30000 });
  const readiness = useQuery(() => api.get("/admin/readiness"), { interval: 15000 });
  const audit = useQuery(() => api.get("/admin/audit?limit=20"), { interval: 15000 });

  const nodes = status.data?.nodes || [];
  const backends = nodes.filter((n) => n.role === "backend");
  const routesList = routes.data || [];
  const readinessReady = !!readiness.data?.ready;
  const checks = readiness.data?.checks || [];
  const failed = checks.filter((c) => !c.ok).length;

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Операции</h1>
          <div className="page-subtitle">Действия оператора и их история · настройки политик → раздел «Настройки»</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={() => { status.refetch(); routes.refetch(); readiness.refetch(); audit.refetch(); }}>
            <Icon name="refresh" size={13} /> Обновить
          </button>
        </div>
      </div>

      {/* Readiness panel */}
      <div className="sec">
        <div className="kpi-hero">
          <ReadinessCell
            icon="shield-check"
            label="Readiness"
            value={readinessReady ? "ready" : "not ready"}
            tone={readinessReady ? "up" : "down"}
            hint={`${checks.length - failed}/${checks.length} checks`}
          />
          <ReadinessCell
            icon="server"
            label="Нод в флоте"
            value={nodes.length}
            hint={`${nodes.filter((n) => n.is_enabled && !n.is_draining).length} активных · ${nodes.filter((n) => n.is_draining).length} draining`}
          />
          <ReadinessCell
            icon="route"
            label="Маршрутов"
            value={routesList.length}
            hint={`${routesList.filter((r) => r.health_status === "blocked").length} blocked · ${routesList.filter((r) => ["degraded","suspected"].includes(r.health_status)).length} degraded`}
          />
          <ReadinessCell
            icon="activity"
            label="Админ-действий 24h"
            value={audit.data?.items?.filter((a) => Date.now() - new Date(a.created_at).getTime() < 86400000).length ?? 0}
            hint="миграции, health-override, policy изменения"
          />
        </div>

        {!readinessReady && failed > 0 && (
          <div className="card card-bad" style={{ marginTop: 10 }}>
            <strong>Readiness not ready:</strong>
            <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
              {checks.filter((c) => !c.ok).map((c, i) => (
                <li key={i} className="small">{c.name}: {c.detail || "failed"}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Action forms */}
      <div className="split-2">
        <MigrateForm backends={backends} onDone={audit.refetch} />
        <RouteHealthForm routes={routesList} onDone={audit.refetch} />
      </div>

      {/* Audit feed */}
      <div className="sec" style={{ marginTop: 20 }}>
        <AuditFeed items={audit.data?.items || []} loading={audit.loading} />
      </div>
    </div>
  );
}

function ReadinessCell({ icon, label, value, hint, tone }) {
  return (
    <div className="kpi-cell">
      <div className="kpi-label"><Icon name={icon} size={12} /> <span>{label}</span></div>
      <div className="kpi-value-row">
        <div className="kpi-value tnum">{value}</div>
      </div>
      {hint && <div className={`kpi-delta ${tone || "flat"}`}>{hint}</div>}
    </div>
  );
}

function MigrateForm({ backends, onDone }) {
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("admin_manual");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [result, setResult] = useState(null);

  const sourceNode = backends.find((n) => n.id === source);
  const targetNode = target ? backends.find((n) => n.id === target) : null;
  const capacityUsagePct = (n) => Math.min(100, Math.round(((n?.placements_backend || 0) / Math.max(n?.capacity || 50, 1)) * 100));

  const go = async () => {
    setBusy(true); setErr(""); setResult(null);
    try {
      if (!source) throw new Error("Выберите исходную ноду");
      const payload = { source_backend_id: source, last_migration_reason: reason };
      if (target) payload.target_backend_id = target;
      const r = await api.post("/admin/migrate-backend", payload);
      setResult(r);
      toast.ok(`Мигрировано: ${r.migrated_count}`);
      onDone?.();
    } catch (e) { setErr(e.message || String(e)); toast.bad(e.message || "Ошибка"); }
    finally { setBusy(false); }
  };

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column" }}>
      <div className="card-head">
        <Icon name="arrow-right" size={14} />
        <div className="sec-title">Миграция плейсментов</div>
        <div className="sec-sub">перенос активных ключей между backend-нодами</div>
      </div>
      <div className="card-body" style={{ flex: 1 }}>
        {err && <div className="form-error">{err}</div>}
        <Field label="Исходная нода">
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">— выберите —</option>
            {backends.map((n) => <option key={n.id} value={n.id}>{n.name} · {n.region}</option>)}
          </select>
        </Field>
        {sourceNode && (
          <div className="muted small" style={{ marginTop: -8, marginBottom: 12 }}>
            <Icon name="info" size={11} /> {sourceNode.placements_backend || 0} активных · {capacityUsagePct(sourceNode)}% capacity · {sourceNode.is_draining ? "draining" : "active"}
          </div>
        )}
        <Field label="Целевая нода" hint="пусто = автоматический выбор">
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">Авто</option>
            {backends.filter((n) => n.id !== source && n.is_enabled && !n.is_draining).map((n) => (
              <option key={n.id} value={n.id}>{n.name} · {n.region} · {capacityUsagePct(n)}%</option>
            ))}
          </select>
        </Field>
        {targetNode && (
          <div className="muted small" style={{ marginTop: -8, marginBottom: 12 }}>
            <Icon name="info" size={11} /> Текущая загрузка: {capacityUsagePct(targetNode)}% · свободно capacity: {(targetNode.capacity || 0) - (targetNode.placements_backend || 0)}
          </div>
        )}
        <Field label="Причина" hint="метка для логов">
          <input type="text" value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        {result && (
          <div style={{ marginTop: 10, padding: 10, background: "var(--ok-soft)", borderRadius: 6, border: "1px solid var(--ok)" }}>
            <div className="small" style={{ fontWeight: 500, color: "var(--ok)" }}>
              <Icon name="check" size={12} /> Успех: мигрировано {result.migrated_count} плейсментов
            </div>
          </div>
        )}
      </div>
      <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "flex-end" }}>
        <button className="btn btn-primary" onClick={go} disabled={busy || !source}>
          <Icon name="arrow-right" size={12} /> Запустить миграцию
        </button>
      </div>
    </div>
  );
}

function RouteHealthForm({ routes, onDone }) {
  const [routeId, setRouteId] = useState("");
  const [action, setAction] = useState("set_healthy");
  const [cooldown, setCooldown] = useState(6);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const route = routes.find((r) => r.id === routeId);
  const currentTone = route ? (ROUTE_HEALTH_TONE[route.health_status] || "muted") : null;

  const go = async () => {
    setBusy(true); setErr("");
    try {
      if (!routeId) throw new Error("Выберите маршрут");
      await api.post("/admin/set-route-health", { route_id: routeId, action, cooldown_hours: Number(cooldown) || 6 });
      toast.ok(`Маршрут ${route?.name} → ${ACTION_META[action]?.label}`);
      onDone?.();
    } catch (e) { setErr(e.message || String(e)); toast.bad(e.message || "Ошибка"); }
    finally { setBusy(false); }
  };

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column" }}>
      <div className="card-head">
        <Icon name="shield-check" size={14} />
        <div className="sec-title">Управление health маршрута</div>
        <div className="sec-sub">override probe-политики вручную</div>
      </div>
      <div className="card-body" style={{ flex: 1 }}>
        {err && <div className="form-error">{err}</div>}
        <Field label="Маршрут">
          <select value={routeId} onChange={(e) => setRouteId(e.target.value)}>
            <option value="">— выберите —</option>
            {routes.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </Field>
        {route && (
          <div className="muted small" style={{ marginTop: -8, marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
            Текущий статус: <span className={`pill ${currentTone}`}><span className={`status-dot ${currentTone}`} /> {route.health_status}</span>
            <span>· weight {route.effective_weight}/{route.base_weight}</span>
          </div>
        )}
        <div>
          <div className="form-label">Действие</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
            {Object.entries(ACTION_META).map(([key, meta]) => (
              <button
                key={key}
                type="button"
                onClick={() => setAction(key)}
                className={`pill ${meta.tone}`}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 4, cursor: "pointer",
                  border: action === key ? `1px solid var(--${meta.tone})` : "1px solid transparent",
                  outline: action === key ? `1px solid var(--${meta.tone})` : "none",
                  outlineOffset: -1,
                  fontWeight: action === key ? 600 : 400,
                }}
              >
                <Icon name={meta.icon} size={11} />
                {meta.label}
              </button>
            ))}
          </div>
        </div>
        <Field label="Cooldown, часов" hint="1–72, применяется к block/recover">
          <input type="number" min={1} max={72} value={cooldown} onChange={(e) => setCooldown(e.target.value)} />
        </Field>
      </div>
      <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "flex-end" }}>
        <button className="btn btn-primary" onClick={go} disabled={busy || !routeId}>
          Применить
        </button>
      </div>
    </div>
  );
}

const AUDIT_ACTION_META = {
  migrate_backend:     { icon: "arrow-right",   tone: "info",   label: "Миграция" },
  set_route_health:    { icon: "shield-check",  tone: "warn",   label: "Route health" },
  probe_policy_update: { icon: "sliders",       tone: "accent", label: "Policy" },
};

function AuditFeed({ items, loading }) {
  return (
    <div className="card">
      <div className="card-head">
        <Icon name="activity" size={14} />
        <div className="sec-title">Недавние действия</div>
        <div className="sec-sub">аудит лог мутаций за последние 24ч</div>
        <div className="sec-spacer" />
        <span className="muted text-xs">{items.length} записей</span>
      </div>
      {loading && !items.length && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
      {!loading && !items.length && <div className="muted" style={{ padding: 14 }}>Нет записей. Действия появятся здесь автоматически.</div>}
      {items.map((r) => {
        const meta = AUDIT_ACTION_META[r.action] || { icon: "activity", tone: "", label: r.action };
        return (
          <div key={r.id} className="activity" style={{ borderBottom: "1px solid var(--border)" }}>
            <div className={`activity-dot ${meta.tone === "accent" ? "ok" : meta.tone}`} />
            <div className="activity-main">
              <div className="activity-text">
                <span className={`pill ${meta.tone}`} style={{ marginRight: 8 }}>
                  <Icon name={meta.icon} size={11} /> {meta.label}
                </span>
                {r.summary || r.action}
              </div>
              <div className="activity-meta">
                <strong>{r.actor}</strong>
                {r.target && <> · <span className="mono">{String(r.target).slice(0, 12)}…</span></>}
                {" · "}{relTime(r.created_at)} назад
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
