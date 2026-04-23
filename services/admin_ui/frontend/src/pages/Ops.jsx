import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Field } from "../components/Field.jsx";
import { Icon } from "../components/Icon.jsx";
import { toast } from "../components/Toast.jsx";

const ACTIONS = ["set_healthy", "set_degraded", "set_suspected", "block", "recover"];

export function OpsPage() {
  const status = useQuery(() => api.get("/admin/status"), { interval: 30000 });
  const routes = useQuery(() => api.get("/routes?limit=500"), { interval: 30000 });
  const readiness = useQuery(() => api.get("/admin/readiness"), { interval: 15000 });

  const backends = (status.data?.nodes || []).filter((n) => n.role === "backend");
  const routesList = routes.data || [];

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Операции</h1>
          <div className="page-subtitle">
            Readiness: {readiness.data?.ready ? <span className="pill ok">ready</span> : <span className="pill bad">not ready</span>}
            {" · "}
            {status.data?.nodes?.length ?? "—"} нод в флоте
          </div>
        </div>
      </div>

      <div className="split-2">
        <MigrateForm backends={backends} />
        <RouteHealthForm routes={routesList} />
      </div>

      <div className="sec" style={{ marginTop: 20 }}>
        <ProbePolicyCard />
      </div>
    </div>
  );
}

