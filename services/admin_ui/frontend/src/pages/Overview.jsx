import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";

export function OverviewPage() {
  const { data: status, loading, error } = useQuery(() => api.get("/admin/status"), { interval: 15000 });

  const nodes = status?.nodes || [];
  const healthy = nodes.filter((n) => n.is_healthy && !n.is_draining && n.is_enabled).length;
  const draining = nodes.filter((n) => n.is_draining).length;
  const down = nodes.filter((n) => !n.is_healthy || !n.is_enabled).length;
  const total = nodes.length || 1;
  const pct = Math.round((healthy / total) * 100);

  const ringLen = 2 * Math.PI * 28;
  const dash = ringLen * (pct / 100);
  const tone = pct < 70 ? "bad" : pct < 90 ? "warn" : "";

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Fleet overview</h1>
          <div className="page-subtitle">Сводка по инфраструктуре, обновляется каждые 15 секунд</div>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

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
        <KpiCell label="Активных" value={healthy} icon="shield-check" tone="ok" />
        <KpiCell label="Draining" value={draining} icon="clock" tone={draining ? "warn" : "muted"} />
        <KpiCell label="Нерабочих" value={down} icon="activity" tone={down ? "bad" : "muted"} />
      </div>

      {loading && !status && <div className="muted" style={{ marginTop: 24 }}>Загрузка…</div>}
    </div>
  );
}

function KpiCell({ label, value, icon, tone }) {
  return (
    <div className={"kpi-card " + (tone ? "tone-" + tone : "")}>
      <div className="kpi-label"><Icon name={icon} size={12} /> {label}</div>
      <div className="kpi-value tnum">{value}</div>
    </div>
  );
}
