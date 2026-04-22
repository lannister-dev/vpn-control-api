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
      const payload = {
        route_suspected_after_failures: f.route_suspected_after_failures,
        route_degraded_after_failures: f.route_degraded_after_failures,
        route_block_after_failures: f.route_block_after_failures,
        route_block_cooldown_hours: f.route_block_cooldown_hours,
        auto_drain_enabled: f.auto_drain_enabled,
        auto_drain_tick_sec: f.auto_drain_tick_sec,
        auto_drain_min_consecutive_failures: f.auto_drain_min_consecutive_failures,
        auto_drain_max_probe_age_sec: f.auto_drain_max_probe_age_sec,
        auto_drain_max_nodes: f.auto_drain_max_nodes,
        auto_undrain_enabled: f.auto_undrain_enabled,
        auto_undrain_min_consecutive_successes: f.auto_undrain_min_consecutive_successes,
        auto_undrain_max_probe_age_sec: f.auto_undrain_max_probe_age_sec,
      };
      const updated = await api.patch("/admin/probe/policy", payload);
      setF(updated);
      toast.ok("Probe-политика обновлена");
    } catch (e) { toast.bad(e.message || "Ошибка"); }
    finally { setBusy(false); }
  };

  return (
    <div className="card">
      <div className="card-head">
        <Icon name="shield-check" size={14} />
        <div className="sec-title">Probe-политика</div>
        <div className="sec-sub">пороги блокировки маршрутов + авто-drain</div>
      </div>
      <div className="card-body">
        <div className="split-2">
          <div>
            <div className="kpi-label" style={{ marginBottom: 8 }}>Пороги маршрутов (подряд неудачных probe)</div>
            <div className="form-row">
              <Field label="Suspected после">
                <input type="number" min={1} max={50} value={f.route_suspected_after_failures} onChange={set("route_suspected_after_failures")} />
              </Field>
              <Field label="Degraded после">
                <input type="number" min={2} max={50} value={f.route_degraded_after_failures} onChange={set("route_degraded_after_failures")} />
              </Field>
            </div>
            <div className="form-row">
              <Field label="Block после">
                <input type="number" min={3} max={50} value={f.route_block_after_failures} onChange={set("route_block_after_failures")} />
              </Field>
              <Field label="Cooldown, часов">
                <input type="number" min={1} max={168} value={f.route_block_cooldown_hours} onChange={set("route_block_cooldown_hours")} />
              </Field>
            </div>
          </div>
          <div>
            <div className="kpi-label" style={{ marginBottom: 8 }}>Авто-drain нод</div>
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
            <label className="form-check" style={{ marginTop: 10 }}>
              <input type="checkbox" checked={f.auto_undrain_enabled} onChange={set("auto_undrain_enabled")} />
              Авто-снятие drain при восстановлении
            </label>
            <div className="form-row" style={{ marginTop: 8 }}>
              <Field label="Мин. подряд OK">
                <input type="number" min={1} max={50} value={f.auto_undrain_min_consecutive_successes} onChange={set("auto_undrain_min_consecutive_successes")} />
              </Field>
              <Field label="Макс. возраст probe, сек">
                <input type="number" min={60} max={86400} value={f.auto_undrain_max_probe_age_sec} onChange={set("auto_undrain_max_probe_age_sec")} />
              </Field>
            </div>
          </div>
        </div>
      </div>
      <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button className="btn btn-ghost" onClick={() => q.refetch()} disabled={busy}>Отменить</button>
        <button className="btn btn-primary" onClick={save} disabled={busy}>Сохранить</button>
      </div>
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
