import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Drawer } from "./Drawer.jsx";
import { Modal } from "./Modal.jsx";
import { Field } from "./Field.jsx";
import { Icon } from "./Icon.jsx";
import { Spark } from "./Spark.jsx";
import { RouteForm } from "./RouteForm.jsx";
import { toast } from "./Toast.jsx";
import { nodeGeo } from "../lib/geo.js";
import { nodeLoad } from "../lib/nodeLoad.js";

const isEntryRole = (n) => ["entry", "whitelist_entry"].includes(String(n?.role || "").toLowerCase());

function spark(seed, len = 48, base = 50, vol = 30) {
  let x = seed || 7;
  const out = [];
  for (let i = 0; i < len; i++) {
    x = (x * 9301 + 49297) % 233280;
    out.push(base + ((x / 233280) - 0.5) * vol * 2);
  }
  return out;
}

function relTime(iso) {
  if (!iso) return "—";
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h`;
}

function healthTone(n) {
  if (!n.is_enabled) return "bad";
  if (n.is_draining) return "warn";
  return n.is_healthy ? "ok" : "bad";
}

function stateOf(n) {
  if (!n.is_enabled) return "disabled";
  if (n.is_draining) return "draining";
  return "active";
}

const DRAIN_REASON_LABELS = {
  probe_auto_failure: "probe: авто-дрейн",
  unhealthy_heartbeat: "heartbeat: unhealthy",
  manual_admin: "админ",
  entry_auto_drain: "entry pool: авто",
  probe_synthetic_self_heal: "synthetic self-heal",
};

function drainReasonLabel(reason) {
  if (!reason) return "";
  return DRAIN_REASON_LABELS[reason] || reason;
}

export function NodeDrawer({ node, onClose, onGoto, onOpenNode, initialTab, focusRouteId }) {
  const entryRole = isEntryRole(node);
  const fallbackTab = initialTab || "overview";
  const [tab, setTab] = useState(fallbackTab);
  const [sshOpen, setSshOpen] = useState(false);

  useEffect(() => {
    if (!initialTab) return;
    if (initialTab === "pool" && !entryRole) {
      setTab("overview");
      return;
    }
    setTab(initialTab);
  }, [initialTab, node?.id, entryRole]);

  const routes = useQuery(() => api.get("/routes?limit=500"), { interval: 15000 });
  const transport = useQuery(() => api.get("/admin/transport/nodes"), { interval: 30000 });
  const status = useQuery(() => api.get("/admin/status"), { interval: 30000 });
  const routesCount = (routes.data || []).filter((r) => r.node_id === node.id || r.entry_node_id === node.id).length;

  const tabs = [
    { id: "overview", label: "Обзор" },
    { id: "routes", label: `Маршруты · ${routesCount}` },
    { id: "probes", label: "Probes" },
    { id: "transport", label: "Transport" },
    ...(entryRole ? [{ id: "pool", label: "Pool" }] : []),
  ];

  const geo = nodeGeo(node.region);
  const tone = healthTone(node);

  const head = (
    <>
      <span className={`status-dot ${tone} ${tone === "bad" ? "pulse" : ""}`} style={{ marginTop: 6 }} />
      <div className="slideover-title-main">
        <div className="slideover-title" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span>{geo.flag}</span>
          <span>{node.name}</span>
          <span className="pill">{node.role}</span>
        </div>
        <div className="slideover-sub">
          <span className="mono">{String(node.id).slice(0, 12)}</span> · {node.region} · heartbeat {relTime(node.last_seen_at)}
        </div>
      </div>
    </>
  );

  return (
    <Drawer
      head={head}
      onClose={onClose}
      tabs={tabs}
      activeTab={tab}
      onTab={setTab}
      actions={<button className="btn btn-ghost btn-icon" title="Действия"><Icon name="more-horizontal" size={15} /></button>}
    >
      {tab === "overview" && (
        <NodeOverview
          node={node}
          routesCount={routesCount}
          transportData={transport.data}
          onSshClick={() => setSshOpen(true)}
          onMigrateClick={() => { onGoto?.("ops"); onClose(); }}
        />
      )}
      {tab === "routes" && (
        <NodeRoutes
          node={node}
          routes={routes.data || []}
          allNodes={status.data?.nodes || []}
          focusRouteId={focusRouteId}
          onRefresh={routes.refetch}
        />
      )}
      {tab === "probes" && <NodeProbes node={node} />}
      {tab === "transport" && <NodeTransport node={node} />}
      {tab === "pool" && entryRole && <NodePool node={node} onOpenNode={onOpenNode} />}
      {sshOpen && <SshHintModal node={node} onClose={() => setSshOpen(false)} />}
    </Drawer>
  );
}

function SshHintModal({ node, onClose }) {
  const host = node.reality_ip || node.public_domain || node.internal_wg_ip || "";
  const user = "root";
  const cmd = host ? `ssh ${user}@${host}` : "—";
  const sshUrl = host ? `ssh://${user}@${host}` : null;

  const copy = () => {
    if (!host) return;
    navigator.clipboard.writeText(cmd).then(() => toast.ok("Команда скопирована"));
  };

  const openInTerminal = () => {
    if (!sshUrl) return;
    window.location.href = sshUrl;
  };

  return (
    <Modal title={`SSH · ${node.name}`} onClose={onClose} footer={
      <>
        <button className="btn btn-ghost" onClick={onClose}>Закрыть</button>
        <button className="btn" onClick={copy} disabled={!host}>
          <Icon name="command" size={12} /> Скопировать команду
        </button>
        <button className="btn btn-primary" onClick={openInTerminal} disabled={!sshUrl}>
          <Icon name="terminal" size={12} /> Открыть в терминале
        </button>
      </>
    }>
      <Field label="Host">
        <input type="text" readOnly value={host || "—"} style={{ fontFamily: "var(--font-mono)", fontSize: 12 }} />
      </Field>
      <Field label="Команда">
        <input type="text" readOnly value={cmd} style={{ fontFamily: "var(--font-mono)", fontSize: 12 }} />
      </Field>
      <div className="muted small">
        Кнопка «Открыть в терминале» использует системный <span className="mono">ssh://</span> handler — запускается iTerm / Terminal на macOS и настроенный SSH-клиент на Windows/Linux. Если ничего не открывается, скопируйте команду и запустите вручную.
        Убедитесь что ваш публичный ключ лежит в <span className="mono">~root/.ssh/authorized_keys</span> на ноде.
      </div>
    </Modal>
  );
}

