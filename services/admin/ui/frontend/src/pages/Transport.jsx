import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { toast } from "../components/Toast.jsx";
import { nodeGeo } from "../lib/geo.js";

const VERDICT_TONE = { ok: "ok", lag: "warn", silent: "warn", dead: "bad" };
const VERDICT_LABEL = { ok: "в строю", lag: "отстаёт", silent: "молчит", dead: "мёртв" };

const OUTBOX_TONE = { pending: "warn", failed: "bad", publishing: "info", published: "ok" };
const OUTBOX_LABEL = { pending: "в пути", publishing: "публикуется", published: "доставлено", failed: "ошибка" };

function fmtAgo(t) {
  if (!t) return "—";
  const delta = (Date.now() - new Date(t).getTime()) / 1000;
  if (delta < 60) return `${Math.round(delta)}s`;
  if (delta < 3600) return `${Math.round(delta / 60)}m`;
  if (delta < 86400) return `${Math.round(delta / 3600)}h`;
  return `${Math.round(delta / 86400)}d`;
}

function heartbeatTone(t) {
  if (!t) return "bad";
  const sec = (Date.now() - new Date(t).getTime()) / 1000;
  if (sec < 15) return "ok";
  if (sec < 60) return "warn";
  return "bad";
}

export function TransportPage() {
  const [tab, setTab] = useState("nodes");
  const [selectedNode, setSelectedNode] = useState(null);

  const overview = useQuery(() => api.get("/admin/transport/overview"), { interval: 15000 });
  const nodes = useQuery(() => api.get("/admin/transport/nodes"), { interval: 15000 });

  const statusData = useQuery(() => api.get("/admin/status"), { interval: 30000 });
  const nodesById = useMemo(
    () => Object.fromEntries((statusData.data?.nodes || []).map((n) => [n.id, n])),
    [statusData.data],
  );

  const items = nodes.data?.items || [];

  const cleanup = async () => {
    if (!confirm("Удалить старые события и опубликованные outbox-записи?")) return;
    try {
      const r = await api.post("/admin/transport/cleanup");
      toast.ok(`Удалено: events ${r.deleted_events}, outbox ${r.deleted_outbox}`);
    } catch (e) { toast.bad(e.message || "Ошибка"); }
  };

  const retryAll = async (nodeId) => {
    try {
      const qs = nodeId ? `?node_id=${nodeId}` : "";
      const r = await api.post(`/admin/transport/outbox/retry-all-failed${qs}`);
      toast.ok(`Поставлено на повтор: ${r.retried_count}`);
      nodes.refetch();
    } catch (e) { toast.bad(e.message || "Ошибка"); }
  };

  const forceSnapshot = async (nodeId) => {
    try {
      const r = await api.post(`/admin/transport/nodes/${nodeId}/request-snapshot`);
      toast.ok(`Snapshot запрошен · gen ${r.epoch}`);
      nodes.refetch();
    } catch (e) { toast.bad(e.message || "Ошибка"); }
  };

  const ov = overview.data;

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Очередь</h1>
          <div className="page-subtitle">
            NATS-транспорт: состояние агентов, outbox, поток событий
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={() => { overview.refetch(); nodes.refetch(); }}>
            <Icon name="refresh" size={13} /> Обновить
          </button>
          <button className="btn" onClick={() => retryAll(null)}>
            <Icon name="refresh" size={13} /> Повторить с ошибкой
          </button>
          <button className="btn" onClick={cleanup}>
            <Icon name="x" size={13} /> Удалить старые</button>
        </div>
      </div>

      <div className="sec">
        <div className="kpi-hero">
          <div className="kpi-cell primary">
            <div className="kpi-label">
              <Icon name="activity" size={12} />
              <span>NATS</span>
            </div>
            <div className="kpi-value-row">
              <div className="kpi-value">
                {ov?.nats_connected ? "connected" : "—"}
              </div>
              <span className={`status-dot ${ov?.nats_connected ? "ok pulse" : "bad"}`} style={{ width: 10, height: 10 }} />
            </div>
            <div className="kpi-delta flat">
              {ov?.uptime_s != null ? `uptime ${fmtAgo(Date.now() - ov.uptime_s * 1000)}` : ""}
              {ov?.consumer_tasks?.length ? ` · ${ov.consumer_tasks.filter((t) => t.running).length}/${ov.consumer_tasks.length} consumers` : ""}
            </div>
          </div>
          <KpiCell
            icon="server"
            label="Агентов"
            value={items.length}
            delta={`${items.filter((t) => t.health_verdict === "ok").length} в строю`}
            tone="up"
          />
          <KpiCell
            icon="clock"
            label="Команд в пути"
            value={ov?.outbox?.pending ?? 0}
            delta={ov?.outbox?.failed ? `${ov.outbox.failed} с ошибкой` : "без ошибок"}
            tone={ov?.outbox?.failed ? "down" : "up"}
          />
          <KpiCell
            icon="arrow-up-right"
            label="Доставлено за 24ч"
            value={ov?.outbox?.published_24h ?? 0}
            delta={`публикуется ${ov?.outbox?.publishing ?? 0}`}
            tone="flat"
          />
          <KpiCell
            icon="arrow-down-right"
            label="Отчётов за 24ч"
            value={ov?.events?.total_24h ?? 0}
            delta={ov?.events?.by_type ? `типов: ${Object.keys(ov.events.by_type).length}` : ""}
            tone="flat"
          />
        </div>
      </div>

      <div className="sec">
        <div className="seg" style={{ display: "inline-flex" }}>
          <button data-active={tab === "nodes"} onClick={() => setTab("nodes")}>
            <Icon name="server" size={12} /> Агенты
          </button>
          <button data-active={tab === "outbox"} onClick={() => setTab("outbox")}>
            <Icon name="arrow-up-right" size={12} /> Команды агентам
          </button>
          <button data-active={tab === "events"} onClick={() => setTab("events")}>
            <Icon name="arrow-down-right" size={12} /> Отчёты от агентов
          </button>
        </div>
      </div>

      {tab === "nodes" && (
        <NodesTab
          items={items}
          nodesById={nodesById}
          loading={nodes.loading}
          onSelect={setSelectedNode}
          onRetryAll={retryAll}
          onForceSnapshot={forceSnapshot}
        />
      )}
      {tab === "outbox" && <OutboxTab nodesById={nodesById} />}
      {tab === "events" && <EventsTab nodesById={nodesById} />}

      {selectedNode && (
        <NodeDetailDrawer
          nodeId={selectedNode}
          nodesById={nodesById}
          onClose={() => setSelectedNode(null)}
          onForceSnapshot={forceSnapshot}
        />
      )}
    </div>
  );
}