function ProbePolicyCard() {
  const q = useQuery(() => api.get("/admin/probe/policy"), { interval: 0 });
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (q.data) setF(q.data); }, [q.data]);

  if (!f) return (
    <div className="card"><div className="card-body muted">Загрузка policy…</div></div>
  );

  const set = (k) => (e) => {
    const val = e.target.type === "checkbox" ? e.target.checked : (e.target.type === "number" ? Number(e.target.value) : e.target.value);
    setF((s) => ({ ...s, [k]: val }));
  };

  const save = async () => {
    setBusy(true);
    try {
      const keys = [
        "auto_route_health_enabled",
        "route_suspected_after_failures", "route_degraded_after_failures", "route_block_after_failures",
        "route_block_cooldown_hours",
        "auto_drain_enabled", "auto_drain_tick_sec", "auto_drain_min_consecutive_failures",
        "auto_drain_max_probe_age_sec", "auto_drain_max_nodes",
        "auto_drain_source", "auto_drain_require_recent_failure", "auto_drain_include_already_draining",
        "auto_drain_target_backend_id", "auto_drain_last_migration_reason",
        "auto_undrain_enabled", "auto_undrain_min_consecutive_successes",
        "auto_undrain_max_probe_age_sec", "auto_undrain_source",
        "retention_days", "cleanup_enabled", "cleanup_tick_sec",
        "synthetic_reconcile_enabled", "synthetic_reconcile_tick_sec",
        "synthetic_key_valid_days", "synthetic_key_traffic_limit_mb",
      ];
      const payload = {};
      for (const k of keys) if (f[k] !== undefined) payload[k] = f[k] === "" ? null : f[k];
      const updated = await api.patch("/admin/probe/policy", payload);
      setF(updated);
      toast.ok("Probe-политика обновлена");
    } catch (e) { toast.bad(e.message || "Ошибка"); }
    finally { setBusy(false); }
  };

  const killSwitchOff = !f.auto_route_health_enabled;

  return (
    <div className="card">
      <div className="card-head">
        <Icon name="shield-check" size={14} />
        <div className="sec-title">Probe-политика</div>
        <div className="sec-sub">управление автоматикой probe · изменения применяются на лету</div>
        <div className="sec-spacer" />
        <label className="form-check" style={{ margin: 0 }}>
          <input type="checkbox" checked={!!f.auto_route_health_enabled} onChange={set("auto_route_health_enabled")} />
          <span>Автоматика включена</span>
        </label>
      </div>

      <div style={{ opacity: killSwitchOff ? 0.5 : 1, transition: "opacity 150ms ease" }}>
        <Section
          title="Пороги маршрутов"
          subtitle="когда переводить route в suspected/degraded/blocked"
          icon="route"
          defaultOpen
        >
          <div className="form-row">
            <Field label="Suspected после N подряд fail" hint="1–50">
              <input type="number" min={1} max={50} value={f.route_suspected_after_failures} onChange={set("route_suspected_after_failures")} />
            </Field>
            <Field label="Degraded после" hint="2–50">
              <input type="number" min={2} max={50} value={f.route_degraded_after_failures} onChange={set("route_degraded_after_failures")} />
            </Field>
          </div>
          <div className="form-row">
            <Field label="Blocked после" hint="3–50">
              <input type="number" min={3} max={50} value={f.route_block_after_failures} onChange={set("route_block_after_failures")} />
            </Field>
            <Field label="Cooldown блокировки, часов" hint="1–168">
              <input type="number" min={1} max={168} value={f.route_block_cooldown_hours} onChange={set("route_block_cooldown_hours")} />
            </Field>
          </div>
        </Section>

        <Section
          title="Авто-drain нод"
          subtitle={f.auto_drain_enabled ? "активен" : "выключен"}
          icon="pause"
          toneWhenClosed={f.auto_drain_enabled ? "ok" : "muted"}
        >
          <label className="form-check" style={{ marginBottom: 10 }}>
            <input type="checkbox" checked={f.auto_drain_enabled} onChange={set("auto_drain_enabled")} />
            Включить авто-drain при деградации
          </label>
          <div className="form-row">
            <Field label="Тик, секунд">
              <input type="number" min={30} max={3600} value={f.auto_drain_tick_sec} onChange={set("auto_drain_tick_sec")} />
            </Field>
            <Field label="Мин. подряд fail">
              <input type="number" min={1} max={50} value={f.auto_drain_min_consecutive_failures} onChange={set("auto_drain_min_consecutive_failures")} />
            </Field>
          </div>
          <div className="form-row">
            <Field label="Макс. возраст probe, сек">
              <input type="number" min={60} max={86400} value={f.auto_drain_max_probe_age_sec} onChange={set("auto_drain_max_probe_age_sec")} />
            </Field>
            <Field label="Макс. нод за тик">
              <input type="number" min={1} max={500} value={f.auto_drain_max_nodes} onChange={set("auto_drain_max_nodes")} />
            </Field>
          </div>
          <div className="form-row">
            <Field label="Drain source" hint="имя probe-источника">
              <input type="text" value={f.auto_drain_source || ""} onChange={set("auto_drain_source")} placeholder="probe-prod-entry" />
            </Field>
            <Field label="Reason label" hint="метка для логов миграции">
              <input type="text" value={f.auto_drain_last_migration_reason || ""} onChange={set("auto_drain_last_migration_reason")} />
            </Field>
          </div>
          <Field label="Target backend (UUID)" hint="пусто = автоматический выбор">
            <input type="text" value={f.auto_drain_target_backend_id || ""} onChange={set("auto_drain_target_backend_id")} placeholder="—" />
          </Field>
          <label className="form-check">
            <input type="checkbox" checked={!!f.auto_drain_require_recent_failure} onChange={set("auto_drain_require_recent_failure")} />
            Требовать свежий probe failure
          </label>
          <label className="form-check" style={{ marginTop: 6 }}>
            <input type="checkbox" checked={!!f.auto_drain_include_already_draining} onChange={set("auto_drain_include_already_draining")} />
            Включать уже draining ноды в рассмотрение
          </label>
        </Section>

        <Section
          title="Авто-undrain нод"
          subtitle={f.auto_undrain_enabled ? "активен" : "выключен"}
          icon="play"
          toneWhenClosed={f.auto_undrain_enabled ? "ok" : "muted"}
        >
          <label className="form-check" style={{ marginBottom: 10 }}>
            <input type="checkbox" checked={f.auto_undrain_enabled} onChange={set("auto_undrain_enabled")} />
            Включить авто-снятие drain при восстановлении
          </label>
          <div className="form-row">
            <Field label="Мин. подряд OK">
              <input type="number" min={1} max={50} value={f.auto_undrain_min_consecutive_successes} onChange={set("auto_undrain_min_consecutive_successes")} />
            </Field>
            <Field label="Макс. возраст probe, сек">
              <input type="number" min={60} max={86400} value={f.auto_undrain_max_probe_age_sec} onChange={set("auto_undrain_max_probe_age_sec")} />
            </Field>
          </div>
          <Field label="Undrain source" hint="пусто = тот же что и drain">
            <input type="text" value={f.auto_undrain_source || ""} onChange={set("auto_undrain_source")} />
          </Field>
        </Section>

        <Section
          title="Хранение и cleanup"
          subtitle={`retention ${f.retention_days}д · tick ${f.cleanup_tick_sec}s`}
          icon="clock"
        >
          <div className="form-row">
            <Field label="Retention, дней">
              <input type="number" min={1} max={365} value={f.retention_days} onChange={set("retention_days")} />
            </Field>
            <Field label="Cleanup tick, сек">
              <input type="number" min={60} max={86400} value={f.cleanup_tick_sec} onChange={set("cleanup_tick_sec")} />
            </Field>
          </div>
          <label className="form-check">
            <input type="checkbox" checked={!!f.cleanup_enabled} onChange={set("cleanup_enabled")} />
            Включить cleanup старых probe-сигналов
          </label>
        </Section>

        <Section
          title="Synthetic probe"
          subtitle={f.synthetic_reconcile_enabled ? "активен" : "выключен"}
          icon="radar"
          toneWhenClosed={f.synthetic_reconcile_enabled ? "ok" : "muted"}
        >
          <label className="form-check" style={{ marginBottom: 10 }}>
            <input type="checkbox" checked={!!f.synthetic_reconcile_enabled} onChange={set("synthetic_reconcile_enabled")} />
            Включить synthetic probe reconcile
          </label>
          <div className="form-row">
            <Field label="Tick, сек">
              <input type="number" min={30} max={86400} value={f.synthetic_reconcile_tick_sec} onChange={set("synthetic_reconcile_tick_sec")} />
            </Field>
            <Field label="Срок действия ключа, дней">
              <input type="number" min={1} max={36500} value={f.synthetic_key_valid_days} onChange={set("synthetic_key_valid_days")} />
            </Field>
          </div>
          <Field label="Лимит трафика synthetic-ключа, MB">
            <input type="number" min={1} max={10485760} value={f.synthetic_key_traffic_limit_mb} onChange={set("synthetic_key_traffic_limit_mb")} />
          </Field>
        </Section>
      </div>

      <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button className="btn btn-ghost" onClick={() => q.refetch()} disabled={busy}>Отменить</button>
        <button className="btn btn-primary" onClick={save} disabled={busy}>Сохранить</button>
      </div>
    </div>
  );
}

