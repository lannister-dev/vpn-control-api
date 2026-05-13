import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { Spark } from "../components/Spark.jsx";
import { nodeGeo } from "../lib/geo.js";

function spark(seed, len = 24, base = 50, vol = 25) {
  let x = seed;
  const out = [];
  for (let i = 0; i < len; i++) {
    x = (x * 9301 + 49297) % 233280;
    out.push(base + ((x / 233280) - 0.5) * vol * 2);
  }
  return out;
}

function relTime(iso) {
  if (!iso) return "";
  const diff = Math.max(0, Date.now() - new Date(iso).getTime());
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

const PERIOD_OPTS = [
  { id: "1h", label: "1 час" },
  { id: "24h", label: "24 часа" },
  { id: "7d", label: "7 дней" },
  { id: "30d", label: "30 дней" },
];

export function OverviewPage({ onOpenNode, onGoto }) {
  const [period, setPeriod] = useState(() => localStorage.getItem("ov.period") || "24h");
  const [periodOpen, setPeriodOpen] = useState(false);

  const setP = (p) => { setPeriod(p); localStorage.setItem("ov.period", p); setPeriodOpen(false); };

  const status = useQuery(() => api.get("/admin/status"), { interval: 15000 });
  const probes = useQuery(() => api.get("/probe/reports/recent?limit=300"), { interval: 15000 });
  const routes = useQuery(() => api.get("/routes?limit=500"), { interval: 20000 });
  const zones = useQuery(() => api.get("/zones"), { interval: 60000 });
  const plans = useQuery(() => api.get("/plans"), { interval: 60000 });
  const traffic = useQuery(
    () => api.get(`/admin/traffic/nodes?period=${period}&limit=500`).catch((e) => (e.status === 404 ? { items: [] } : Promise.reject(e))),
    { interval: 60000, deps: [period] },
  );
  const subsStats = useQuery(() => api.get("/subscriptions/stats").catch(() => null), { interval: 60000 });
  const probeStatsApi = useQuery(() => api.get("/probe/stats?window_hours=1").catch(() => null), { interval: 30000 });

  const nodes = status.data?.nodes || [];
  const totals = status.data?.totals || {};
  const probeList = probes.data || [];
  const routesList = routes.data || [];
  const zonesList = zones.data?.items || [];

  const healthy = totals.nodes_healthy ?? nodes.filter((n) => n.is_healthy && !n.is_draining && n.is_enabled).length;
  const total = totals.nodes_total ?? nodes.length;
  const draining = totals.nodes_draining ?? nodes.filter((n) => n.is_draining).length;
  const down = Math.max(0, (total || 0) - healthy - draining);
  const healthPct = total ? Math.round((healthy / total) * 100) : 0;
  const ringLen = 2 * Math.PI * 28;
  const dash = ringLen * (healthPct / 100);

  const probeStats = useMemo(() => {
    if (!probeList.length) return { successRate: null, avgLatency: null, latencySpark: [], successSpark: [] };
    const sorted = probeList.slice().sort((a, b) => new Date(a.checked_at) - new Date(b.checked_at));
    const reachable = sorted.filter((p) => p.is_reachable).length;
    const rate = Math.round((reachable / sorted.length) * 1000) / 10;
    const lats = sorted.filter((p) => p.is_reachable && p.latency_ms != null).map((p) => p.latency_ms);
    const avg = lats.length ? Math.round(lats.reduce((a, b) => a + b, 0) / lats.length) : null;

    const bucketCount = 22;
    const buckets = Array.from({ length: bucketCount }, () => ({ total: 0, ok: 0, lat: 0, latN: 0 }));
    const first = new Date(sorted[0].checked_at).getTime();
    const last = new Date(sorted[sorted.length - 1].checked_at).getTime();
    const span = Math.max(1, last - first);
    for (const p of sorted) {
      const idx = Math.min(bucketCount - 1, Math.floor(((new Date(p.checked_at).getTime() - first) / span) * bucketCount));
      const b = buckets[idx];
      b.total++;
      if (p.is_reachable) b.ok++;
      if (p.is_reachable && p.latency_ms != null) { b.lat += p.latency_ms; b.latN++; }
    }
    const latencySpark = buckets.map((b) => (b.latN ? b.lat / b.latN : null)).filter((v) => v != null);
    const successSpark = buckets.map((b) => (b.total ? (b.ok / b.total) * 100 : null)).filter((v) => v != null);
    const halfTrend = (arr) => {
      if (arr.length < 4) return null;
      const mid = Math.floor(arr.length / 2);
      const avgOf = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
      const prev = avgOf(arr.slice(0, mid));
      const curr = avgOf(arr.slice(mid));
      return curr - prev;
    };
    return {
      successRate: rate,
      avgLatency: avg,
      latencySpark,
      successSpark,
      latencyDelta: halfTrend(latencySpark),
      successDelta: halfTrend(successSpark),
    };
  }, [probeList]);

  const issues = useMemo(() => {
    const items = [];

    const byNode = {};
    for (const p of probeList) {
      (byNode[p.node_id] = byNode[p.node_id] || []).push(p);
    }
    for (const [nodeId, list] of Object.entries(byNode)) {
      list.sort((a, b) => new Date(b.checked_at) - new Date(a.checked_at));
      const last = list[0];
      if (!last || last.is_reachable) continue;
      let consecutive = 0;
      for (const p of list) { if (!p.is_reachable) consecutive++; else break; }
      if (consecutive < 3) continue;
      const node = nodes.find((n) => n.id === nodeId);
      items.push({
        severity: consecutive >= 10 ? "bad" : "warn",
        title: `${node?.name || nodeId.slice(0, 8) + "…"} heartbeat потерян`,
        sub: `${consecutive} probe-сигналов подряд · ${last.error || "no response"}`,
        time: relTime(last.checked_at),
        _sort: 100 + consecutive,
        kind: "node",
        target: nodeId,
      });
    }

    for (const r of routesList) {
      if (r.health_status === "blocked") {
        items.push({
          severity: "bad",
          title: `Маршрут ${r.name} заблокирован`,
          sub: `${r.id.slice(0, 8)}… · health ${r.health_status}`,
          time: relTime(r.updated_at || r.created_at),
          _sort: 80,
          kind: "route",
          target: r.id,
        });
      }
    }
    for (const r of routesList) {
      if (r.health_status === "degraded" || r.health_status === "suspected") {
        items.push({
          severity: "warn",
          title: `${r.name} — ${r.health_status}`,
          sub: `weight ${r.effective_weight}/${r.base_weight}`,
          time: relTime(r.updated_at || r.created_at),
          _sort: 40,
          kind: "route",
          target: r.id,
        });
      }
    }

    for (const n of nodes) {
      if (n.is_draining) {
        items.push({
          severity: "warn",
          title: `${n.name} в draining`,
          sub: `${n.region} · ${n.placements_backend || 0} плейсментов`,
          time: relTime(n.last_sync_at),
          _sort: 30,
          kind: "node",
          target: n.id,
        });
      }
    }
    for (const n of nodes) {
      if (!n.is_enabled) {
        items.push({
          severity: "info",
          title: `${n.name} отключён`,
          sub: `${n.role} · ${n.region}`,
          time: relTime(n.last_sync_at),
          _sort: 10,
          kind: "node",
          target: n.id,
        });
      }
    }

    items.sort((a, b) => b._sort - a._sort);
    return items.slice(0, 6);
  }, [probeList, routesList, nodes]);

  const activity = useMemo(() => {
    const out = [];
    const recentOk = probeList.slice().sort((a, b) => new Date(b.checked_at) - new Date(a.checked_at)).slice(0, 30);
    for (const p of recentOk) {
      if (!p.is_reachable) continue;
      const n = nodes.find((x) => x.id === p.node_id);
      if (!n) continue;
      out.push({
        tone: "ok",
        text: `Probe OK от ${p.source} к ${n.name}`,
        meta: `${p.probe_kind} · ${relTime(p.checked_at)} назад · ${p.latency_ms ?? "—"}ms`,
      });
      if (out.length >= 2) break;
    }
    for (const r of routesList.slice(0, 20)) {
      if (r.health_status === "warming_up") {
        out.push({ tone: "warn", text: `Маршрут ${r.name} прогревается`, meta: `weight ${r.effective_weight}/${r.base_weight}` });
        if (out.length >= 3) break;
      }
    }
    for (const r of routesList) {
      if (r.health_status === "blocked") {
        out.push({ tone: "bad", text: `${r.name} заблокирован probe-политикой`, meta: `${relTime(r.updated_at || r.created_at)} назад` });
        break;
      }
    }
    for (const n of nodes.slice(0, 20)) {
      if (n.is_draining) {
        out.push({ tone: "warn", text: `${n.name} → drain (${n.placements_backend || 0} плейсментов)`, meta: `${n.region}` });
        break;
      }
    }
    for (const n of nodes) {
      if (n.is_healthy && n.is_enabled) {
        out.push({ tone: "ok", text: `${n.name} синхронизирован`, meta: `${n.role} · ${relTime(n.last_sync_at)} назад` });
        break;
      }
    }
    while (out.length < 4) {
      out.push({ tone: "ok", text: "Без новых событий", meta: "system · только что" });
    }
    return out.slice(0, 6);
  }, [probeList, routesList, nodes]);

  const regionRows = useMemo(() => {
    const byRegion = {};
    for (const n of nodes) {
      const key = n.region || "—";
      if (!byRegion[key]) byRegion[key] = { region: key, nodes: [], h: [0, 0, 0], keys: 0 };
      byRegion[key].nodes.push(n);
      byRegion[key].keys += n.placements_backend || 0;
      if (!n.is_enabled) byRegion[key].h[2]++;
      else if (n.is_draining || !n.is_healthy) byRegion[key].h[1]++;
      else byRegion[key].h[0]++;
    }
    const nodeIdToRegion = Object.fromEntries(nodes.map((n) => [n.id, n.region]));
    const trafficByRegion = {};
    for (const t of (traffic.data?.items || [])) {
      const reg = nodeIdToRegion[t.node_id] || "—";
      trafficByRegion[reg] = (trafficByRegion[reg] || 0) + (t.bytes_in || 0) + (t.bytes_out || 0);
    }
    const zoneByCode = Object.fromEntries((zonesList || []).map((z) => [z.code, z]));
    const rows = Object.values(byRegion).map((r, i) => {
      const avgLoad = r.nodes.length
        ? Math.min(1, r.nodes.reduce((a, n) => a + (n.placements_backend || 0), 0) / (r.nodes.length * 50))
        : 0;
      const seed = (r.region.charCodeAt(0) + i) * 7 + 11;
      const zoneNode = r.nodes[0];
      const zone = zoneByCode[zoneNode?.zone];
      const emoji = zone?.emoji || nodeGeo(r.region).flag;
      const name = zone?.name || nodeGeo(r.region).country;
      const tone = r.h[2] > 0 ? "bad" : r.h[1] > 0 ? "warn" : "ok";
      return {
        label: `${emoji} ${r.region} · ${name}`,
        cnt: r.nodes.length,
        h: r.h,
        load: avgLoad,
        trafficBytes: trafficByRegion[r.region],
        keys: r.keys,
        seed,
        tone,
      };
    });
    rows.sort((a, b) => b.cnt - a.cnt);
    return rows;
  }, [nodes, zonesList, traffic.data]);

  const activeSubsValue = plans.data?.items?.reduce((a, p) => a + (p.is_active ? 1 : 0), 0);
  const latestLat = probeStats.avgLatency;

  const trafficTotal = useMemo(() => {
    const items = traffic.data?.items || [];
    if (!items.length) return null;
    return items.reduce((a, t) => a + (t.bytes_in || 0) + (t.bytes_out || 0), 0);
  }, [traffic.data]);
  const trafficPrev = traffic.data?.previous_total_bytes ?? null;
  const trafficDeltaPct = useMemo(() => {
    if (trafficTotal == null || trafficPrev == null || trafficPrev === 0) return null;
    return ((trafficTotal - trafficPrev) / trafficPrev) * 100;
  }, [trafficTotal, trafficPrev]);
  const trafficFmt = (b) => {
    if (b == null) return { v: "—", u: "" };
    const units = ["B", "KB", "MB", "GB", "TB", "PB"];
    let i = 0; let v = b;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return { v: v >= 10 || i <= 1 ? String(Math.round(v)) : v.toFixed(1), u: units[i] };
  };
  const tf = trafficFmt(trafficTotal);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Fleet overview</h1>
          <div className="page-subtitle">Сводка по инфраструктуре и бизнесу · период {PERIOD_OPTS.find((o) => o.id === period)?.label}</div>
        </div>
        <div className="page-head-actions">
          <div style={{ position: "relative" }}>
            <button className="btn" onClick={() => setPeriodOpen((v) => !v)}>
              <Icon name="clock" size={13} /> {PERIOD_OPTS.find((o) => o.id === period)?.label}
              <Icon name="chevron-down" size={12} />
            </button>
            {periodOpen && (
              <>
                <div style={{ position: "fixed", inset: 0, zIndex: 50 }} onClick={() => setPeriodOpen(false)} />
                <div style={{
                  position: "absolute", top: "100%", right: 0, marginTop: 4, minWidth: 140, zIndex: 51,
                  background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8,
                  boxShadow: "var(--shadow-lg)", padding: 4,
                }}>
                  {PERIOD_OPTS.map((o) => (
                    <button key={o.id} onClick={() => setP(o.id)}
                      style={{
                        display: "block", width: "100%", textAlign: "left", padding: "7px 10px",
                        border: 0, background: period === o.id ? "var(--accent-soft)" : "transparent",
                        cursor: "pointer", borderRadius: 5, color: "var(--text)", fontSize: 13,
                      }}
                      onMouseEnter={(e) => period !== o.id && (e.currentTarget.style.background = "var(--surface-hover)")}
                      onMouseLeave={(e) => period !== o.id && (e.currentTarget.style.background = "transparent")}>
                      {o.label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {status.error && <div className="card card-bad">Ошибка: {status.error.message}</div>}

      <div className="sec">
        <div className="kpi-hero">
          <div className="kpi-cell primary">
            <div className="kpi-label"><Icon name="shield-check" size={12} /> Здоровье флота</div>
            <div className="health-ring">
              <svg className="ring-svg" viewBox="0 0 64 64">
                <circle className="ring-bg" cx="32" cy="32" r="28" fill="none" strokeWidth="5" />
                <circle
                  className={`ring-fg ${healthPct < 70 ? "bad" : healthPct < 90 ? "warn" : ""}`}
                  cx="32" cy="32" r="28" fill="none" strokeWidth="5"
                  strokeDasharray={`${dash} ${ringLen}`}
                  transform="rotate(-90 32 32)"
                  strokeLinecap="round"
                />
              </svg>
              <div className="health-main">
                <div className="kpi-value tnum">{healthPct}<span className="kpi-unit">%</span></div>
                <div className="health-sub">
                  <span><span className="status-dot ok" /> {healthy} healthy</span>
                  <span><span className="status-dot warn" /> {draining} draining</span>
                  <span><span className="status-dot bad" /> {down} down</span>
                </div>
              </div>
            </div>
          </div>

          {(() => {
            const a = subsStats.data;
            const activeDiff = a?.active != null && a?.active_24h_ago != null ? a.active - a.active_24h_ago : null;
            return (
              <KpiCell
                label="Активные подписки"
                value={a?.active != null ? a.active.toLocaleString("ru-RU") : "—"}
                delta={
                  activeDiff != null
                    ? `${activeDiff > 0 ? "+" : ""}${activeDiff}`
                    : a?.expired
                      ? `${a.expired} истекли`
                      : null
                }
                deltaSub={activeDiff != null ? "vs вчера" : null}
                deltaTone={
                  activeDiff == null
                    ? (a?.expired ? "down" : "up")
                    : activeDiff > 0 ? "up" : activeDiff < 0 ? "down" : "flat"
                }
                icon="key"
                sparkSeed={13}
                sparkColor="var(--accent)"
              />
            );
          })()}
          <KpiCell
            label={period === "1h" ? "Трафик за час" : period === "24h" ? "Трафик сегодня" : period === "7d" ? "Трафик за 7д" : "Трафик за 30д"}
            value={tf.v}
            unit={tf.u}
            delta={
              trafficDeltaPct != null
                ? `${trafficDeltaPct > 0 ? "+" : ""}${trafficDeltaPct.toFixed(1)}%`
                : null
            }
            deltaSub={trafficDeltaPct != null ? "vs прошлый период" : null}
            deltaTone={
              trafficDeltaPct == null
                ? ""
                : trafficDeltaPct > 1 ? "up"
                : trafficDeltaPct < -1 ? "down" : "flat"
            }
            icon="activity"
            sparkSeed={42}
            sparkColor="var(--ok)"
          />
          {(() => {
            const ps = probeStatsApi.data;
            const latDiff = ps?.avg_latency_ms != null && ps?.avg_latency_ms_24h_ago != null
              ? ps.avg_latency_ms - ps.avg_latency_ms_24h_ago : null;
            return (
              <KpiCell
                label="Средняя latency"
                value={ps?.avg_latency_ms != null ? Math.round(ps.avg_latency_ms).toString() : latestLat != null ? String(latestLat) : "—"}
                unit={ps?.avg_latency_ms != null || latestLat != null ? "ms" : ""}
                delta={
                  latDiff != null
                    ? `${latDiff > 0 ? "+" : ""}${Math.round(latDiff)} ms`
                    : null
                }
                deltaSub={latDiff != null ? "vs вчера" : null}
                deltaTone={
                  latDiff == null
                    ? ""
                    : latDiff > 5 ? "down"
                    : latDiff < -5 ? "up" : "flat"
                }
                icon="zap"
                sparkSeed={91}
                sparkColor="var(--warn)"
                realSpark={probeStats.latencySpark}
              />
            );
          })()}
          {(() => {
            const ps = probeStatsApi.data;
            const sDiff = ps?.success_rate != null && ps?.success_rate_24h_ago != null
              ? ps.success_rate - ps.success_rate_24h_ago : null;
            const rate = ps?.success_rate ?? probeStats.successRate;
            return (
              <KpiCell
                label="Probe success"
                value={rate != null ? String(rate) : "—"}
                unit={rate != null ? "%" : ""}
                delta={
                  sDiff != null
                    ? `${sDiff > 0 ? "+" : ""}${sDiff.toFixed(1)}%`
                    : null
                }
                deltaSub={sDiff != null ? "vs вчера" : null}
                deltaTone={
                  sDiff == null
                    ? ""
                    : sDiff > 0.2 ? "up"
                    : sDiff < -0.2 ? "down" : "flat"
                }
                icon="radar"
                sparkSeed={27}
                sparkColor="var(--info)"
                realSpark={probeStats.successSpark}
              />
            );
          })()}
        </div>
      </div>

      <div className="sec split-2">
        <div className="card">
          <div className="card-head">
            <Icon name="alert-triangle" size={14} style={{ color: "var(--warn)" }} />
            <div className="sec-title">Требуют внимания</div>
            <span className="pill warn">{issues.length}</span>
            <div className="sec-spacer" />
            <button className="btn btn-ghost btn-xs" onClick={() => onGoto && onGoto("probes")}>
              Все инциденты <Icon name="arrow-up-right" size={11} />
            </button>
          </div>
          <div>
            {issues.length === 0 && (
              <div className="muted" style={{ padding: 14 }}>Всё зелёное — проблем нет.</div>
            )}
            {issues.map((is, i) => (
              <div
                key={i}
                className="issue"
                onClick={() => {
                  if (is.kind === "node") {
                    const n = nodes.find((nn) => nn.id === is.target);
                    if (n && onOpenNode) onOpenNode(n);
                  } else if (is.kind === "route" && onGoto) {
                    onGoto("routes");
                  }
                }}
              >
                <div className={`issue-icon ${is.severity}`}>
                  <Icon name={is.severity === "bad" ? "alert-circle" : is.severity === "warn" ? "alert-triangle" : "info"} size={14} />
                </div>
                <div className="issue-main">
                  <div className="issue-title">{is.title}</div>
                  <div className="issue-sub">{is.sub}</div>
                </div>
                <div className="issue-time">{is.time}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <Icon name="activity" size={14} />
            <div className="sec-title">Последняя активность</div>
            <div className="sec-spacer" />
            <button className="btn btn-ghost btn-xs" onClick={() => onGoto && onGoto("ops")}>
              Полный аудит <Icon name="arrow-up-right" size={11} />
            </button>
          </div>
          <div>
            {activity.map((a, i) => (
              <div key={i} className="activity">
                <div className={`activity-dot ${a.tone}`} />
                <div className="activity-main">
                  <div className="activity-text">{a.text}</div>
                  <div className="activity-meta">{a.meta}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="sec">
        <div className="sec-head">
          <div className="sec-title">Регионы</div>
          <div className="sec-sub">Нагрузка и маршруты по регионам</div>
          <div className="sec-spacer" />
          <button className="btn btn-ghost btn-xs" onClick={() => onGoto && onGoto("zones")}>
            Все зоны <Icon name="arrow-up-right" size={11} />
          </button>
        </div>
        <div className="card">
          <table className="tbl">
            <thead>
              <tr>
                <th>Зона</th>
                <th>Серверов</th>
                <th>Здоровье</th>
                <th>Средняя нагрузка</th>
                <th style={{ textAlign: "right" }}>Трафик 24h</th>
                <th style={{ textAlign: "right" }}>Активные ключи</th>
                <th style={{ width: 120 }}>Тренд</th>
              </tr>
            </thead>
            <tbody>
              {regionRows.length === 0 && (
                <tr><td colSpan={7} className="muted" style={{ padding: 14 }}>Нод нет.</td></tr>
              )}
              {regionRows.map((r, i) => {
                const t = trafficFmt(r.trafficBytes);
                return (
                  <tr key={i}>
                    <td style={{ fontWeight: 500 }}>{r.label}</td>
                    <td className="tbl-num">{r.cnt}</td>
                    <td>
                      <div style={{ display: "flex", gap: 4 }}>
                        {r.h[0] > 0 && <span className="pill ok" style={{ padding: "0 6px" }}>{r.h[0]}</span>}
                        {r.h[1] > 0 && <span className="pill warn" style={{ padding: "0 6px" }}>{r.h[1]}</span>}
                        {r.h[2] > 0 && <span className="pill bad" style={{ padding: "0 6px" }}>{r.h[2]}</span>}
                      </div>
                    </td>
                    <td><LoadBar v={r.load} /></td>
                    <td className="tbl-num">{r.trafficBytes != null ? `${t.v} ${t.u}` : "—"}</td>
                    <td className="tbl-num">{r.keys}</td>
                    <td>
                      <Spark data={spark(r.seed, 24, 50, 25)} color={`var(--${r.tone})`} w={100} h={24} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="sec" style={{ paddingBottom: 40 }}>
        <div className="sec-head">
          <div className="sec-title">Быстрые действия</div>
          <div className="sec-sub">Из командной палитры ⌘K или отсюда</div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
          {[
            { i: "server", l: "Добавить сервер", s: "Новая нода и первичная конфигурация", tab: "nodes", action: "create" },
            { i: "route", l: "Создать маршрут", s: "Entry → Backend связка с весом", tab: "routes", action: "create" },
            { i: "arrow-right", l: "Мигрировать плейсменты", s: "Перенести нагрузку между нодами", tab: "ops" },
            { i: "sliders", l: "Probe-политика", s: "Пороги маршрутов и авто-drain", tab: "settings" },
          ].map((a, i) => (
            <button
              key={i}
              className="card"
              style={{ textAlign: "left", border: "1px solid var(--border)", padding: 14, cursor: "pointer", background: "var(--surface)" }}
              onClick={() => onGoto && onGoto(a.tab, a.action ? { action: a.action } : undefined)}
            >
              <Icon name={a.i} size={16} style={{ color: "var(--accent)", marginBottom: 8 }} />
              <div style={{ fontWeight: 500, fontSize: 13 }}>{a.l}</div>
              <div className="muted text-xs" style={{ marginTop: 4 }}>{a.s}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function KpiCell({ label, value, unit, delta, deltaSub, deltaTone, icon, sparkSeed, sparkColor, realSpark }) {
  const data = realSpark && realSpark.length > 2 ? realSpark : spark(sparkSeed, 22, 50, 25);
  const hasDelta = delta != null && delta !== "" && delta !== "—";
  return (
    <div className="kpi-cell">
      <div className="kpi-label">
        <Icon name={icon} size={12} style={{ flexShrink: 0 }} /> <span>{label}</span>
      </div>
      <div className="kpi-value-row">
        <div className="kpi-value tnum">{value}{unit && <span className="kpi-unit">{unit}</span>}</div>
        <div className="kpi-spark">
          <Spark data={data} color={sparkColor} w={54} h={20} />
        </div>
      </div>
      {hasDelta && (
        <div className={`kpi-delta ${deltaTone || ""}`}>
          <Icon name={deltaTone === "up" ? "trending-up" : deltaTone === "down" ? "trending-down" : "arrow-right"} size={12} />
          <span>{delta}</span>
          {deltaSub && <span className="muted" style={{ marginLeft: 4 }}>{deltaSub}</span>}
        </div>
      )}
    </div>
  );
}

function LoadBar({ v }) {
  const pct = Math.round(v * 100);
  const tone = pct > 80 ? "bad" : pct > 65 ? "warn" : "ok";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: "var(--surface-2)", borderRadius: 4, overflow: "hidden", maxWidth: 140 }}>
        <div style={{ width: `${pct}%`, height: "100%", background: `var(--${tone})` }} />
      </div>
      <span className="mono" style={{ color: `var(--${tone})`, fontWeight: 500 }}>{pct}%</span>
    </div>
  );
}
