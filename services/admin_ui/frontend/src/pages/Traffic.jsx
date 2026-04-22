import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { Spark } from "../components/Spark.jsx";
import { nodeGeo } from "../lib/geo.js";

function spark(seed, len = 22, base = 50, vol = 30) {
  let x = seed || 7;
  const out = [];
  for (let i = 0; i < len; i++) {
    x = (x * 9301 + 49297) % 233280;
    out.push(base + ((x / 233280) - 0.5) * vol * 2);
  }
  return out;
}

function formatBytes(n) {
  if (!n) return "0";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0; let v = Number(n);
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export function TrafficPage() {
  const [period, setPeriod] = useState("24h");
  const { data, loading, error, refetch } = useQuery(
    () => api.get(`/admin/traffic/nodes?period=${period}&limit=100`).catch((e) => {
      if (e.status === 404) return { items: [] };
      throw e;
    }),
    { interval: 30000, deps: [period] },
  );
  const items = data?.items || [];

  const totals = useMemo(() => {
    const inB = items.reduce((a, t) => a + (t.bytes_in || 0), 0);
    const outB = items.reduce((a, t) => a + (t.bytes_out || 0), 0);
    const sess = items.reduce((a, t) => a + (t.sessions || 0), 0);
    return { inB, outB, sess };
  }, [items]);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Трафик</h1>
          <div className="page-subtitle">
            Σ In {formatBytes(totals.inB)} · Σ Out {formatBytes(totals.outB)} · {totals.sess} сессий
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={refetch}><Icon name="refresh" size={13} /> Обновить</button>
          <button className="btn"><Icon name="download" size={13} /> Экспорт</button>
        </div>
      </div>

      <div className="filterbar">
        <select className="select" value={period} onChange={(e) => setPeriod(e.target.value)}>
          <option value="1h">1 час</option>
          <option value="24h">24 часа</option>
          <option value="7d">7 дней</option>
          <option value="30d">30 дней</option>
        </select>
        <div style={{ marginLeft: "auto" }}>
          <span className="muted text-xs">{items.length} нод</span>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              <th>Нода</th>
              <th>Роль</th>
              <th style={{ textAlign: "right" }}>In</th>
              <th style={{ textAlign: "right" }}>Out</th>
              <th style={{ textAlign: "right" }}>Сессии</th>
              <th style={{ width: 120 }}>Тренд</th>
            </tr>
          </thead>
          <tbody>
            {items.map((t, idx) => {
              const seed = parseInt(String(t.node_id || idx).replace(/-/g, "").slice(0, 6), 16) || (idx + 11);
              const geo = t.region ? nodeGeo(t.region) : null;
              return (
                <tr key={t.node_id || idx}>
                  <td>
                    {geo && <span style={{ marginRight: 6 }}>{geo.flag}</span>}
                    <span style={{ fontWeight: 500 }}>{t.node_name || <span className="mono muted">{String(t.node_id).slice(0, 12)}…</span>}</span>
                    {t.region && <div className="mono muted" style={{ fontSize: 11 }}>{t.region}</div>}
                  </td>
                  <td><span className="pill">{t.role || "—"}</span></td>
                  <td className="tbl-num mono">{formatBytes(t.bytes_in)}</td>
                  <td className="tbl-num mono">{formatBytes(t.bytes_out)}</td>
                  <td className="tbl-num mono">{t.sessions ?? "—"}</td>
                  <td><Spark data={spark(seed, 22, 50, 30)} color="var(--ok)" w={100} h={22} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Нет данных.</div>}
      </div>
    </div>
  );
}
