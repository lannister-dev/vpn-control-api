import { Icon } from "../Icon.jsx";
import { StatusPill, deriveSubStatus } from "./StatusPill.jsx";
import { TrafficBar } from "./TrafficBar.jsx";
import { DaysCountdown, daysLeft } from "./DaysCountdown.jsx";

export function SubscriptionCard({ sub, plan, onOpen, onExtend }) {
  const status = deriveSubStatus(sub);
  const days = daysLeft(sub.expires_at);
  const planName = plan?.name || (sub.plan_id ? String(sub.plan_id).slice(0, 8) + "…" : "—");
  const trafficUsed = sub.used_traffic_bytes;
  const trafficCap = plan?.traffic_limit_mb ? plan.traffic_limit_mb * 1024 * 1024 : null;

  return (
    <div className="u-subcard">
      <div className="u-subcard-head">
        <div className="u-subcard-plan">
          <span className="u-subcard-plan-name">{planName}</span>
          <StatusPill status={status} />
        </div>
        <div className="u-subcard-id mono">{String(sub.id).slice(0, 8)}…</div>
      </div>

      <div className="u-subcard-meta">
        <div>
          <div className="u-subcard-micro">Осталось</div>
          <DaysCountdown days={days} />
        </div>
        <div>
          <div className="u-subcard-micro">Регион</div>
          <div className="u-subcard-micro-val">{sub.preferred_region || "—"}</div>
        </div>
        <div>
          <div className="u-subcard-micro">Устройств</div>
          <div className="u-subcard-micro-val">
            <Icon name="smartphone" size={12} />
            {sub.device_count ?? "—"}
            {sub.max_devices != null && (
              <span className="muted">/{sub.max_devices}</span>
            )}
          </div>
        </div>
      </div>

      <div className="u-subcard-traffic">
        <div className="u-subcard-micro">Трафик</div>
        <TrafficBar used={trafficUsed} cap={trafficCap} size="lg" />
      </div>

      <div className="u-subcard-actions">
        {onExtend && (
          <button className="btn btn-ghost btn-sm" onClick={() => onExtend(sub)}>
            <Icon name="rotate-cw" size={12} /> Продлить
          </button>
        )}
        {onOpen && (
          <button className="btn btn-ghost btn-sm" onClick={() => onOpen(sub)}>
            <Icon name="external-link" size={12} /> Открыть
          </button>
        )}
      </div>
    </div>
  );
}
