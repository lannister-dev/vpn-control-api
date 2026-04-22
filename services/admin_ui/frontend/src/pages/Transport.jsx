import { useMemo } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";

const VERDICT_TONE = { ok: "ok", lag: "warn", silent: "warn", dead: "bad" };

function fmtAgo(t) {
  if (!t) return "—";
  const delta = (Date.now() - new Date(t).getTime()) / 1000;
  if (delta < 60) return `${Math.round(delta)}s назад`;
  if (delta < 3600) return `${Math.round(delta / 60)}m назад`;
  return `${Math.round(delta / 3600)}h назад`;
}

export function TransportPage() {
  const nodes = useQuery(() => api.get("/admin/transport/nodes"), { interval: 15000 });
  const items = nodes.data?.items || [];

  const totals = useMemo(() => ({
    total: items.length,
    ok: items.filter((t) => t.health_verdict === "ok").length,
    pending: items.reduce((a, t) => a + (t.outbox_pending || 0), 0),
    failed: items.reduce((a, t) => a + (t.outbox_failed || 0), 0),
  }), [items]);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Очередь</h1>
          <div className="page-subtitle">
            {totals.total} агентов · {totals.ok} ok · outbox pending {totals.pending}{totals.failed ? ` · failed ${totals.failed}` : ""}
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={nodes.refetch}><Icon name="refresh" size={13} /> Обновить</button>
        </div>
      </div>

      {nodes.error && <div className="card card-bad">Ошибка: {nodes.error.message}</div>}

      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              <th>Нода</th>
              <th>Вердикт</th>
              <th style={{ textAlign: "right" }}>Эпоха</th>
              <th>Heartbeat</th>
              <th style={{ textAlign: "right" }}>Outbox</th>
              <th>Последний sync</th>
            </tr>
          </thead>
          <tbody>
            {items.map((t) => {
              const tone = VERDICT_TONE[t.health_verdict] || "";
              return (
                <tr key={t.node_id}>
                  <td className="mono" style={{ fontSize: 11 }}>{String(t.node_id).slice(0, 12)}…</td>
                  <td>
                    <span className={"pill " + tone}>
                      {tone && <span className={`status-dot ${tone}`} />} {t.health_verdict || "—"}
                    </span>
                  </td>
                  <td className="tbl-num mono">{t.current_epoch}</td>
                  <td className="small muted">{fmtAgo(t.last_heartbeat_received_at)}</td>
                  <td className="tbl-num mono">
                    {t.outbox_pending || 0}
                    {t.outbox_failed ? <span className="pill bad" style={{ marginLeft: 6 }}>err {t.outbox_failed}</span> : null}
                  </td>
                  <td className="small muted">{fmtAgo(t.last_sync_report_received_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(nodes.loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!nodes.loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Нет агентов.</div>}
      </div>
    </div>
  );
}
