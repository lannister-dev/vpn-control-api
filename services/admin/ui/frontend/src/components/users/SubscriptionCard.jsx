import { Icon } from "../Icon.jsx";
import { StatusPill, deriveSubStatus } from "./StatusPill.jsx";
import { TrafficBar } from "./TrafficBar.jsx";
import { DaysCountdown, daysLeft } from "./DaysCountdown.jsx";

function fmtBytes(b) {
  if (b == null) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, n = Number(b);
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return n.toFixed(n >= 100 || i === 0 ? 0 : 1) + " " + u[i];
}

function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" });
}

export function SubscriptionCard({ sub, plan, onOpen, onExtend }) {
  const status = deriveSubStatus(sub);
  const days = daysLeft(sub.expires_at);
  const planName = plan?.name || (sub.plan_id ? String(sub.plan_id).slice(0, 8) + "…" : "—");
  const trafficUsed = sub.used_traffic_bytes;
  const trafficCap =
    plan?.traffic_limit_bytes > 0
      ? plan.traffic_limit_bytes
      : (plan?.traffic_limit_mb > 0 ? plan.traffic_limit_mb * 1024 * 1024 : null);

  return (
    <div className="u-subcard">
      <div className="u-subcard-head">
        <div className="u-subcard-plan">
          <span className="u-subcard-plan-name">{planName}</span>
          <StatusPill status={status} />
        </div>
        <div className="u-subcard-id mono">{String(sub.id).slice(0, 8)}…</div>
      </div>

      {plan && (
        <div className="u-subcard-sub muted small">
          {plan.price_rub != null && <>{Number(plan.price_rub)}₽</>}
          {plan.duration_days != null && <span> · {plan.duration_days} дн.</span>}
        </div>
      )}

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
        <div>
          <div className="u-subcard-micro">Активна до</div>
          <div className="u-subcard-micro-val">{fmtDate(sub.expires_at)}</div>
        </div>
        <div>
          <div className="u-subcard-micro">Создана</div>
          <div className="u-subcard-micro-val">{fmtDate(sub.created_at)}</div>
        </div>
        <div>
          <div className="u-subcard-micro">HWID</div>
          <div className="u-subcard-micro-val">{sub.hwid_enabled ? "вкл" : "выкл"}</div>
        </div>
      </div>

      <div className="u-subcard-traffic">
        <div className="u-subcard-micro">Трафик</div>
        {trafficCap != null ? (
          <TrafficBar used={trafficUsed} cap={trafficCap} size="lg" />
        ) : (
          <div className="u-subcard-micro-val">
            <Icon name="infinity" size={12} /> {fmtBytes(trafficUsed)} использовано · безлимит
          </div>
        )}
        {sub.lifetime_used_traffic_bytes > 0 && (
          <div className="muted small" style={{ marginTop: 4 }}>
            За всё время: {fmtBytes(sub.lifetime_used_traffic_bytes)}
          </div>
        )}
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
