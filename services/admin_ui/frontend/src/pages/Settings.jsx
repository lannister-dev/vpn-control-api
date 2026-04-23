import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { Field } from "../components/Field.jsx";
import { toast } from "../components/Toast.jsx";

const SECTIONS = [
  { id: "probe", label: "Probe-политика", icon: "shield-check", hint: "пороги маршрутов + автодрейн" },
  { id: "nodes", label: "Ноды и placements", icon: "server", hint: "heartbeat / auto-heal / rebalance / entry" },
  { id: "transport", label: "Транспорт (NATS)", icon: "activity", hint: "хранение событий и outbox" },
];

export function SettingsPage() {
  const [section, setSection] = useState("probe");

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Настройки</h1>
          <div className="page-subtitle">Централизованные политики системы · изменения применяются runtime</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 20, alignItems: "start" }}>
        <aside className="card" style={{ position: "sticky", top: 12, padding: 6 }}>
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              className="side-btn"
              data-active={section === s.id}
              onClick={() => setSection(s.id)}
              style={{ width: "100%", marginBottom: 2 }}
            >
              <Icon name={s.icon} size={15} />
              <span className="side-label">{s.label}</span>
            </button>
          ))}
        </aside>

        <div>
          {section === "probe" && <ProbePolicySection />}
          {section === "nodes" && <NodePolicySection />}
          {section === "transport" && <TransportPolicySection />}
        </div>
      </div>
    </div>
  );
}

function TransportPolicySection() {
  const q = useQuery(() => api.get("/admin/transport/policy"), { interval: 0 });
  const [f, setF] = useState(null);
  const [initial, setInitial] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.data) { setF(q.data); setInitial(q.data); }
  }, [q.data]);

  const set = (k) => (e) => {
    const val = e.target.type === "checkbox" ? e.target.checked
      : (e.target.type === "number" ? Number(e.target.value) : e.target.value);
    setF((s) => ({ ...s, [k]: val }));
  };

  const dirtyFields = useMemo(() => {
    if (!f || !initial) return [];
    return Object.keys(f).filter((k) => {
      if (k === "id" || k === "created_at" || k === "updated_at") return false;
      return JSON.stringify(f[k]) !== JSON.stringify(initial[k]);
    });
  }, [f, initial]);
  const dirty = dirtyFields.length > 0;

  const save = async () => {
    setBusy(true);
    try {
      const payload = {};
      for (const k of dirtyFields) payload[k] = f[k] === "" ? null : f[k];
      const updated = await api.patch("/admin/transport/policy", payload);
      setF(updated);
      setInitial(updated);
      toast.ok(`Сохранено · ${dirtyFields.length} изменений`);
    } catch (e) { toast.bad(e.message || "Ошибка"); }
    finally { setBusy(false); }
  };

  const cancel = () => setF(initial);

  if (!f) return <div className="card"><div className="card-body muted">Загрузка…</div></div>;

  return (
    <>
      <div className="card">
        <div className="card-head">
          <Icon name="activity" size={14} />
          <div className="sec-title">Транспорт · cleanup</div>
          <div className="sec-sub">удаление старых событий и опубликованных outbox-записей</div>
          <div className="sec-spacer" />
          <label className="form-check" style={{ margin: 0 }}>
            <input type="checkbox" checked={!!f.cleanup_enabled} onChange={set("cleanup_enabled")} />
            <span>Включено</span>
          </label>
        </div>
        <div className="card-body" style={{ opacity: f.cleanup_enabled ? 1 : 0.55 }}>
          <div className="form-row">
            <Field label="Retention, дней" hint="хранение outbox + event_log">
              <input type="number" min={1} max={365} value={f.retention_days} onChange={set("retention_days")} />
            </Field>
            <Field label="Cleanup tick, сек" hint="интервал фонового джоба">
              <input type="number" min={60} max={86400} value={f.cleanup_tick_sec} onChange={set("cleanup_tick_sec")} />
            </Field>
          </div>
          <div className="muted small">
            Cleanup удаляет события типа heartbeat / sync_report и выполненные outbox-записи старше Retention дней. Не трогает failed outbox (их нужно разбирать явно).
          </div>
        </div>
      </div>

      {dirty && (
        <div style={{
          position: "sticky", bottom: 12, marginTop: 16, zIndex: 10,
          display: "flex", alignItems: "center", gap: 12, padding: "10px 14px",
          background: "var(--surface)", border: "1px solid var(--accent-border)",
          borderRadius: 10, boxShadow: "var(--shadow-lg)",
        }}>
          <Icon name="alert-triangle" size={14} style={{ color: "var(--warn)" }} />
          <span style={{ fontSize: 13, fontWeight: 500 }}>
            Несохранённых изменений: {dirtyFields.length}
          </span>
          <span className="muted small" style={{ flex: 1 }}>{dirtyFields.join(", ")}</span>
          <button className="btn btn-ghost" onClick={cancel} disabled={busy}>Отменить</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>Сохранить</button>
        </div>
      )}
    </>
  );
}

