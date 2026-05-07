const LABELS = {
  active: "Активна",
  expiring: "Истекает",
  expired: "Истекла",
  inactive: "Отключена",
  none: "Без подписки",
};

export function StatusPill({ status }) {
  return (
    <span className={`u-state ${status || "none"}`}>
      <span className="dot" />
      {LABELS[status] || status || "—"}
    </span>
  );
}

export function deriveSubStatus(sub, now = Date.now()) {
  if (!sub) return "none";
  if (!sub.is_active) return "inactive";
  if (sub.expires_at) {
    const exp = new Date(sub.expires_at).getTime();
    const diff = exp - now;
    if (diff < 0) return "expired";
    if (diff < 3 * 24 * 3600 * 1000) return "expiring";
  }
  return "active";
}
