import { Icon } from "./Icon.jsx";

/**
 * Telegram-style delivery indicator.
 * status:
 *  - "pending"   — clock icon (queued / scheduled / sending)
 *  - "sent"      — single check
 *  - "delivered" — double check
 *  - "read"      — double check, accent-colored
 */
export function TgTicks({ status = "delivered", size = 11 }) {
  if (status === "pending") {
    return (
      <span className="tg-ticks" title="Отправляется">
        <Icon name="clock" size={size} />
      </span>
    );
  }
  if (status === "sent") {
    return (
      <span className="tg-ticks" title="Отправлено">
        <Icon name="check" size={size} />
      </span>
    );
  }
  const tone = status === "read" ? "var(--accent)" : "currentColor";
  const title = status === "read" ? "Прочитано" : "Доставлено";
  return (
    <span className="tg-ticks tg-ticks-double" title={title} style={{ color: tone }}>
      <Icon name="check" size={size} />
      <Icon name="check" size={size} />
    </span>
  );
}
