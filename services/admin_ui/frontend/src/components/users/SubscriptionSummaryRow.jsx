import { Icon } from "../Icon.jsx";
import { StatusPill, deriveSubStatus } from "./StatusPill.jsx";
import { DaysCountdown, daysLeft } from "./DaysCountdown.jsx";

function fmtBytes(b) {
  if (b == null || b === 0) return null;
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = b; let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v >= 10 || i <= 1 ? Math.round(v) : v.toFixed(1)} ${units[i]}`;
}

export function SubscriptionSummaryRow({ sub, plan, onOpen }) {
  const status = deriveSubStatus(sub);
  const planName = plan?.name || (sub.plan_id ? `plan ${String(sub.plan_id).slice(0, 6)}…` : "—");
  const traffic = fmtBytes(sub.used_traffic_bytes);
  const dev = sub.device_count;
  const devMax = sub.max_devices;
  const devText = dev != null
    ? (devMax != null ? `${dev}/${devMax}` : String(dev))
    : null;

  return (
    <div className="u-subrow" onClick={() => onOpen?.(sub)} title="Открыть подписку">
      <div className="u-subrow-main">
        <div className="u-subrow-line">
          <span className="u-subrow-plan">{planName}</span>
          <StatusPill status={status} />
          <span className="muted small mono">{String(sub.id).slice(0, 8)}</span>
        </div>
        <div className="u-subrow-meta">
          <span><DaysCountdown days={daysLeft(sub.expires_at)} /></span>
          {sub.preferred_region && <span><Icon name="map-pin" size={11} /> {sub.preferred_region}</span>}
          {devText && <span><Icon name="smartphone" size={11} /> {devText}</span>}
          {traffic && <span><Icon name="activity" size={11} /> {traffic}</span>}
        </div>
      </div>
      <div className="u-subrow-action">
        <Icon name="chevron-right" size={14} />
      </div>
    </div>
  );
}
