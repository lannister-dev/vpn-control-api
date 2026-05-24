export function daysLeft(expiresAt, now = Date.now()) {
  if (!expiresAt) return null;
  const t = new Date(expiresAt).getTime();
  return Math.ceil((t - now) / (24 * 3600 * 1000));
}

function declension(days) {
  const abs = Math.abs(days);
  const last2 = abs % 100;
  if (last2 >= 11 && last2 <= 14) return "дней";
  const last = abs % 10;
  if (last === 1) return "день";
  if (last >= 2 && last <= 4) return "дня";
  return "дней";
}

export function DaysCountdown({ days }) {
  if (days == null) return <span className="muted small">—</span>;
  if (days < 0) {
    return (
      <span className="u-days bad">
        <span className="u-days-num">истекла</span>
      </span>
    );
  }
  const tone = days < 3 ? "bad" : days < 14 ? "warn" : "";
  return (
    <span className={`u-days ${tone}`}>
      <span className="u-days-num">{days}</span>
      <span className="u-days-lbl">{declension(days)}</span>
    </span>
  );
}