function NodeOverview({ node, routesCount, transportData, onSshClick, onMigrateClick }) {
  const load = nodeLoad(node);
  const loadPct = load.pct;
  const loadTone = load.tone;
  const loadBarWidth = loadPct == null ? 0 : Math.min(100, loadPct);
  const tone = healthTone(node);
  const st = stateOf(node);

  const transport = (transportData?.items || []).find((t) => t.node_id === node.id);
  const epoch = transport?.current_epoch ?? null;
  const outboxPending = transport?.outbox_pending ?? 0;
  const outboxFailed = transport?.outbox_failed ?? 0;

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 20 }}>
        <div className="card">
          <div className="card-body" style={{ padding: 14 }} title={load.tooltip}>
            <div className="kpi-label"><Icon name="activity" size={12} /> Нагрузка</div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div className="kpi-value" style={{ fontSize: 22 }}>
                {loadPct != null ? <>{loadPct}<span className="kpi-unit">%</span></> : <span className="muted">—</span>}
              </div>
              <div style={{ flex: 1, height: 6, background: "var(--surface-2)", borderRadius: 4, overflow: "hidden" }}>
                <div style={{ width: `${loadBarWidth}%`, height: "100%", background: `var(--${loadTone})` }} />
              </div>
            </div>
            <div className="muted small" style={{ marginTop: 6 }}>
              {load.used} / {load.capacity ?? "—"} placements
              {load.capacity == null && <span style={{ marginLeft: 6 }}>· capacity не задан</span>}
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-body" style={{ padding: 14 }}>
            <div className="kpi-label"><Icon name="git-branch" size={12} /> Очередь команд</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <div className="kpi-value" style={{ fontSize: 22 }}>{outboxPending}</div>
              {outboxFailed > 0 && <span className="pill bad">err {outboxFailed}</span>}
            </div>
            <div className="muted small" style={{ marginTop: 6 }}>ресинков: {epoch ?? "—"}</div>
          </div>
        </div>
      </div>

      <div className="sec-head"><div className="sec-title">Параметры</div></div>
      <dl className="kv" style={{ marginBottom: 20 }}>
        <dt>UUID</dt><dd className="mono">{node.id}</dd>
        <dt>Регион</dt><dd>{nodeGeo(node.region).flag} {node.region}</dd>
        <dt>Зона</dt><dd>{node.zone || <span className="muted">—</span>}</dd>
        <dt>Роль</dt><dd>{node.role}</dd>
        <dt>Статус</dt><dd>
          <span className={`pill ${st === "active" ? "ok" : st === "draining" ? "warn" : ""}`}>{st}</span>
          {st === "draining" && node.drain_reason && (
            <span className="mono muted" style={{ fontSize: 11, marginLeft: 8 }} title={node.drained_at ? `с ${new Date(node.drained_at).toLocaleString()}` : ""}>
              {drainReasonLabel(node.drain_reason)}
            </span>
          )}
        </dd>
        <dt>Здоровье</dt><dd><span className={`pill ${tone}`}><span className={`status-dot ${tone}`} /> {tone === "ok" ? "healthy" : tone === "warn" ? "degraded" : "unhealthy"}</span></dd>
        <dt>Нагрузка</dt><dd>
          <div title={load.tooltip} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ flex: 1, height: 6, background: "var(--surface-2)", borderRadius: 4, overflow: "hidden", maxWidth: 140 }}>
              <div style={{ width: `${loadBarWidth}%`, height: "100%", background: `var(--${loadTone})` }} />
            </div>
            <span className="mono" style={{ color: `var(--${loadTone})`, fontWeight: 500, whiteSpace: "nowrap" }}>
              {load.label}{loadPct != null ? ` · ${loadPct}%` : ""}
            </span>
          </div>
        </dd>
        <dt>Capacity</dt><dd className="mono">{node.capacity ?? <span className="muted">—</span>}</dd>
        <dt>Heartbeat</dt><dd className="mono">{relTime(node.last_seen_at)} назад</dd>
        <dt>Маршрутов</dt><dd className="mono">{routesCount}</dd>
        {(node.upstream_name || node.upstream_node_id) && (
          <>
            <dt>Upstream</dt>
            <dd>
              <span style={{ fontWeight: 500 }}>{node.upstream_name || String(node.upstream_node_id).slice(0, 8) + "…"}</span>
              <div className="mono muted small">{node.upstream_node_id}</div>
            </dd>
          </>
        )}
        <dt>Public domain</dt><dd className="mono small">{node.public_domain || "—"}</dd>
        <dt>Reality IP</dt><dd className="mono small">{node.reality_ip || "—"}</dd>
      </dl>

      <div className="sec-head"><div className="sec-title">Быстрые действия</div></div>
      <QuickActions node={node} onSshClick={onSshClick} onMigrateClick={onMigrateClick} />
    </div>
  );
}

