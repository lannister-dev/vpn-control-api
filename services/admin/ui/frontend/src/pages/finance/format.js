const RUB = "₽";

export function fmtRub(n, { sign = false } = {}) {
  if (n == null) return "—";
  const s = Math.round(Math.abs(n)).toLocaleString("ru-RU");
  const pfx = n < 0 ? "−" : sign && n > 0 ? "+" : "";
  return `${pfx}${RUB}${s}`;
}

export function fmtRubK(n) {
  if (n == null) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e6) return `${RUB}${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${RUB}${(n / 1e3).toFixed(0)}k`;
  return `${RUB}${Math.round(n)}`;
}

export function fmtNum(n) {
  return n == null ? "—" : Math.round(n).toLocaleString("ru-RU");
}

export function fmtPct(n, d = 1) {
  return n == null ? "—" : `${n.toFixed(d)}%`;
}

export function fmtCur(n, cur) {
  const sym = { RUB: "₽", EUR: "€", USD: "$", GBP: "£" }[cur] || "";
  if (cur === "RUB") return `₽${Math.round(n).toLocaleString("ru-RU")}`;
  return `${sym}${Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function fmtDelta(pct) {
  if (pct == null) return null;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

export function dueProximity(dateStr, now = Date.now()) {
  if (!dateStr) return { cls: "chip-muted", days: null };
  const days = Math.ceil((new Date(dateStr).getTime() - now) / 86400000);
  let cls;
  if (days < 0) cls = "chip-over";
  else if (days <= 3) cls = "chip-bad";
  else if (days <= 7) cls = "chip-orange";
  else if (days <= 14) cls = "chip-warn";
  else if (days <= 30) cls = "chip-lime";
  else cls = "chip-ok";
  return { cls, days };
}
