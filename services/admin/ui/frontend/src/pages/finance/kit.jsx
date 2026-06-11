import { useState } from "react";
import { Icon } from "../../components/Icon.jsx";
import { Spark } from "../../components/Spark.jsx";

export const PERIODS = [
  { id: "today", label: "Сегодня" },
  { id: "7d", label: "7 дней" },
  { id: "30d", label: "30 дней" },
  { id: "quarter", label: "Квартал" },
  { id: "year", label: "Год" },
];

export function periodLabel(id) {
  return PERIODS.find((p) => p.id === id)?.label || "30 дней";
}

export function rangeFor(period) {
  const to = new Date();
  const from = new Date(to);
  if (period === "today") from.setHours(0, 0, 0, 0);
  else if (period === "7d") from.setDate(to.getDate() - 7);
  else if (period === "quarter") from.setMonth(to.getMonth() - 3);
  else if (period === "year") from.setFullYear(to.getFullYear() - 1);
  else from.setDate(to.getDate() - 30);
  return { date_from: from.toISOString(), date_to: to.toISOString() };
}

export function KpiCell({ label, value, unit, icon, delta, deltaSub, deltaTone, spark, sparkColor, primary, planned }) {
  return (
    <div className={"kpi-cell" + (primary ? " primary" : "")}>
      {planned && <span className="kpi-planned">план</span>}
      <div className="kpi-label"><Icon name={icon} size={12} style={{ flexShrink: 0 }} /> <span>{label}</span></div>
      <div className="kpi-value-row">
        <div className="kpi-value tnum">{value}{unit && <span className="kpi-unit">{unit}</span>}</div>
        {spark && <div className="kpi-spark"><Spark data={spark} color={sparkColor} w={primary ? 70 : 54} h={primary ? 26 : 20} /></div>}
      </div>
      {delta && (
        <div className={`kpi-delta ${deltaTone || ""}`}>
          <Icon name={deltaTone === "up" ? "trending-up" : deltaTone === "down" ? "trending-down" : "trending-flat"} size={12} />
          <span>{delta}</span>
          {deltaSub && <span className="muted" style={{ marginLeft: 4 }}>{deltaSub}</span>}
        </div>
      )}
    </div>
  );
}

export function PeriodSelector({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const cur = PERIODS.find((p) => p.id === value) || PERIODS[2];
  return (
    <div style={{ position: "relative" }}>
      <button className="btn" onClick={() => setOpen((v) => !v)}>
        <Icon name="clock" size={13} /> {cur.label} <Icon name="chevron-down" size={12} />
      </button>
      {open && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 50 }} onClick={() => setOpen(false)} />
          <div style={{ position: "absolute", top: "100%", right: 0, marginTop: 4, minWidth: 150, zIndex: 51, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, boxShadow: "var(--shadow-lg)", padding: 4 }}>
            {PERIODS.map((o) => (
              <button key={o.id} onClick={() => { onChange(o.id); setOpen(false); }}
                style={{ display: "block", width: "100%", textAlign: "left", padding: "7px 10px", border: 0, background: value === o.id ? "var(--accent-soft)" : "transparent", cursor: "pointer", borderRadius: 5, color: "var(--text)", fontSize: 13 }}>
                {o.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export function FinLoading() {
  return <div className="page"><div style={{ padding: 48, color: "var(--text-muted)" }}>Загрузка…</div></div>;
}

export function FinError({ error }) {
  return (
    <div className="page">
      <div className="card card-bad" style={{ marginTop: 24 }}>
        Не удалось загрузить данные: {error?.message || "ошибка"}
      </div>
    </div>
  );
}