function QuickActions({ node, onSshClick, onMigrateClick }) {
  const [busy, setBusy] = useState(null);
  const run = async (key, fn) => {
    setBusy(key);
    try { await fn(); }
    finally { setBusy(null); }
  };

  const drain = () => run("drain", async () => {
    try {
      if (node.is_draining) {
        await api.post(`/agent/nodes/${node.id}/enable`);
        toast.ok("Drain снят");
      } else {
        if (!confirm(`Включить drain для ${node.name}?\nКлючи перестанут на неё назначаться, существующие уйдут на другие ноды.`)) return;
        await api.post(`/agent/nodes/${node.id}/drain`);
        toast.ok("Drain включён");
      }
    } catch (e) { toast.bad(e.message || "Ошибка"); }
  });

  const snapshot = () => run("snapshot", async () => {
    try {
      const r = await api.post(`/admin/transport/nodes/${node.id}/request-snapshot`);
      toast.ok(`Snapshot запрошен · ресинков ${r.epoch}`);
    } catch (e) { toast.bad(e.message || "Ошибка"); }
  });

  const toggleEnabled = () => run("toggle", async () => {
    try {
      if (node.is_enabled && !confirm(`Отключить ${node.name}?\nВсе маршруты и назначения перестанут работать.`)) return;
      await api.patch(`/agent/nodes/${node.id}`, { is_enabled: !node.is_enabled });
      toast.ok(node.is_enabled ? "Нода отключена" : "Нода включена");
    } catch (e) { toast.bad(e.message || "Ошибка"); }
  });

  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      <button className="btn" onClick={drain} disabled={busy === "drain"} title={node.is_draining ? "Снять drain" : "Включить drain"}>
        <Icon name="pause" size={12} /> {node.is_draining ? "Снять drain" : "Drain"}
      </button>
      <button className="btn" onClick={onMigrateClick} title="Открыть страницу Операции с выбранной нодой в миграции">
        <Icon name="arrow-right" size={12} /> Migrate
      </button>
      <button className="btn" onClick={snapshot} disabled={busy === "snapshot"}>
        <Icon name="refresh" size={12} /> Snapshot
      </button>
      <button className="btn" onClick={onSshClick}>
        <Icon name="terminal" size={12} /> SSH
      </button>
      <button className="btn" onClick={toggleEnabled} disabled={busy === "toggle"}>
        <Icon name="power" size={12} /> {node.is_enabled ? "Отключить" : "Включить"}
      </button>
    </div>
  );
}

