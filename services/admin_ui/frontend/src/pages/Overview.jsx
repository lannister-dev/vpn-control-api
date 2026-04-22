import { useMemo } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { Spark } from "../components/Spark.jsx";

export function OverviewPage() {
  const status = useQuery(() => api.get("/admin/status"), { interval: 15000 });
  const probes = useQuery(() => api.get("/probe/reports/recent?limit=200"), { interval: 15000 });

  const nodes = status.data?.nodes || [];
  const healthy = nodes.filter((n) => n.is_healthy && !n.is_draining && n.is_enabled).length;
  const draining = nodes.filter((n) => n.is_draining).length;
  const down = nodes.filter((n) => !n.is_healthy || !n.is_enabled).length;
  const total = nodes.length || 1;
  const pct = Math.round((healthy / total) * 100);
  const ringLen = 2 * Math.PI * 28;
  const dash = ringLen * (pct / 100);
  const tone = pct < 70 ? "bad" : pct < 90 ? "warn" : "";

  const probeList = probes.data || [];

  const { successRate, latencySpark, successSpark } = useMemo(() => {
    if (!probeList.length) return { successRate: null, latencySpark: [], successSpark: [] };
    const sorted = probeList.slice().sort((a, b) => new Date(a.checked_at) - new Date(b.checked_at));
    const reachable = sorted.filter((p) => p.is_reachable).length;
    const rate = Math.round((reachable / sorted.length) * 1000) / 10;

    const bucketCount = 20;
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
    return {
      successRate: rate,
      latencySpark: buckets.map((b) => (b.latN ? b.lat / b.latN : null)).filter((v) => v != null),
      successSpark: buckets.map((b) => (b.total ? (b.ok / b.total) * 100 : null)).filter((v) => v != null),
    };
  }, [probeList]);

  const problemNodes = useMemo(() => {
    const byNode = {};
    for (const p of probeList) {
      (byNode[p.node_id] = byNode[p.node_id] || []).push(p);
    }
    const items = [];
    for (const [nodeId, list] of Object.entries(byNode)) {
      list.sort((a, b) => new Date(b.checked_at) - new Date(a.checked_at));
      const last = list[0];
      if (!last || last.is_reachable) continue;
      let consecutive = 0;
      for (const p of list) { if (!p.is_reachable) consecutive++; else break; }
      items.push({ nodeId, node: nodes.find((n) => n.id === nodeId), consecutive, error: last.error });
    }
    items.sort((a, b) => b.consecutive - a.consecutive);
    return items.slice(0, 6);
  }, [probeList, nodes]);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Fleet overview</h1>
          <div className="page-subtitle">Здоровье флота, пробы и текущие проблемы</div>
        </div>
      </div>

      {status.error && <div className="card card-bad">Ошибка: {status.error.message}</div>}

      <div className="kpi-grid">
        <div className="kpi-card primary">
          <div className="kpi-label"><Icon name="shield-check" size={12} /> Здоровье флота</div>
          <div className="health-ring">
            <svg viewBox="0 0 64 64" className="ring-svg">
              <circle className="ring-bg" cx="32" cy="32" r="28" fill="none" strokeWidth="5" />
              <circle
                className={"ring-fg " + tone}
                cx="32" cy="32" r="28" fill="none" strokeWidth="5"
                strokeDasharray={`${dash} ${ringLen}`}
                transform="rotate(-90 32 32)"
                strokeLinecap="round"
              />
            </svg>
            <div className="health-main">
              <div className="kpi-value tnum">{pct}<span className="kpi-unit">%</span></div>
              <div className="health-sub">
                <span><span className="status-dot ok" /> {healthy} healthy</span>
                <span><span className="status-dot warn" /> {draining} draining</span>
                <span><span className="status-dot bad" /> {down} down</span>
              </div>
            </div>
          </div>
        </div>

        <KpiCell label="Серверов" value={nodes.length} icon="server" />
        <KpiCell
          label="Probe success"
          value={successRate != null ? `${successRate}%` : "—"}
          icon="radar"
          tone={successRate == null ? "muted" : successRate >= 95 ? "ok" : successRate >= 80 ? "warn" : "bad"}
          spark={successSpark}
          sparkColor="var(--ok)"
        />
        <KpiCell
          label="Avg latency"
          value={latencySpark.length ? `${Math.round(latencySpark[latencySpark.length - 1])}ms` : "—"}
          icon="zap"
          spark={latencySpark}
          sparkColor="var(--info)"
        />
        <KpiCell label="Draining" value={draining} icon="clock" tone={draining ? "warn" : "muted"} />
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <div className="kpi-label" style={{ marginBottom: 10 }}>Требуют внимания</div>
        {problemNodes.length === 0 && (
          <div className="muted small">Все зелёные, проблем по последним probe-сигналам нет.</div>
        )}
        {problemNodes.map(({ nodeId, node, consecutive, error }) => (
          <div key={nodeId} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
            <span className="status-dot bad" />
            <div style={{ flex: 1 }}>
              <strong>{node?.name || nodeId.slice(0, 8) + "…"}</strong>
              <span className="muted small" style={{ marginLeft: 6 }}>{node?.role} · {node?.region}</span>
            </div>
            <span className="chip chip-bad">{consecutive} подряд</span>
            <span className="small muted" style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={error || ""}>{error || ""}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function KpiCell({ label, value, icon, tone, spark, sparkColor }) {
  return (
    <div className={"kpi-card " + (tone ? "tone-" + tone : "")}>
      <div className="kpi-label"><Icon name={icon} size={12} /> {label}</div>
      <div className="kpi-value tnum">{value}</div>
      {spark && spark.length > 1 && <div style={{ marginTop: 6 }}><Spark data={spark} color={sparkColor || "var(--accent)"} w={130} h={28} /></div>}
    </div>
  );
}