function KpiCell({ icon, label, value, unit, delta, tone }) {
  return (
    <div className="kpi-cell">
      <div className="kpi-label"><Icon name={icon} size={12} /> <span>{label}</span></div>
      <div className="kpi-value-row">
        <div className="kpi-value tnum">{value}{unit && <span className="kpi-unit">{unit}</span>}</div>
      </div>
      {delta && <div className={`kpi-delta ${tone || "flat"}`}>{delta}</div>}
    </div>
  );
}

function NodesTab({ items, nodesById, loading, onSelect, onRetryAll, onForceSnapshot }) {
  return (
    <div className="card" style={{ overflowX: "auto" }}>
      <table className="tbl">
        <thead>
          <tr>
            <th>Агент</th>
            <th>Статус</th>
            <th style={{ textAlign: "right" }} title="Сколько раз агент делал полную пересинхронизацию (snapshot). Увеличивается при restart агента или форс-snapshot'е.">Ресинков</th>
            <th style={{ width: 180 }}>Heartbeat</th>
            <th style={{ width: 140, textAlign: "right" }}>Outbox</th>
            <th>Последний sync</th>
            <th style={{ width: 100 }}></th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => {
            const n = nodesById[t.node_id];
            const verdict = t.health_verdict || "dead";
            const tone = VERDICT_TONE[verdict] || "muted";
            const hbTone = heartbeatTone(t.last_heartbeat_received_at);
            const geo = n ? nodeGeo(n.region) : null;
            return (
              <tr key={t.node_id} style={{ cursor: "pointer" }} onClick={() => onSelect(t.node_id)}>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className={`status-dot ${tone}`} />
                    <div>
                      <div style={{ fontWeight: 500 }}>
                        {geo && <span style={{ marginRight: 6 }}>{geo.flag}</span>}
                        {t.name || n?.name || String(t.node_id).slice(0, 12)}
                      </div>
                      <div className="mono muted" style={{ fontSize: 11 }}>{t.region || n?.region || ""}</div>
                    </div>
                  </div>
                </td>
                <td>
                  <span className={`pill ${tone}`}>
                    <span className={`status-dot ${tone}`} />
                    {VERDICT_LABEL[verdict] || verdict}
                  </span>
                </td>
                <td className="tbl-num mono" title="Количество полных пересинхронизаций с момента регистрации агента">
                  {t.current_epoch || 0}
                </td>
                <td>
                  <HbBar tone={hbTone} ts={t.last_heartbeat_received_at} />
                </td>
                <td className="tbl-num mono">
                  {t.outbox_pending || 0}
                  {t.outbox_failed ? (
                    <span className="pill bad" style={{ marginLeft: 6 }}>err {t.outbox_failed}</span>
                  ) : null}
                </td>
                <td className="small muted">{fmtAgo(t.last_sync_report_received_at)} назад</td>
                <td className="row-actions" onClick={(e) => e.stopPropagation()}>
                  <RowActions
                    items={[
                      { icon: "refresh", label: "Force snapshot", action: () => onForceSnapshot(t.node_id) },
                      t.outbox_failed ? { icon: "refresh", label: "Retry failed outbox", action: () => onRetryAll(t.node_id) } : null,
                    ].filter(Boolean)}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {loading && !items.length && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
      {!loading && !items.length && <div className="muted" style={{ padding: 14 }}>Агентов нет.</div>}
    </div>
  );
}

function HbBar({ tone, ts }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{
        width: 8, height: 8, borderRadius: "50%", background: `var(--${tone})`,
        animation: tone === "ok" ? "pulse 1.5s ease-in-out infinite" : undefined,
      }} />
      <span className="mono small" style={{ color: `var(--${tone})` }}>{fmtAgo(ts)}</span>
    </div>
  );
}

function RowActions({ items }) {
  const [open, setOpen] = useState(false);
  if (!items.length) return null;
  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <button className="btn btn-ghost btn-icon" onClick={() => setOpen((v) => !v)} style={{ width: 24, height: 24 }}>
        <Icon name="more-horizontal" size={13} />
      </button>
      {open && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 50 }} onClick={() => setOpen(false)} />
          <div style={{
            position: "absolute", top: "100%", right: 0, marginTop: 4, minWidth: 200, zIndex: 51,
            background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8,
            boxShadow: "var(--shadow-lg)", padding: 4,
          }}>
            {items.map((it, i) => (
              <button key={i} onClick={() => { setOpen(false); it.action(); }}
                style={{
                  display: "flex", alignItems: "center", gap: 8, width: "100%", padding: "7px 10px",
                  border: 0, background: "transparent", cursor: "pointer", borderRadius: 5,
                  color: "var(--text)", fontSize: 13, textAlign: "left",
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

function OutboxTab({ nodesById }) {
  const [statusFilter, setStatusFilter] = useState("");
  const [nodeFilter, setNodeFilter] = useState("");
  const qs = new URLSearchParams({ limit: "50" });
  if (statusFilter) qs.set("status", statusFilter);
  if (nodeFilter) qs.set("node_id", nodeFilter);

  const q = useQuery(
    () => api.get(`/admin/transport/outbox?${qs.toString()}`),
    { interval: 15000, deps: [statusFilter, nodeFilter] },
  );
  const breakdownQs = new URLSearchParams();
  if (nodeFilter) breakdownQs.set("node_id", nodeFilter);
  if (statusFilter) breakdownQs.set("status", statusFilter);
  const breakdown = useQuery(
    () => api.get(`/admin/transport/outbox/breakdown?${breakdownQs.toString()}`),
    { interval: 20000, deps: [statusFilter, nodeFilter] },
  );
  const rows = q.data?.items || [];
  const breakdownItems = breakdown.data?.items || [];

  const retry = async (id) => {
    try { await api.post(`/admin/transport/outbox/${id}/retry`); toast.ok("Поставлено на повтор"); q.refetch(); breakdown.refetch(); }
    catch (e) { toast.bad(e.message); }
  };

  const cancel = async (id) => {
    if (!confirm("Отменить и удалить эту команду из очереди?")) return;
    try { await api.post(`/admin/transport/outbox/${id}/cancel`); toast.ok("Команда отменена"); q.refetch(); breakdown.refetch(); }
    catch (e) { toast.bad(e.message); }
  };

  return (
    <>
      {breakdownItems.length > 0 && (
        <div className="card" style={{ marginBottom: 16, padding: 14 }}>
          <div className="kpi-label" style={{ marginBottom: 8 }}>
            <Icon name="bar-chart" size={12} /> Распределение команд
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {breakdownItems.slice(0, 20).map((it, i) => (
              <span
                key={i}
                className={`pill ${OUTBOX_TONE[it.status] || ""}`}
                title={`${it.count} × ${it.event_type} (${OUTBOX_LABEL[it.status] || it.status})`}
                style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}
                onClick={() => setStatusFilter(it.status)}
              >
                <strong>{it.count}</strong>
                <span>{it.event_type}</span>
                <span className="muted" style={{ fontSize: 10 }}>{OUTBOX_LABEL[it.status] || it.status}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="filterbar">
        <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Любой статус</option>
          <option value="pending">в пути</option>
          <option value="publishing">публикуется</option>
          <option value="published">доставлено</option>
          <option value="failed">ошибка</option>
        </select>
        <select className="select" value={nodeFilter} onChange={(e) => setNodeFilter(e.target.value)}>
          <option value="">Все ноды</option>
          {Object.values(nodesById).map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}
        </select>
        <div style={{ marginLeft: "auto" }}>
          <span className="muted text-xs">{rows.length} / {q.data?.total ?? 0}</span>
        </div>
      </div>

      <div className="card" style={{ overflowX: "auto" }}>
        <table className="tbl">
          <thead>
            <tr>
              <th>Команда</th>
              <th>Нода</th>
              <th>Статус</th>
              <th style={{ textAlign: "right" }}>Попытки</th>
              <th>Создано</th>
              <th>Следующая попытка</th>
              <th>Ошибка</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const n = nodesById[r.node_id];
              return (
                <tr key={r.id}>
                  <td>
                    <div style={{ fontWeight: 500 }}>{r.event_type}</div>
                    <div className="mono muted" style={{ fontSize: 11 }}>{r.message_id}</div>
                  </td>
                  <td>{n?.name || <span className="mono small">{String(r.node_id).slice(0, 12)}…</span>}</td>
                  <td><span className={`pill ${OUTBOX_TONE[r.status] || ""}`}>{OUTBOX_LABEL[r.status] || r.status}</span></td>
                  <td className="tbl-num mono">{r.attempts}</td>
                  <td className="small muted">{fmtAgo(r.created_at)} назад</td>
                  <td className="small muted">{r.next_retry_at ? `через ${fmtAgo(r.next_retry_at)}` : "—"}</td>
                  <td className="small muted" style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.last_error || ""}>{r.last_error || "—"}</td>
                  <td className="row-actions">
                    {r.status === "failed" && (
                      <button className="row-btn" onClick={() => retry(r.id)}>Повторить</button>
                    )}
                    {(r.status === "pending" || r.status === "failed") && (
                      <button className="row-btn" onClick={() => cancel(r.id)}>Отменить</button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {q.loading && !rows.length && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {!q.loading && !rows.length && <div className="muted" style={{ padding: 14 }}>Команд нет.</div>}
      </div>
    </>
  );
}

function EventsTab({ nodesById }) {
  const [typeFilter, setTypeFilter] = useState("");
  const [nodeFilter, setNodeFilter] = useState("");
  const qs = new URLSearchParams({ limit: "60" });
  if (typeFilter) qs.set("event_type", typeFilter);
  if (nodeFilter) qs.set("node_id", nodeFilter);

  const q = useQuery(
    () => api.get(`/admin/transport/events?${qs.toString()}`),
    { interval: 15000, deps: [typeFilter, nodeFilter] },
  );
  const rows = q.data?.items || [];
  const types = useMemo(() => Array.from(new Set(rows.map((r) => r.event_type))).sort(), [rows]);

  return (
    <>
      <div className="filterbar">
        <select className="select" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="">Любой тип</option>
          {types.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select className="select" value={nodeFilter} onChange={(e) => setNodeFilter(e.target.value)}>
          <option value="">Все ноды</option>
          {Object.values(nodesById).map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}
        </select>
        <div style={{ marginLeft: "auto" }}>
          <span className="muted text-xs">{rows.length} / {q.data?.total ?? 0}</span>
        </div>
      </div>

      <div className="card" style={{ overflowX: "auto" }}>
        <table className="tbl">
          <thead>
            <tr>
              <th>Тип</th>
              <th>Нода</th>
              <th>Event ID</th>
              <th>Subject</th>
              <th>Время</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const n = nodesById[r.node_id];
              return (
                <tr key={r.id}>
                  <td><span className="pill accent">{r.event_type}</span></td>
                  <td>{n?.name || <span className="mono small">{String(r.node_id).slice(0, 12)}…</span>}</td>
                  <td className="mono small">{r.event_id}</td>
                  <td className="mono small muted">{r.subject || "—"}</td>
                  <td className="small muted">{fmtAgo(r.processed_at)} назад</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {q.loading && !rows.length && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {!q.loading && !rows.length && <div className="muted" style={{ padding: 14 }}>Отчётов нет.</div>}
      </div>
    </>
  );
}

function NodeDetailDrawer({ nodeId, nodesById, onClose, onForceSnapshot }) {
  const q = useQuery(
    () => api.get(`/admin/transport/nodes/${nodeId}`),
    { interval: 15000, deps: [nodeId] },
  );
  const data = q.data;
  const node = nodesById[nodeId];

  return (
    <div className="slideover-backdrop" onClick={onClose}>
      <aside className="slideover" onClick={(e) => e.stopPropagation()}>
        <div className="slideover-head">
          <span className={`status-dot ${VERDICT_TONE[data?.health_verdict] || "muted"}`} style={{ marginTop: 6 }} />
          <div className="slideover-title-main">
            <div className="slideover-title">{data?.name || node?.name || String(nodeId).slice(0, 12)}</div>
            <div className="slideover-sub">
              {data?.region || node?.region} · ресинков {data?.current_epoch ?? 0} · {VERDICT_LABEL[data?.health_verdict] || "—"}
            </div>
          </div>
          <button className="btn btn-ghost btn-icon" onClick={() => onForceSnapshot(nodeId)} title="Force snapshot">
            <Icon name="refresh" size={14} />
          </button>
          <button className="btn btn-ghost btn-icon" onClick={onClose} title="Закрыть">
            <Icon name="x" size={15} />
          </button>
        </div>

        <div className="slideover-body">
          <div className="sec-head"><div className="sec-title">Состояние</div></div>
          <dl className="kv" style={{ marginBottom: 20 }}>
            <dt>Вердикт</dt>
            <dd><span className={`pill ${VERDICT_TONE[data?.health_verdict] || ""}`}>{VERDICT_LABEL[data?.health_verdict] || "—"}</span></dd>
            <dt title="Количество полных пересинхронизаций с момента регистрации агента">Ресинков</dt>
            <dd className="mono">{data?.current_epoch ?? 0}</dd>
            <dt>Последний snapshot</dt>
            <dd className="small">
              {data?.last_snapshot_id ? (
                <>
                  <div className="mono">{data.last_snapshot_id}</div>
                  <div className="muted">{data.last_snapshot_reason} · {fmtAgo(data.last_snapshot_generated_at)} назад</div>
                </>
              ) : "—"}
            </dd>
            <dt>Последний heartbeat</dt><dd className="small muted">{fmtAgo(data?.last_heartbeat_received_at)} назад</dd>
            <dt>Последний отчёт</dt><dd className="small muted">{fmtAgo(data?.last_sync_report_received_at)} назад</dd>
            <dt>Последняя команда</dt><dd className="small muted">{fmtAgo(data?.last_command_published_at)} назад</dd>
            <dt>Задержка связи</dt><dd className="mono">{data?.communication_lag_s != null ? `${data.communication_lag_s.toFixed(1)}s` : "—"}</dd>
          </dl>

          <div className="sec-head">
            <div className="sec-title">Команды агенту</div>
            <div className="sec-sub">в пути {data?.outbox_pending || 0} · с ошибкой {data?.outbox_failed || 0}</div>
          </div>
          {data?.outbox_items?.length ? (
            <table className="tbl" style={{ marginBottom: 20 }}>
              <thead><tr><th>Команда</th><th>Статус</th><th style={{ textAlign: "right" }}>Попытки</th><th>Создано</th></tr></thead>
              <tbody>
                {data.outbox_items.map((it) => (
                  <tr key={it.id}>
                    <td className="small">{it.event_type}<div className="mono muted" style={{ fontSize: 10 }}>{it.message_id}</div></td>
                    <td><span className={`pill ${OUTBOX_TONE[it.status] || ""}`}>{OUTBOX_LABEL[it.status] || it.status}</span></td>
                    <td className="tbl-num mono">{it.attempts}</td>
                    <td className="small muted">{fmtAgo(it.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="muted small" style={{ marginBottom: 20 }}>Очередь команд пуста.</div>}

          <div className="sec-head">
            <div className="sec-title">Последние отчёты от агента</div>
          </div>
          {data?.recent_events?.length ? (
            <table className="tbl">
              <thead><tr><th>Тип</th><th>Event ID</th><th>Время</th></tr></thead>
              <tbody>
                {data.recent_events.map((e) => (
                  <tr key={e.id}>
                    <td><span className="pill accent">{e.event_type}</span></td>
                    <td className="mono small">{e.event_id}</td>
                    <td className="small muted">{fmtAgo(e.processed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="muted small">Отчётов нет.</div>}
        </div>
      </aside>
    </div>
  );
}
