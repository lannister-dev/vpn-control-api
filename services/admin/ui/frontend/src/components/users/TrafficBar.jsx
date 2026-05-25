function fmtBytes(b) {
  if (b == null) return null;
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, n = Number(b);
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return n.toFixed(n >= 100 || i === 0 ? 0 : 1) + " " + u[i];
}

export function TrafficBar({ used, cap, size = "md" }) {
  if (cap == null || cap === 0) {
    return <span className="muted small">—</span>;
  }
  const pct = Math.min(1, (used || 0) / cap);
  const tone = pct >= 0.95 ? "bad" : pct >= 0.8 ? "warn" : "";
  return (
    <div className={`u-traffic ${size === "lg" ? "lg" : ""}`}>
      <div className="u-traffic-top">
        <span>
          {fmtBytes(used)}
          <span className="u-traffic-sep"> / </span>
          {fmtBytes(cap)}
        </span>
        <span className="u-traffic-pct">{Math.round(pct * 100)}%</span>
      </div>
      <div className="u-traffic-track">
        <div className={`u-traffic-fill ${tone}`} style={{ width: pct * 100 + "%" }} />
      </div>
    </div>
  );
}
