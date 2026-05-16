import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { Spark } from "../components/Spark.jsx";
import { Modal } from "../components/Modal.jsx";
import { Field } from "../components/Field.jsx";
import { toast } from "../components/Toast.jsx";
import { nodeGeo, zoneFlag } from "../lib/geo.js";
import { nodeLoad } from "../lib/nodeLoad.js";

function spark(seed, len = 20, base = 50, vol = 30) {
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

function healthOf(n) {
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

export function NodesPage({ onOpenNode, initialAction, onActionConsumed }) {
  const [filter, setFilter] = useState("");
  const [health, setHealth] = useState("");
  const [role, setRole] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (initialAction === "create") { setCreating(true); onActionConsumed?.(); }
  }, [initialAction, onActionConsumed]);

  const { data: status, loading, error, refetch } = useQuery(() => api.get("/admin/status"), { interval: 15000 });
  const zones = useQuery(() => api.get("/zones"), { interval: 60000 });
  const zoneByCode = useMemo(() => Object.fromEntries((zones.data?.items || []).map((z) => [z.code, z])), [zones.data]);

  // Live entry-node load: count of subscriptions/devices currently routed through each entry.
  const distQ = useQuery(
    () => api.get("/subscriptions/route-assignments/distribution").catch(() => []),
    { interval: 30000 },
  );
  const loadByNode = useMemo(() => {
    const m = {};
    for (const r of (Array.isArray(distQ.data) ? distQ.data : [])) {
      m[r.entry_node_id] = r;
    }
    return m;
  }, [distQ.data]);

  const nodes = status?.nodes || [];
  const list = useMemo(() => {
    return nodes.filter((n) => {
      const h = healthOf(n);
      if (filter) {
        const q = filter.toLowerCase();
        if (!((n.name || "").toLowerCase().includes(q) || String(n.id).toLowerCase().includes(q) || (n.region || "").toLowerCase().includes(q) || (n.public_domain || "").toLowerCase().includes(q))) return false;
      }
      if (health && h !== health) return false;
      if (role && n.role !== role) return false;
      return true;
    });
  }, [nodes, filter, health, role]);

  const totalsLine = useMemo(() => {
    const total = nodes.length;
    const active = nodes.filter((n) => n.is_enabled && !n.is_draining).length;
    const draining = nodes.filter((n) => n.is_draining).length;
    return `${total} нод · ${active} активных${draining ? " · " + draining + " в draining" : ""}`;
  }, [nodes]);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Серверы</h1>
          <div className="page-subtitle">{totalsLine}</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={refetch}><Icon name="refresh" size={13} /> Обновить</button>
          <button className="btn"><Icon name="download" size={13} /> Экспорт</button>
          <button className="btn btn-primary" onClick={() => setCreating(true)}><Icon name="plus" size={13} /> Добавить сервер</button>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="filterbar">
        <div className="input-search-wrap">
          <Icon name="search" size={13} className="input-search-icon" />
          <input className="input" placeholder="Имя, UUID, домен, регион…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
        <select className="select" value={health} onChange={(e) => setHealth(e.target.value)}>
          <option value="">Любое здоровье</option>
          <option value="ok">Healthy</option>
          <option value="warn">Degraded</option>
          <option value="bad">Down</option>
        </select>
        <select className="select" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">Любая роль</option>
          <option value="entry">Entry</option>
          <option value="whitelist_entry">Whitelist entry</option>
          <option value="backend">Backend</option>
        </select>
        <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
          <span className="muted text-xs">{list.length} / {nodes.length}</span>
        </div>
      </div>

      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              <th>Сервер</th>
              <th>Регион</th>
              <th>Роль</th>
              <th>Статус</th>
              <th style={{ width: 180 }}>Нагрузка</th>
              <th style={{ textAlign: "right" }} title="Активных подписчиков (по последним фетчам подписки)">Подписчики</th>
              <th style={{ textAlign: "right" }}>Capacity</th>
              <th style={{ textAlign: "right" }}>Маршруты</th>
              <th>Heartbeat</th>
              <th style={{ width: 120 }}>Трафик 24h</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {list.map((n) => {
              const h = healthOf(n);
              const st = stateOf(n);
              const load = nodeLoad(n);
              const seed = parseInt(String(n.id).replace(/-/g, "").slice(0, 6), 16) || 7;
              const flag = zoneFlag(zoneByCode, n.zone, n.region);
              const geo = nodeGeo(n.region);
              const hb = relTime(n.last_seen_at);
              const hbBad = /s$/.test(hb) && parseInt(hb) > 10;
              return (
                <tr key={n.id} onClick={() => onOpenNode && onOpenNode(n)} style={{ cursor: "pointer" }}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className={`status-dot ${h} ${h === "bad" ? "pulse" : ""}`} />
                      <div>
                        <div style={{ fontWeight: 500 }}>{n.name}</div>
                        <div className="mono muted" style={{ fontSize: 11 }}>{String(n.id).slice(0, 12)}…</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span style={{ marginRight: 6 }}>{flag}</span>
                    <span>{geo.country}</span>
                    <div className="mono muted" style={{ fontSize: 11 }}>{n.region}</div>
                  </td>
                  <td><span className="pill">{n.role}</span></td>
                  <td>
                    <span className={`pill ${st === "active" ? "ok" : st === "draining" ? "warn" : "muted"}`}>{st}</span>
                    {st === "draining" && n.drain_reason && (
                      <div className="muted" style={{ fontSize: 11, marginTop: 2 }} title={n.drain_reason}>
                        {drainReasonLabel(n.drain_reason)}
                      </div>
                    )}
                  </td>
                  <td><LoadBar load={load} /></td>
                  <td className="tbl-num">
                    {(() => {
                      const d = loadByNode[n.id];
                      if (!d) return <span className="muted">—</span>;
                      const subs = d.subscription_count ?? 0;
                      const devs = d.device_count ?? 0;
                      const loadPct = d.load_pct;
                      return (
                        <span title={`${subs} подписок · ${devs} устройств · последний фетч ${relTime(d.most_recent_at)} назад`}>
                          <span style={{ fontWeight: 600 }}>{subs}</span>
                          {devs !== subs && <span className="muted small"> /{devs}</span>}
                          {loadPct != null && (
                            <span
                              className="muted small"
                              style={{ marginLeft: 4, color: loadPct > 85 ? "var(--bad)" : loadPct > 65 ? "var(--warn)" : "var(--text-muted)" }}
                            >
                              {loadPct}%
                            </span>
                          )}
                        </span>
                      );
                    })()}
                  </td>
                  <td className="tbl-num">{n.capacity ?? <span className="muted">—</span>}</td>
                  <td className="tbl-num">{n.placements_backend ?? 0}</td>
                  <td className="mono" style={{ color: hbBad ? "var(--bad)" : "var(--text-secondary)" }}>{hb}</td>
                  <td><Spark data={spark(seed, 20, 50, 30)} color="var(--accent)" w={90} h={22} /></td>
                  <td className="row-actions">
                    <RowMenu node={n} onRefresh={refetch} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {loading && !nodes.length && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {!loading && !list.length && <div className="muted" style={{ padding: 14 }}>Нет нод, подходящих под фильтр.</div>}
      </div>

      {creating && <CreateNodeModal zones={zones.data?.items || []} onClose={() => { setCreating(false); refetch(); }} />}
    </div>
  );
}

function CreateNodeModal({ zones, onClose }) {
  const [f, setF] = useState({
    name: "",
    role: "backend",
    region: "",
    public_domain: "",
    reality_ip: "",
    internal_wg_ip: "",
    capacity: 100,
    zone: "",
  });
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [result, setResult] = useState(null);

  const save = async () => {
    setBusy(true); setErr("");
    try {
      if (!f.name) throw new Error("Имя обязательно");
      if (!f.region) throw new Error("Регион обязателен");
      const payload = {
        name: f.name.trim(),
        role: f.role,
        region: f.region.trim(),
        public_domain: f.public_domain.trim() || "",
        internal_wg_ip: f.internal_wg_ip.trim() || "",
        capacity: Number(f.capacity) || 100,
      };
      if (f.reality_ip.trim()) payload.reality_ip = f.reality_ip.trim();
      if (f.zone) payload.zone = f.zone;
      const r = await api.post("/admin/nodes", payload);
      setResult(r);
      toast.ok("Нода создана");
    } catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  const copy = (text) => { navigator.clipboard.writeText(text).then(() => toast.ok("Скопировано")); };

  if (result) {
    return (
      <Modal
        title="Нода создана"
        onClose={onClose}
        footer={<button className="btn btn-primary" onClick={onClose}>Готово</button>}
      >
        <div className="muted small" style={{ marginBottom: 12 }}>
          Скопируйте команду установки на сервер — токен одноразовый и истекает {new Date(result.bootstrap_token_expires_at).toLocaleString()}.
        </div>
        <Field label="Bootstrap token">
          <div style={{ display: "flex", gap: 6 }}>
            <input type="text" readOnly value={result.bootstrap_token} style={{ fontFamily: "var(--font-mono)", fontSize: 11 }} />
            <button className="btn" onClick={() => copy(result.bootstrap_token)}>Copy</button>
          </div>
        </Field>
        <Field label="Install command">
          <div style={{ display: "flex", gap: 6, alignItems: "start" }}>
            <textarea readOnly value={result.install_command} rows={3} style={{ fontFamily: "var(--font-mono)", fontSize: 11, width: "100%", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, padding: 7 }} />
            <button className="btn" onClick={() => copy(result.install_command)}>Copy</button>
          </div>
        </Field>
      </Modal>
    );
  }

  return (
    <Modal
      title="Новый сервер"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose}>Отмена</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>Создать</button>
        </>
      }
    >
      {err && <div className="form-error">{err}</div>}
      <Field label="Имя"><input type="text" value={f.name} onChange={set("name")} placeholder="fra-backend-01" /></Field>
      <div className="form-row">
        <Field label="Роль">
          <select value={f.role} onChange={set("role")}>
            <option value="backend">backend</option>
            <option value="entry">entry</option>
            <option value="whitelist_entry">whitelist_entry</option>
          </select>
        </Field>
        <Field label="Регион" hint="fra, ams, nyc…">
          <input type="text" value={f.region} onChange={set("region")} placeholder="fra" />
        </Field>
      </div>
      <Field label="Public domain" hint="опционально">
        <input type="text" value={f.public_domain} onChange={set("public_domain")} placeholder="fra-01.example.com" />
      </Field>
      <div className="form-row">
        <Field label="Reality IP" hint="опционально">
          <input type="text" value={f.reality_ip} onChange={set("reality_ip")} />
        </Field>
        <Field label="Internal WG IP" hint="опционально">
          <input type="text" value={f.internal_wg_ip} onChange={set("internal_wg_ip")} />
        </Field>
      </div>
      <div className="form-row">
        <Field label="Capacity">
          <input type="number" min={1} max={10000} value={f.capacity} onChange={set("capacity")} />
        </Field>
        <Field label="Зона">
          <select value={f.zone} onChange={set("zone")}>
            <option value="">—</option>
            {zones.filter((z) => z.is_active).map((z) => (
              <option key={z.code} value={z.code}>{z.emoji ? `${z.emoji} ` : ""}{z.name}</option>
            ))}
          </select>
        </Field>
      </div>
    </Modal>
  );
}

function LoadBar({ load }) {
  const { pct, tone, label, tooltip } = load;
  const barWidth = pct == null ? 0 : Math.min(100, pct);
  return (
    <div title={tooltip} style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: "var(--surface-2)", borderRadius: 4, overflow: "hidden", maxWidth: 140 }}>
        <div style={{ width: `${barWidth}%`, height: "100%", background: `var(--${tone})` }} />
      </div>
      <span className="mono" style={{ color: `var(--${tone})`, fontWeight: 500, whiteSpace: "nowrap" }}>
        {label}{pct != null ? ` · ${pct}%` : ""}
      </span>
    </div>
  );
}

function RowMenu({ node, onRefresh }) {
  const [open, setOpen] = useState(false);
  const btnRef = useRef(null);
  const menuRef = useRef(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  const computePos = () => {
    const btn = btnRef.current;
    if (!btn) return;
    const rect = btn.getBoundingClientRect();
    const margin = 8;
    const menuW = (menuRef.current && menuRef.current.offsetWidth) || 200;
    const menuH = (menuRef.current && menuRef.current.offsetHeight) || 180;
    const roomBelow = window.innerHeight - rect.bottom - margin;
    const roomAbove = rect.top - margin;
    const wantBelow = roomBelow >= menuH || roomBelow >= roomAbove;
    let top = wantBelow ? rect.bottom + 4 : rect.top - menuH - 4;
    if (top + menuH + margin > window.innerHeight) {
      top = Math.max(margin, window.innerHeight - menuH - margin);
    }
    if (top < margin) top = margin;
    // anchor to button's right edge
    let left = rect.right - menuW;
    const maxLeft = window.innerWidth - menuW - margin;
    if (left > maxLeft) left = maxLeft;
    if (left < margin) left = margin;
    setPos({ top, left });
  };

  useLayoutEffect(() => {
    if (!open) return;
    computePos();
    const onScroll = () => computePos();
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [open]);

  const wrap = async (label, fn) => {
    setOpen(false);
    try { await fn(); toast.ok(label); onRefresh?.(); }
    catch (e) { toast.bad(e.message || "Ошибка"); }
  };

  const drain = () => wrap(
    node.is_draining ? "Drain снят" : "Drain включён",
    () => node.is_draining
      ? api.post(`/agent/nodes/${node.id}/enable`)
      : api.post(`/agent/nodes/${node.id}/drain`),
  );
  const toggleEnabled = () => {
    if (node.is_enabled && !confirm(`Отключить ноду ${node.name}? Ключи перестанут на неё назначаться.`)) return;
    return wrap(
      node.is_enabled ? "Нода отключена" : "Нода включена",
      () => api.patch(`/agent/nodes/${node.id}`, { is_enabled: !node.is_enabled }),
    );
  };
  const forceSnapshot = () => wrap(
    "Snapshot запрошен",
    () => api.post(`/admin/transport/nodes/${node.id}/request-snapshot`),
  );
  const copyId = () => {
    navigator.clipboard.writeText(node.id).then(() => toast.ok("UUID скопирован"));
    setOpen(false);
  };

  const items = [
    {
      icon: "pause",
      label: node.is_draining ? "Снять drain" : "Drain",
      run: drain,
    },
    {
      icon: "refresh",
      label: "Force snapshot",
      run: forceSnapshot,
    },
    {
      icon: "command",
      label: "Скопировать UUID",
      run: copyId,
    },
    {
      icon: "power",
      label: node.is_enabled ? "Отключить ноду" : "Включить ноду",
      run: toggleEnabled,
      danger: node.is_enabled,
    },
  ];

  return (
    <div style={{ display: "inline-block" }} onClick={(e) => e.stopPropagation()}>
      <button ref={btnRef} className="btn btn-ghost btn-icon" onClick={() => setOpen((v) => !v)} style={{ width: 24, height: 24 }}>
        <Icon name="more-horizontal" size={13} />
      </button>
      {open && createPortal(
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 200 }} onClick={() => setOpen(false)} />
          <div
            ref={menuRef}
            style={{
              position: "fixed", top: pos.top, left: pos.left,
              minWidth: 200, zIndex: 201,
              background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8,
              boxShadow: "var(--shadow-lg)", padding: 4,
            }}
          >
            {items.map((it, i) => (
              <button key={i} onClick={it.run}
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
        </>,
        document.body,
      )}
    </div>
  );
}