function NodeRoutes({ node, routes, allNodes, focusRouteId, onRefresh }) {
  const list = useMemo(
    () => routes.filter((r) => r.node_id === node.id || r.entry_node_id === node.id),
    [routes, node.id],
  );
  const isBackend = String(node.role).toLowerCase() === "backend";
  const focusedRowRef = useRef(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);

  useEffect(() => {
    if (focusRouteId && focusedRowRef.current) {
      focusedRowRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [focusRouteId, list.length]);

  const apply = async (route, action, opts = {}) => {
    const label = opts.label || action;
    try {
      if (action === "deactivate") {
        if (!confirm(`Деактивировать маршрут ${route.name}?`)) return;
        await api.post(`/routes/${route.id}/deactivate`);
      } else if (action === "activate") {
        await api.post(`/routes/${route.id}/activate`);
      } else {
        await api.post("/admin/set-route-health", {
          route_id: route.id,
          action,
          cooldown_hours: 6,
        });
      }
      toast.ok(`${route.name} → ${label}`);
      onRefresh?.();
    } catch (e) { toast.bad(e.message || "Ошибка"); }
  };

  const closeForm = (saved) => {
    setCreating(false);
    setEditing(null);
    if (saved) onRefresh?.();
  };

  const head = (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, gap: 8 }}>
      <div className="muted small">
        {list.length
          ? `${list.length} маршрутов через эту ноду`
          : "Маршрутов через эту ноду пока нет"}
      </div>
      {isBackend && allNodes.length > 0 && (
        <button className="btn btn-primary" onClick={() => setCreating(true)} title="Создать маршрут с этой backend-ноды">
          <Icon name="plus" size={12} /> Создать с этой ноды
        </button>
      )}
    </div>
  );

  if (!list.length) {
    return (
      <>
        {head}
        <div className="muted" style={{ padding: 14 }}>Маршрутов нет.</div>
        {creating && (
          <RouteForm
            nodes={allNodes}
            defaults={isBackend ? { node_id: node.id } : { entry_node_id: node.id }}
            onClose={closeForm}
          />
        )}
      </>
    );
  }

  return (
    <>
      {head}
      <table className="tbl">
        <thead>
          <tr>
            <th>Маршрут</th>
            <th>Направление</th>
            <th>Status</th>
            <th style={{ textAlign: "right" }}>Weight</th>
            <th style={{ width: 40 }}></th>
          </tr>
        </thead>
        <tbody>
          {list.map((r) => {
            const focused = focusRouteId && r.id === focusRouteId;
            return (
              <tr
                key={r.id}
                ref={focused ? focusedRowRef : null}
                style={{
                  opacity: r.is_active ? 1 : 0.55,
                  background: focused ? "var(--surface-hover)" : undefined,
                  outline: focused ? "1px solid var(--accent)" : undefined,
                  outlineOffset: focused ? "-1px" : undefined,
                }}
              >
                <td>
                  <span style={{ fontWeight: focused ? 600 : 400 }}>{r.name}</span>
                  {!r.is_active && <span className="pill muted" style={{ marginLeft: 6 }}>off</span>}
                </td>
                <td className="small muted">{r.node_id === node.id ? "backend" : "entry"}</td>
                <td>
                  {r.is_active
                    ? <span className={"pill " + toneOf(r.health_status)}>{r.health_status}</span>
                    : <span className="pill muted">не активен</span>}
                </td>
                <td className="tbl-num mono">{r.effective_weight}</td>
                <td className="row-actions" onClick={(e) => e.stopPropagation()}>
                  <RouteRowMenu route={r} apply={apply} onEdit={() => setEditing(r)} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {creating && (
        <RouteForm
          nodes={allNodes}
          defaults={isBackend ? { node_id: node.id } : { entry_node_id: node.id }}
          onClose={closeForm}
        />
      )}
      {editing && (
        <RouteForm
          route={editing}
          nodes={allNodes}
          onClose={closeForm}
        />
      )}
    </>
  );
}

function RouteRowMenu({ route, apply, onEdit }) {
  const [open, setOpen] = useState(false);
  const items = [];
  if (onEdit) items.push({ icon: "edit", label: "Редактировать", action: "edit" });
  if (route.health_status !== "healthy") items.push({ icon: "check", label: "Set healthy", action: "set_healthy" });
  if (route.health_status !== "blocked") items.push({ icon: "alert-circle", label: "Block", action: "block", danger: true });
  if (route.health_status === "blocked") items.push({ icon: "refresh", label: "Recover", action: "recover" });
  if (route.is_active) items.push({ icon: "pause", label: "Деактивировать", action: "deactivate" });
  else items.push({ icon: "play", label: "Активировать", action: "activate" });

  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <button className="btn btn-ghost btn-icon" onClick={() => setOpen((v) => !v)} style={{ width: 24, height: 24 }}>
        <Icon name="more-horizontal" size={13} />
      </button>
      {open && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 50 }} onClick={() => setOpen(false)} />
          <div style={{
            position: "absolute", top: "100%", right: 0, marginTop: 4, minWidth: 180, zIndex: 51,
            background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8,
            boxShadow: "var(--shadow-lg)", padding: 4,
          }}>
            {items.map((it, i) => (
              <button key={i}
                onClick={() => {
                  setOpen(false);
                  if (it.action === "edit") { onEdit?.(); return; }
                  apply(route, it.action, { label: it.label });
                }}
                style={{
                  display: "flex", alignItems: "center", gap: 8, width: "100%", padding: "7px 10px",
                  border: 0, background: "transparent", cursor: "pointer", borderRadius: 5,
                  color: it.danger ? "var(--bad)" : "var(--text)", fontSize: 13, textAlign: "left",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface-hover)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                <Icon name={it.icon} size={12} />
                <span>{it.label}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function NodeProbes({ node }) {
  const { data, loading } = useQuery(() => api.get("/probe/reports/recent?limit=80"), { interval: 10000 });
  const rows = (data || []).filter((p) => p.node_id === node.id);
  if (loading && !rows.length) return <div className="muted" style={{ padding: 14 }}>Загрузка…</div>;
  if (!rows.length) return <div className="muted" style={{ padding: 14 }}>Probe-сигналов нет.</div>;
  return (
    <table className="tbl">
      <thead>
        <tr><th>Источник</th><th>Тип</th><th>Status</th><th style={{ textAlign: "right" }}>Latency</th><th>Время</th></tr>
      </thead>
      <tbody>
        {rows.slice(0, 30).map((p) => (
          <tr key={p.id}>
            <td><span className="pill">{p.source}</span></td>
            <td className="small">{p.probe_kind}</td>
            <td>{p.is_reachable ? <span className="pill ok">OK</span> : <span className="pill bad">FAIL</span>}</td>
            <td className="tbl-num mono">{p.latency_ms ?? "—"}</td>
            <td className="small muted">{p.checked_at ? new Date(p.checked_at).toLocaleTimeString() : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function NodeTransport({ node }) {
  const { data, loading } = useQuery(() => api.get("/admin/transport/nodes"), { interval: 15000 });
  const row = (data?.items || []).find((t) => t.node_id === node.id);
  if (loading && !row) return <div className="muted" style={{ padding: 14 }}>Загрузка…</div>;
  if (!row) return <div className="muted" style={{ padding: 14 }}>Агент не зарегистрирован.</div>;
  const tone = { ok: "ok", lag: "warn", silent: "warn", dead: "bad" }[row.health_verdict] || "";
  return (
    <dl className="kv">
      <dt>Вердикт</dt><dd><span className={"pill " + tone}>{row.health_verdict || "—"}</span></dd>
      <dt>Эпоха</dt><dd className="mono">{row.current_epoch}</dd>
      <dt>Heartbeat</dt><dd className="small muted">{relTime(row.last_heartbeat_received_at)} назад</dd>
      <dt>Outbox pending</dt><dd className="mono">{row.outbox_pending || 0}</dd>
      <dt>Outbox failed</dt><dd className="mono">{row.outbox_failed || 0}</dd>
      <dt>Last sync</dt><dd className="small muted">{relTime(row.last_sync_report_received_at)} назад</dd>
    </dl>
  );
}

function NodePool({ node, onOpenNode }) {
  const { data, loading, refetch } = useQuery(
    () => api.get(`/entry/${node.id}/assignments`),
    { interval: 20000, deps: [node.id] },
  );
  const status = useQuery(() => api.get("/admin/status"), { interval: 30000 });
  const nodesById = useMemo(
    () => Object.fromEntries((status.data?.nodes || []).map((n) => [n.id, n])),
    [status.data],
  );
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);

  const items = Array.isArray(data) ? data : (data?.items || []);

  const summary = useMemo(() => {
    const total = items.length;
    const enabled = items.filter((a) => a.enabled).length;
    const totalWeight = items.reduce((s, a) => s + (a.enabled ? Number(a.weight || 0) : 0), 0);
    const ranks = new Set(items.filter((a) => a.enabled).map((a) => Number(a.rank || 0)));
    return { total, enabled, totalWeight, ranks: ranks.size };
  }, [items]);

  const remove = async (backendId) => {
    if (!confirm("Убрать backend из пула этого entry?")) return;
    try { await api.del(`/entry/${node.id}/assignments/${backendId}`); toast.ok("Backend удалён из пула"); refetch(); }
    catch (e) { toast.bad(e.message); }
  };

  const toggleEnabled = async (assignment) => {
    try {
      await api.patch(
        `/entry/${node.id}/assignments/${assignment.backend_node_id}`,
        { enabled: !assignment.enabled },
      );
      toast.ok(assignment.enabled ? "Backend выключен в пуле" : "Backend включён в пул");
      refetch();
    } catch (e) { toast.bad(e.message); }
  };

  const renderSummary = () => (
    <div
      className="card"
      style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, padding: 12, marginBottom: 12 }}
    >
      <PoolStat label="В пуле" value={summary.total} />
      <PoolStat label="Активных" value={summary.enabled} tone={summary.enabled === 0 && summary.total > 0 ? "bad" : "ok"} />
      <PoolStat label="Сумма весов" value={summary.totalWeight || "—"} />
      <PoolStat label="Rank-групп" value={summary.ranks || "—"} />
    </div>
  );

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, gap: 8 }}>
        <div className="muted small">Backends, закреплённые за этой entry (HAProxy pool)</div>
        <button className="btn btn-primary" onClick={() => setAdding(true)}><Icon name="plus" size={12} /> Добавить</button>
      </div>
      {(items.length > 0 || (!loading && summary.total === 0)) && renderSummary()}
      {loading && !items.length && <div className="muted">Загрузка…</div>}
      {!loading && !items.length && (
        <div className="muted" style={{ padding: 14 }}>
          Пул пуст. Добавьте хотя бы один backend, чтобы entry начала проксировать трафик.
        </div>
      )}
      {items.length > 0 && (
        <table className="tbl">
          <thead>
            <tr><th>Backend</th><th style={{ textAlign: "right" }}>Вес</th><th style={{ textAlign: "right" }}>Rank</th><th>Enabled</th><th></th></tr>
          </thead>
          <tbody>
            {items.map((a) => {
              const n = nodesById[a.backend_node_id];
              const openBackend = () => n && onOpenNode && onOpenNode(n);
              return (
                <tr key={a.backend_node_id} style={{ opacity: a.enabled ? 1 : 0.6 }}>
                  <td>
                    {n ? (
                      <span
                        style={{ cursor: onOpenNode ? "pointer" : "default" }}
                        onClick={openBackend}
                        title={onOpenNode ? "Открыть backend-ноду" : ""}
                      >
                        <span style={{ marginRight: 6 }}>{nodeGeo(n.region).flag}</span>
                        <span style={{ fontWeight: 500 }}>{n.name}</span>
                        <div className="mono muted" style={{ fontSize: 11 }}>{n.region}</div>
                      </span>
                    ) : (
                      <span className="mono small">{String(a.backend_node_id).slice(0, 12)}…</span>
                    )}
                  </td>
                  <td className="tbl-num mono">{a.weight}</td>
                  <td className="tbl-num mono">{a.rank}</td>
                  <td>
                    <button
                      className={"pill " + (a.enabled ? "ok" : "")}
                      onClick={() => toggleEnabled(a)}
                      style={{ border: 0, background: "transparent", cursor: "pointer", padding: 0 }}
                      title={a.enabled ? "Выключить в пуле" : "Включить в пул"}
                    >
                      <span className={"pill " + (a.enabled ? "ok" : "")}>{a.enabled ? "enabled" : "off"}</span>
                    </button>
                  </td>
                  <td className="row-actions">
                    <button className="row-btn" onClick={() => setEditing(a)}>Edit</button>
                    <button className="row-btn" onClick={() => remove(a.backend_node_id)}>Remove</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {adding && <AssignmentForm entryId={node.id} existing={items} allNodes={status.data?.nodes || []} onClose={() => { setAdding(false); refetch(); }} />}
      {editing && <AssignmentForm entryId={node.id} assignment={editing} onClose={() => { setEditing(null); refetch(); }} />}
    </>
  );
}

function PoolStat({ label, value, tone }) {
  return (
    <div>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={{ fontSize: 18, color: tone ? `var(--${tone})` : undefined }}>{value}</div>
    </div>
  );
}

function AssignmentForm({ entryId, assignment, existing = [], allNodes = [], onClose }) {
  const isEdit = !!assignment;
  const [backendId, setBackendId] = useState(assignment?.backend_node_id || "");
  const [weight, setWeight] = useState(assignment?.weight ?? 100);
  const [rank, setRank] = useState(assignment?.rank ?? 0);
  const [enabled, setEnabled] = useState(assignment?.enabled ?? true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const existingIds = new Set(existing.map((a) => a.backend_node_id));
  const candidates = allNodes.filter((n) => n.role === "backend" && !existingIds.has(n.id));

  const save = async () => {
    setBusy(true); setErr("");
    try {
      if (isEdit) {
        await api.patch(`/entry/${entryId}/assignments/${assignment.backend_node_id}`, { weight: Number(weight), rank: Number(rank), enabled: !!enabled });
      } else {
        if (!backendId) throw new Error("Выберите backend");
        await api.post(`/entry/${entryId}/assignments`, { backend_node_id: backendId, weight: Number(weight), rank: Number(rank), enabled: !!enabled });
      }
      onClose();
    } catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <Modal
      title={isEdit ? `Backend ${String(assignment.backend_node_id).slice(0, 8)}…` : "Добавить backend в пул"}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose}>Отмена</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>{isEdit ? "Сохранить" : "Добавить"}</button>
        </>
      }
    >
      {err && <div className="form-error">{err}</div>}
      {!isEdit && (
        <Field label="Backend">
          <select value={backendId} onChange={(e) => setBackendId(e.target.value)}>
            <option value="">— выберите —</option>
            {candidates.map((n) => (
              <option key={n.id} value={n.id}>{n.name} · {n.region}</option>
            ))}
          </select>
        </Field>
      )}
      <div className="form-row">
        <Field label="Вес"><input type="number" min={0} max={1000} value={weight} onChange={(e) => setWeight(e.target.value)} /></Field>
        <Field label="Rank"><input type="number" min={0} max={1000} value={rank} onChange={(e) => setRank(e.target.value)} /></Field>
      </div>
      <label className="form-check">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Enabled
      </label>
    </Modal>
  );
}

function toneOf(s) {
  if (s === "healthy") return "ok";
  if (s === "warming_up" || s === "degraded" || s === "suspected") return "warn";
  if (s === "blocked") return "bad";
  return "";
}