function ProbePolicySection() {
  const q = useQuery(() => api.get("/admin/probe/policy"), { interval: 0 });
  const [f, setF] = useState(null);
  const [initial, setInitial] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.data) { setF(q.data); setInitial(q.data); }
  }, [q.data]);

  const set = (k) => (e) => {
    const val = e.target.type === "checkbox" ? e.target.checked
      : (e.target.type === "number" ? Number(e.target.value) : e.target.value);
    setF((s) => ({ ...s, [k]: val }));
  };

  const dirtyFields = useMemo(() => {
    if (!f || !initial) return [];
    return Object.keys(f).filter((k) => {
      if (k === "id" || k === "created_at" || k === "updated_at") return false;
      return JSON.stringify(f[k]) !== JSON.stringify(initial[k]);
    });
  }, [f, initial]);
  const dirty = dirtyFields.length > 0;

  const save = async () => {
    setBusy(true);
    try {
      const payload = {};
      for (const k of dirtyFields) payload[k] = f[k] === "" ? null : f[k];
      const updated = await api.patch("/admin/probe/policy", payload);
      setF(updated);
      setInitial(updated);
      toast.ok(`Сохранено · ${dirtyFields.length} изменений`);
    } catch (e) { toast.bad(e.message || "Ошибка"); }
    finally { setBusy(false); }
  };

  const cancel = () => setF(initial);

  if (!f) return <div className="card"><div className="card-body muted">Загрузка…</div></div>;

  const killSwitchOff = !f.auto_route_health_enabled;

  return (
    <>
      <div className="card">
        <div className="card-head" style={{ position: "sticky", top: 0, background: "var(--surface)", zIndex: 5 }}>
          <Icon name="shield-check" size={14} />
          <div className="sec-title">Probe-политика</div>
          <div className="sec-sub">{killSwitchOff ? "автоматика выключена глобально" : "автоматика активна"}</div>
          <div className="sec-spacer" />
          <label className="form-check" style={{ margin: 0 }}>
            <input type="checkbox" checked={!!f.auto_route_health_enabled} onChange={set("auto_route_health_enabled")} />
            <span>Включена</span>
          </label>
        </div>

        <div style={{ opacity: killSwitchOff ? 0.5 : 1, transition: "opacity 150ms ease" }}>
          <Section title="Пороги маршрутов" subtitle="когда переводить route в suspected/degraded/blocked" icon="route" defaultOpen>
            <div className="form-row">
              <Field label="Suspected после N fail" hint="1–50">
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

          <Section title="Авто-drain нод" subtitle={f.auto_drain_enabled ? "активен" : "выключен"} icon="pause" toneWhenClosed={f.auto_drain_enabled ? "ok" : ""}>
            <label className="form-check" style={{ marginBottom: 10 }}>
              <input type="checkbox" checked={f.auto_drain_enabled} onChange={set("auto_drain_enabled")} /> Включить
            </label>
            <div className="form-row">
              <Field label="Тик, секунд"><input type="number" min={30} max={3600} value={f.auto_drain_tick_sec} onChange={set("auto_drain_tick_sec")} /></Field>
              <Field label="Мин. подряд fail"><input type="number" min={1} max={50} value={f.auto_drain_min_consecutive_failures} onChange={set("auto_drain_min_consecutive_failures")} /></Field>
            </div>
            <div className="form-row">
              <Field label="Макс. возраст probe, сек"><input type="number" min={60} max={86400} value={f.auto_drain_max_probe_age_sec} onChange={set("auto_drain_max_probe_age_sec")} /></Field>
              <Field label="Макс. нод за тик"><input type="number" min={1} max={500} value={f.auto_drain_max_nodes} onChange={set("auto_drain_max_nodes")} /></Field>
            </div>
            <div className="form-row">
              <Field label="Drain source" hint="имя probe-источника">
                <input type="text" value={f.auto_drain_source || ""} onChange={set("auto_drain_source")} placeholder="probe-prod-entry" />
              </Field>
              <Field label="Reason label">
                <input type="text" value={f.auto_drain_last_migration_reason || ""} onChange={set("auto_drain_last_migration_reason")} />
              </Field>
            </div>
            <Field label="Target backend (UUID)" hint="пусто = авто">
              <input type="text" value={f.auto_drain_target_backend_id || ""} onChange={set("auto_drain_target_backend_id")} placeholder="—" />
            </Field>
            <label className="form-check">
              <input type="checkbox" checked={!!f.auto_drain_require_recent_failure} onChange={set("auto_drain_require_recent_failure")} /> Требовать свежий probe failure
            </label>
            <label className="form-check" style={{ marginTop: 6 }}>
              <input type="checkbox" checked={!!f.auto_drain_include_already_draining} onChange={set("auto_drain_include_already_draining")} /> Включать уже draining ноды
            </label>
          </Section>

          <Section title="Авто-undrain нод" subtitle={f.auto_undrain_enabled ? "активен" : "выключен"} icon="play" toneWhenClosed={f.auto_undrain_enabled ? "ok" : ""}>
            <label className="form-check" style={{ marginBottom: 10 }}>
              <input type="checkbox" checked={f.auto_undrain_enabled} onChange={set("auto_undrain_enabled")} /> Включить
            </label>
            <div className="form-row">
              <Field label="Мин. подряд OK"><input type="number" min={1} max={50} value={f.auto_undrain_min_consecutive_successes} onChange={set("auto_undrain_min_consecutive_successes")} /></Field>
              <Field label="Макс. возраст probe, сек"><input type="number" min={60} max={86400} value={f.auto_undrain_max_probe_age_sec} onChange={set("auto_undrain_max_probe_age_sec")} /></Field>
            </div>
            <Field label="Undrain source" hint="пусто = тот же что и drain">
              <input type="text" value={f.auto_undrain_source || ""} onChange={set("auto_undrain_source")} />
            </Field>
          </Section>

          <Section title="Хранение и cleanup" subtitle={`retention ${f.retention_days}д · tick ${f.cleanup_tick_sec}s`} icon="clock">
            <div className="form-row">
              <Field label="Retention, дней"><input type="number" min={1} max={365} value={f.retention_days} onChange={set("retention_days")} /></Field>
              <Field label="Cleanup tick, сек"><input type="number" min={60} max={86400} value={f.cleanup_tick_sec} onChange={set("cleanup_tick_sec")} /></Field>
            </div>
            <label className="form-check">
              <input type="checkbox" checked={!!f.cleanup_enabled} onChange={set("cleanup_enabled")} /> Включить cleanup
            </label>
          </Section>

          <Section title="Synthetic probe" subtitle={f.synthetic_reconcile_enabled ? "активен" : "выключен"} icon="radar" toneWhenClosed={f.synthetic_reconcile_enabled ? "ok" : ""}>
            <label className="form-check" style={{ marginBottom: 10 }}>
              <input type="checkbox" checked={!!f.synthetic_reconcile_enabled} onChange={set("synthetic_reconcile_enabled")} /> Включить synthetic probe reconcile
            </label>
            <div className="form-row">
              <Field label="Tick, сек"><input type="number" min={30} max={86400} value={f.synthetic_reconcile_tick_sec} onChange={set("synthetic_reconcile_tick_sec")} /></Field>
              <Field label="Срок ключа, дней"><input type="number" min={1} max={36500} value={f.synthetic_key_valid_days} onChange={set("synthetic_key_valid_days")} /></Field>
            </div>
            <Field label="Лимит трафика synthetic-ключа, MB">
              <input type="number" min={1} max={10485760} value={f.synthetic_key_traffic_limit_mb} onChange={set("synthetic_key_traffic_limit_mb")} />
            </Field>
          </Section>
        </div>
      </div>

      {dirty && (
        <div style={{
          position: "sticky", bottom: 12, marginTop: 16, zIndex: 10,
          display: "flex", alignItems: "center", gap: 12, padding: "10px 14px",
          background: "var(--surface)", border: "1px solid var(--accent-border)",
          borderRadius: 10, boxShadow: "var(--shadow-lg)",
        }}>
          <Icon name="alert-triangle" size={14} style={{ color: "var(--warn)" }} />
          <span style={{ fontSize: 13, fontWeight: 500 }}>
            Несохранённых изменений: {dirtyFields.length}
          </span>
          <span className="muted small" style={{ flex: 1 }} title={dirtyFields.join(", ")}>
            {dirtyFields.slice(0, 4).join(", ")}{dirtyFields.length > 4 ? `, +${dirtyFields.length - 4}` : ""}
          </span>
          <button className="btn btn-ghost" onClick={cancel} disabled={busy}>Отменить</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>Сохранить</button>
        </div>
      )}
    </>
  );
}

