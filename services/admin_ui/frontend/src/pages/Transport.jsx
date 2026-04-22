import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";

const VERDICT_TONE = { ok: "ok", lag: "warn", silent: "warn", dead: "bad" };

export function TransportPage() {
  const nodes = useQuery(() => api.get("/admin/transport/nodes"), { interval: 15000 });
  const items = nodes.data?.items || [];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Очередь</h1>
          <div className="page-subtitle">Heartbeat, outbox и состояние агентов в NATS</div>
        </div>
      </div>

      {nodes.error && <div className="card card-bad">Ошибка: {nodes.error.message}</div>}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Нода</th>
              <th>Вердикт</th>
              <th>Эпоха</th>
              <th>Heartbeat</th>
              <th>Outbox</th>
              <th>Последний sync</th>
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.node_id}>
                <td className="mono small">{String(t.node_id).slice(0, 12)}…</td>
                <td><span className={"chip chip-" + (VERDICT_TONE[t.health_verdict] || "muted")}>{t.health_verdict || "—"}</span></td>
                <td className="mono">{t.current_epoch}</td>
                <td className="small muted">{fmtAgo(t.last_heartbeat_received_at)}</td>
                <td className="mono">{t.outbox_pending || 0}{t.outbox_failed ? <span className="chip chip-bad" style={{ marginLeft: 6 }}>err {t.outbox_failed}</span> : null}</td>
                <td className="small muted">{fmtAgo(t.last_sync_report_received_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(nodes.loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!nodes.loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Нет агентов.</div>}
      </div>
    </div>
  );
}

function fmtAgo(t) {
  if (!t) return "—";
  const delta = (Date.now() - new Date(t).getTime()) / 1000;
  if (delta < 60) return `${Math.round(delta)}s назад`;
  if (delta < 3600) return `${Math.round(delta / 60)}m назад`;
  return `${Math.round(delta / 3600)}h назад`;
}