function Section({ title, subtitle, icon, children, defaultOpen = false, toneWhenClosed = "" }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ borderBottom: "1px solid var(--border)" }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "12px 14px",
          background: "transparent", border: 0, cursor: "pointer", textAlign: "left",
        }}
      >
        {icon && <Icon name={icon} size={13} style={{ color: "var(--text-muted)" }} />}
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 500, fontSize: 13 }}>{title}</div>
          {subtitle && (
            <div className={`small ${toneWhenClosed === "ok" ? "" : "muted"}`} style={{ color: toneWhenClosed === "ok" ? "var(--ok)" : undefined, marginTop: 2 }}>
              {subtitle}
            </div>
          )}
        </div>
        <Icon name={open ? "chevron-down" : "chevron-right"} size={14} style={{ color: "var(--text-muted)" }} />
      </button>
      {open && (
        <div style={{ padding: "4px 14px 16px" }}>
          {children}
        </div>
      )}
    </div>
  );
}

function MigrateForm({ backends }) {
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("admin_manual");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");

  const go = async () => {
    setBusy(true); setErr(""); setResult(null);
    try {
      if (!source) throw new Error("Выберите исходную ноду");
      const payload = { source_backend_id: source, last_migration_reason: reason };
      if (target) payload.target_backend_id = target;
      const r = await api.post("/admin/migrate-backend", payload);
      setResult(r);
    } catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column" }}>
      <div className="card-head">
        <Icon name="arrow-right" size={14} />
        <div className="sec-title">Миграция плейсментов</div>
      </div>
      <div className="card-body" style={{ flex: 1 }}>
        {err && <div className="form-error">{err}</div>}
        <Field label="Исходная нода">
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">— выберите —</option>
            {backends.map((n) => <option key={n.id} value={n.id}>{n.name} · {n.region}</option>)}
          </select>
        </Field>
        <Field label="Целевая нода" hint="опционально (иначе авто)">
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">Авто</option>
            {backends.map((n) => <option key={n.id} value={n.id}>{n.name} · {n.region}</option>)}
          </select>
        </Field>
        <Field label="Причина"><input type="text" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        {result && (
          <div style={{ marginTop: 10, padding: 10, background: "var(--surface-2)", borderRadius: 6, border: "1px solid var(--border)" }}>
            <pre className="mono small" style={{ margin: 0, whiteSpace: "pre-wrap" }}>{JSON.stringify(result, null, 2)}</pre>
          </div>
        )}
      </div>
      <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "flex-end" }}>
        <button className="btn btn-primary" onClick={go} disabled={busy}>Запустить миграцию</button>
      </div>
    </div>
  );
}

function RouteHealthForm({ routes }) {
  const [routeId, setRouteId] = useState("");
  const [action, setAction] = useState("set_healthy");
  const [cooldown, setCooldown] = useState(6);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState(false);

  const go = async () => {
    setBusy(true); setErr(""); setOk(false);
    try {
      if (!routeId) throw new Error("Выберите маршрут");
      await api.post("/admin/set-route-health", { route_id: routeId, action, cooldown_hours: Number(cooldown) || 6 });
      setOk(true);
    } catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column" }}>
      <div className="card-head">
        <Icon name="shield-check" size={14} />
        <div className="sec-title">Управление health маршрута</div>
      </div>
      <div className="card-body" style={{ flex: 1 }}>
        {err && <div className="form-error">{err}</div>}
        <Field label="Маршрут">
          <select value={routeId} onChange={(e) => setRouteId(e.target.value)}>
            <option value="">— выберите —</option>
            {routes.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </Field>
        <Field label="Действие">
          <select value={action} onChange={(e) => setAction(e.target.value)}>
            {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </Field>
        <Field label="Cooldown, часов" hint="1–72"><input type="number" min={1} max={72} value={cooldown} onChange={(e) => setCooldown(e.target.value)} /></Field>
        {ok && <div className="muted small" style={{ marginTop: 8 }}>Применено.</div>}
      </div>
      <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "flex-end" }}>
        <button className="btn btn-primary" onClick={go} disabled={busy}>Применить</button>
      </div>
    </div>
  );
}
