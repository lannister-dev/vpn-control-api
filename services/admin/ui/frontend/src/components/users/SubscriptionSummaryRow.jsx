import { Icon } from "../Icon.jsx";
import { StatusPill, deriveSubStatus } from "./StatusPill.jsx";
import { DaysCountdown, daysLeft } from "./DaysCountdown.jsx";

function fmtBytes(b) {
  if (b == null) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, n = Number(b);
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return n.toFixed(n >= 100 || i === 0 ? 0 : 1) + " " + u[i];
}

function trafficCapBytes(plan) {
  if (!plan) return null;
  if (plan.traffic_limit_bytes != null && plan.traffic_limit_bytes > 0) return plan.traffic_limit_bytes;
  if (plan.traffic_limit_mb != null && plan.traffic_limit_mb > 0) return plan.traffic_limit_mb * 1024 * 1024;
  return null;
}

export function SubscriptionSummaryRow({ sub, plan, onOpen }) {
  const status = deriveSubStatus(sub);
  const days = daysLeft(sub.expires_at);
  const planName = plan?.name || (sub.plan_id ? `plan ${String(sub.plan_id).slice(0, 6)}…` : "—");

  const trafficUsed = sub.used_traffic_bytes || 0;
  const trafficCap = trafficCapBytes(plan);
  const trafficPct = trafficCap ? Math.min(100, Math.round((trafficUsed / trafficCap) * 100)) : null;
  const trafficTone = trafficPct == null ? "" : trafficPct >= 95 ? "bad" : trafficPct >= 80 ? "warn" : "";

  const dev = sub.device_count;
  const devMax = sub.max_devices;

  return (
    <div className="u-subtile" onClick={() => onOpen?.(sub)} title="Открыть подписку">
      <div className="u-subtile-head">
        <div className="u-subtile-head-main">
          <div className="u-subtile-plan">{planName}</div>
          <div className="u-subtile-id mono">{String(sub.id).slice(0, 8)}</div>
        </div>
        <div className="u-subtile-head-right">
          <StatusPill status={status} />
          <DaysCountdown days={days} />
        </div>
      </div>

      <div className="u-subtile-traffic">
        <div className="u-subtile-traffic-head">
          <span className="u-subtile-label">Трафик</span>
          <span className="u-subtile-traffic-vals mono">
            {trafficCap ? `${fmtBytes(trafficUsed)} / ${fmtBytes(trafficCap)}` : `${fmtBytes(trafficUsed)} · безлимит`}
            {trafficPct != null && <span className={`u-subtile-traffic-pct ${trafficTone}`}>{trafficPct}%</span>}
          </span>
        </div>
        <div className="u-subtile-traffic-track">
          <div
            className={`u-subtile-traffic-fill ${trafficTone}`}
            style={{ width: `${trafficPct ?? 0}%` }}
          />
        </div>
      </div>

      <div className="u-subtile-foot">
        <span>
          <Icon name="smartphone" size={12} />
          {dev != null ? (devMax != null ? `${dev}/${devMax}` : dev) : "—"}
          <span className="muted"> устройств</span>
        </span>
        <span>
          <Icon name="map-pin" size={12} />
          {sub.preferred_region || <span className="muted">любой регион</span>}
        </span>
        <span className="u-subtile-foot-open muted">
          <Icon name="chevron-right" size={14} />
        </span>
      </div>
    </div>
  );
}