function NodePolicySection() {
  const q = useQuery(() => api.get("/admin/nodes/policy"), { interval: 0 });
  const [f, setF] = useState(null);
  const [initial, setInitial] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.data) { setF(q.data); setInitial(q.data); }
  }, [q.data]);

  const set = (k) => (e) => {
    const val = e.target.type === "checkbox" ? e.target.checked
      : (e.target.type === "number" ? Number(e.target.value) : e.target.value);
    setF((s) => ({ ...s, [k]: val }));
  };

  const dirtyFields = useMemo(() => {
    if (!f || !initial) return [];
    return Object.keys(f).filter((k) => {
      if (k === "id" || k === "created_at" || k === "updated_at") return false;
      return JSON.stringify(f[k]) !== JSON.stringify(initial[k]);
    });
  }, [f, initial]);
  const dirty = dirtyFields.length > 0;

  const save = async () => {
    setBusy(true);
    try {
      const payload = {};
      for (const k of dirtyFields) payload[k] = f[k] === "" ? null : f[k];
      const updated = await api.patch("/admin/nodes/policy", payload);
      setF(updated);
      setInitial(updated);
      toast.ok(`Сохранено · ${dirtyFields.length} изменений`);
    } catch (e) { toast.bad(e.message || "Ошибка"); }
    finally { setBusy(false); }
  };

  const cancel = () => setF(initial);

  if (!f) return <div className="card"><div className="card-body muted">Загрузка…</div></div>;

  return (
    <>
      <div className="card">
        <div className="card-head">
          <Icon name="server" size={14} />
          <div className="sec-title">Ноды и placements</div>
          <div className="sec-sub">heartbeat, auto-heal, rebalance, entry pool</div>
        </div>

        <Section title="Heartbeat" subtitle={`stale ${f.stale_after_sec}s · drain x${f.heartbeat_unhealthy_drain_threshold} · undrain x${f.heartbeat_healthy_undrain_threshold}`} icon="activity" defaultOpen>
          <div className="form-row">
            <Field label="Stale after, сек" hint="нода считается потерянной">
              <input type="number" min={30} max={3600} value={f.stale_after_sec} onChange={set("stale_after_sec")} />
            </Field>
            <Field label="Unhealthy drain threshold" hint="подряд fail → auto-drain">
              <input type="number" min={1} max={50} value={f.heartbeat_unhealthy_drain_threshold} onChange={set("heartbeat_unhealthy_drain_threshold")} />
            </Field>
            <Field label="Healthy undrain threshold" hint="подряд OK → undrain">
              <input type="number" min={1} max={50} value={f.heartbeat_healthy_undrain_threshold} onChange={set("heartbeat_healthy_undrain_threshold")} />
            </Field>
          </div>
        </Section>

        <Section title="Auto-heal (drain + migrate)" subtitle={f.auto_heal_enabled ? "активен" : "выключен"} icon="wrench" toneWhenClosed={f.auto_heal_enabled ? "ok" : ""}>
          <label className="form-check" style={{ marginBottom: 10 }}>
            <input type="checkbox" checked={!!f.auto_heal_enabled} onChange={set("auto_heal_enabled")} /> Включить drain + migrate stale backends
          </label>
          <div className="form-row">
            <Field label="Tick, сек"><input type="number" min={30} max={3600} value={f.auto_heal_tick_sec} onChange={set("auto_heal_tick_sec")} /></Field>
            <Field label="Макс. нод за тик"><input type="number" min={1} max={500} value={f.auto_heal_max_nodes} onChange={set("auto_heal_max_nodes")} /></Field>
            <Field label="Drain cooldown, сек"><input type="number" min={0} max={86400} value={f.auto_heal_drain_cooldown_sec} onChange={set("auto_heal_drain_cooldown_sec")} /></Field>
          </div>
          <label className="form-check">
            <input type="checkbox" checked={!!f.auto_undrain_enabled} onChange={set("auto_undrain_enabled")} /> Auto-undrain восстановившихся нод
          </label>
        </Section>

        <Section title="Placement error retry" subtitle={f.placement_error_retry_enabled ? "активен" : "выключен"} icon="refresh" toneWhenClosed={f.placement_error_retry_enabled ? "ok" : ""}>
          <label className="form-check" style={{ marginBottom: 10 }}>
            <input type="checkbox" checked={!!f.placement_error_retry_enabled} onChange={set("placement_error_retry_enabled")} /> Включить retry упавших placements
          </label>
          <div className="form-row">
            <Field label="Tick, сек"><input type="number" min={30} max={3600} value={f.placement_error_retry_tick_sec} onChange={set("placement_error_retry_tick_sec")} /></Field>
            <Field label="Retry после, сек" hint="minimum age перед retry"><input type="number" min={30} max={86400} value={f.placement_error_retry_after_sec} onChange={set("placement_error_retry_after_sec")} /></Field>
          </div>
        </Section>

        <Section title="Placement rebalance" subtitle={f.placement_rebalance_enabled ? "активен" : "выключен"} icon="layers" toneWhenClosed={f.placement_rebalance_enabled ? "ok" : ""}>
          <label className="form-check" style={{ marginBottom: 10 }}>
            <input type="checkbox" checked={!!f.placement_rebalance_enabled} onChange={set("placement_rebalance_enabled")} /> Перераспределять placements со stale backends
          </label>
          <div className="form-row">
            <Field label="Tick, сек"><input type="number" min={30} max={3600} value={f.placement_rebalance_tick_sec} onChange={set("placement_rebalance_tick_sec")} /></Field>
            <Field label="Batch size"><input type="number" min={1} max={10000} value={f.placement_rebalance_batch_size} onChange={set("placement_rebalance_batch_size")} /></Field>
          </div>
        </Section>

        <Section title="Entry pool drain" subtitle={f.entry_auto_drain_enabled ? "активен" : "выключен"} icon="globe" toneWhenClosed={f.entry_auto_drain_enabled ? "ok" : ""}>
          <label className="form-check" style={{ marginBottom: 10 }}>
            <input type="checkbox" checked={!!f.entry_auto_drain_enabled} onChange={set("entry_auto_drain_enabled")} /> Auto-drain entry-нод по probe-фейлам
          </label>
          <div className="form-row">
            <Field label="Tick, сек"><input type="number" min={15} max={3600} value={f.entry_auto_drain_tick_sec} onChange={set("entry_auto_drain_tick_sec")} /></Field>
            <Field label="Probe failures threshold"><input type="number" min={1} max={50} value={f.entry_auto_drain_probe_failures} onChange={set("entry_auto_drain_probe_failures")} /></Field>
            <Field label="Макс. нод за тик"><input type="number" min={1} max={500} value={f.entry_auto_drain_max_nodes} onChange={set("entry_auto_drain_max_nodes")} /></Field>
          </div>
          <Field label="Reason label">
            <input type="text" maxLength={64} value={f.entry_auto_drain_reason || ""} onChange={set("entry_auto_drain_reason")} />
          </Field>
          <label className="form-check" style={{ marginTop: 8 }}>
            <input type="checkbox" checked={!!f.entry_auto_undrain_enabled} onChange={set("entry_auto_undrain_enabled")} /> Auto-undrain entry-нод после восстановления
          </label>
          <Field label="Healthy ticks для undrain">
            <input type="number" min={1} max={50} value={f.entry_auto_undrain_healthy_ticks} onChange={set("entry_auto_undrain_healthy_ticks")} />
          </Field>
        </Section>

        <Section title="Entry apply" subtitle={`fail threshold ${f.entry_apply_fail_threshold}`} icon="alert-triangle">
          <div className="form-row">
            <Field label="Fail threshold" hint="подряд fail apply → пометить unhealthy">
              <input type="number" min={1} max={50} value={f.entry_apply_fail_threshold} onChange={set("entry_apply_fail_threshold")} />
            </Field>
          </div>
          <label className="form-check">
            <input type="checkbox" checked={!!f.entry_apply_fail_unhealthy} onChange={set("entry_apply_fail_unhealthy")} /> Помечать unhealthy при превышении
          </label>
        </Section>
      </div>

      {dirty && (
        <div style={{
          position: "sticky", bottom: 12, marginTop: 16, zIndex: 10,
          display: "flex", alignItems: "center", gap: 12, padding: "10px 14px",
          background: "var(--surface)", border: "1px solid var(--accent-border)",
          borderRadius: 10, boxShadow: "var(--shadow-lg)",
        }}>
          <Icon name="alert-triangle" size={14} style={{ color: "var(--warn)" }} />
          <span style={{ fontSize: 13, fontWeight: 500 }}>
            Несохранённых изменений: {dirtyFields.length}
          </span>
          <span className="muted small" style={{ flex: 1 }} title={dirtyFields.join(", ")}>
            {dirtyFields.slice(0, 4).join(", ")}{dirtyFields.length > 4 ? `, +${dirtyFields.length - 4}` : ""}
          </span>
          <button className="btn btn-ghost" onClick={cancel} disabled={busy}>Отменить</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>Сохранить</button>
        </div>
      )}
    </>
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
            <div className="small" style={{ color: toneWhenClosed === "ok" ? "var(--ok)" : "var(--text-muted)", marginTop: 2 }}>
              {subtitle}
            </div>
          )}
        </div>
        <Icon name={open ? "chevron-down" : "chevron-right"} size={14} style={{ color: "var(--text-muted)" }} />
      </button>
      {open && <div style={{ padding: "4px 14px 16px" }}>{children}</div>}
    </div>
  );
}
