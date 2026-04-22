import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Field } from "../components/Field.jsx";
import { Icon } from "../components/Icon.jsx";

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
