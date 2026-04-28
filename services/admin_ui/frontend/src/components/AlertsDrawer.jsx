import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Drawer } from "./Drawer.jsx";
import { Icon } from "./Icon.jsx";
import { toast } from "./Toast.jsx";

const LEVEL_TONE = { critical: "bad", warning: "warn", info: "ok" };
const LEVEL_LABEL = { critical: "критично", warning: "внимание", info: "info" };
const SOURCE_LABEL = {
  probe: "проба",
  transport: "транспорт",
  billing: "биллинг",
  deploy: "деплой",
  nats: "NATS",
  scheduler: "расписание",
  security: "безопасность",
  generic: "система",
};

function fmtAgo(ts) {
  if (!ts) return "—";
  const t = new Date(ts).getTime();
  if (Number.isNaN(t)) return "—";
  const sec = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (sec < 60) return `${sec}s назад`;
  if (sec < 3600) return `${Math.round(sec / 60)}m назад`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h назад`;
  return `${Math.round(sec / 86400)}d назад`;
}

export function AlertsDrawer({ onClose, onChanged }) {
  const [levelFilter, setLevelFilter] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);

  const qs = new URLSearchParams({ limit: "50", active_only: "true" });
  if (levelFilter) qs.set("level", levelFilter);
  if (unreadOnly) qs.set("unread_only", "true");

  const { data, loading, error, refetch } = useQuery(
    () => api.get(`/admin/alerts?${qs.toString()}`),
    { interval: 15000, deps: [levelFilter, unreadOnly] },
  );
  const items = data?.items || [];

  const fireChange = () => { refetch(); onChanged?.(); };

  const markRead = async (id) => {
    try { await api.post(`/admin/alerts/${id}/read`); fireChange(); }
    catch (e) { toast.bad(e.message || "Ошибка"); }
  };
  const dismiss = async (id) => {
    try { await api.post(`/admin/alerts/${id}/dismiss`); fireChange(); }
    catch (e) { toast.bad(e.message || "Ошибка"); }
  };
  const markAll = async () => {
    try {
      const r = await api.post("/admin/alerts/mark-all-read");
      toast.ok(`Прочитано: ${r.marked}`);
      fireChange();
    } catch (e) { toast.bad(e.message || "Ошибка"); }
  };

  const head = (
    <div className="slideover-title-main">
      <div className="slideover-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Icon name="bell" size={16} />
        <span>Уведомления</span>
        {data?.unread > 0 && <span className="pill bad">{data.unread} непрочитано</span>}
      </div>
      <div className="slideover-sub">Системные события: ноды, NATS, биллинг, деплой</div>
    </div>
  );

  const actions = (
    <button className="btn btn-ghost" onClick={markAll} disabled={!data?.unread}>
      <Icon name="check" size={13} /> Прочитать всё
    </button>
  );

  return (
    <Drawer head={head} onClose={onClose} actions={actions}>
      <div className="filterbar" style={{ paddingBottom: 12 }}>
        <select className="select" value={levelFilter} onChange={(e) => setLevelFilter(e.target.value)}>
          <option value="">Любой уровень</option>
          <option value="critical">🔴 critical</option>
          <option value="warning">🟡 warning</option>
          <option value="info">🟢 info</option>
        </select>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "var(--text-secondary)", cursor: "pointer" }}>
          <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />
          Только непрочитанные
        </label>
        <div style={{ marginLeft: "auto" }}>
          <span className="muted text-xs">{items.length} / {data?.total ?? 0}</span>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      {loading && !items.length && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
      {!loading && !items.length && (
        <div className="muted" style={{ padding: 24, textAlign: "center" }}>
          <Icon name="check" size={20} />
          <div style={{ marginTop: 8 }}>Уведомлений нет</div>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {items.map((a) => (
          <AlertRow
            key={a.id}
            alert={a}
            onRead={() => markRead(a.id)}
            onDismiss={() => dismiss(a.id)}
          />
        ))}
      </div>
    </Drawer>
  );
}

function AlertRow({ alert, onRead, onDismiss }) {
  const tone = LEVEL_TONE[alert.level] || "muted";
  const isUnread = !alert.read_at;
  const isResolved = !!alert.resolved_at;
  const sourceLabel = SOURCE_LABEL[alert.source] || alert.source;

  return (
    <div
      className="card"
      style={{
        padding: "10px 12px",
        borderLeft: `3px solid var(--${tone})`,
        opacity: isResolved ? 0.6 : 1,
        background: isUnread ? "var(--surface)" : "var(--surface-2)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 10 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
            <span className={`pill ${tone}`}>{LEVEL_LABEL[alert.level] || alert.level}</span>
            <span className="muted text-xs">{sourceLabel}</span>
            {alert.occurrences > 1 && (
              <span className="pill" title="Сколько раз повторялось">×{alert.occurrences}</span>
            )}
            {isResolved && <span className="pill ok">resolved</span>}
            {isUnread && !isResolved && <span className="status-dot bad" style={{ width: 6, height: 6 }} />}
          </div>
          <div style={{ fontWeight: 500, marginBottom: 2 }}>{alert.title}</div>
          <div className="small muted" style={{ whiteSpace: "pre-wrap", maxHeight: 120, overflow: "auto" }}>
            {alert.body}
          </div>
          <div className="small muted" style={{ marginTop: 6 }}>
            {fmtAgo(alert.last_seen_at)}
            {alert.entity_id && <> · <span className="mono">{String(alert.entity_id).slice(0, 12)}</span></>}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {isUnread && (
            <button className="btn btn-ghost btn-icon" onClick={onRead} title="Отметить прочитанным">
              <Icon name="check" size={13} />
            </button>
          )}
          <button className="btn btn-ghost btn-icon" onClick={onDismiss} title="Скрыть">
            <Icon name="x" size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}
