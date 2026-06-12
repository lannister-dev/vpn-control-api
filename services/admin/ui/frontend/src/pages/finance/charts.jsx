import { useState } from "react";
import { fmtRub, fmtRubK } from "./format.js";

export function ComboChart({ data, height = 260 }) {
  const [hover, setHover] = useState(null);
  const padL = 56, padR = 16, padT = 14, padB = 26;
  const w = 1000;
  const innerW = w - padL - padR;
  const innerH = height - padT - padB;
  const maxBar = Math.max(1, ...data.map((d) => Math.max(d.income, d.expense)));
  const maxY = Math.ceil(maxBar / 20000) * 20000 || 20000;
  const x = (i) => padL + (i + 0.5) * (innerW / data.length);
  const yBar = (v) => padT + innerH - (v / maxY) * innerH;
  const groupW = innerW / data.length;
  const bw = Math.min(9, groupW * 0.32);

  const profitPts = data.map((d, i) => `${x(i)},${yBar(d.profit)}`).join(" ");
  const profitArea = `${profitPts} ${x(data.length - 1)},${padT + innerH} ${x(0)},${padT + innerH}`;
  const ticks = 4;

  return (
    <div style={{ position: "relative", width: "100%" }}>
      <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} preserveAspectRatio="none" onMouseLeave={() => setHover(null)}>
        <defs>
          <linearGradient id="profitGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--ok)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--ok)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {Array.from({ length: ticks + 1 }).map((_, t) => {
          const v = (maxY / ticks) * t;
          const yy = yBar(v);
          return (
            <g key={t}>
              <line x1={padL} y1={yy} x2={w - padR} y2={yy} stroke="var(--border)" strokeWidth="1" opacity={t === 0 ? 1 : 0.45} />
              <text x={padL - 8} y={yy + 3} textAnchor="end" fontSize="10" fontFamily="var(--font-mono)" fill="var(--text-faint)">
                {v === 0 ? "0" : `${(v / 1000).toFixed(0)}k`}
              </text>
            </g>
          );
        })}
        {data.map((d, i) => {
          const cx = x(i);
          const active = hover === i;
          return (
            <g key={i}>
              <rect x={cx - bw - 1.5} y={yBar(d.income)} width={bw} height={padT + innerH - yBar(d.income)} fill="var(--accent)" opacity={active ? 1 : 0.9} rx="2" />
              <rect x={cx + 1.5} y={yBar(d.expense)} width={bw} height={padT + innerH - yBar(d.expense)} fill="var(--spend)" opacity={active ? 0.95 : 0.7} rx="2" />
              {i % 5 === 0 && (
                <text x={cx} y={height - 8} textAnchor="middle" fontSize="9.5" fontFamily="var(--font-mono)" fill="var(--text-faint)">{d.label}</text>
              )}
              <rect x={cx - groupW / 2} y={padT} width={groupW} height={innerH} fill="transparent" onMouseEnter={() => setHover(i)} style={{ cursor: "crosshair" }} />
              {active && <line x1={cx} y1={padT} x2={cx} y2={padT + innerH} stroke="var(--border-strong)" strokeWidth="1" strokeDasharray="2 2" />}
            </g>
          );
        })}
        <polygon points={profitArea} fill="url(#profitGrad)" />
        <polyline points={profitPts} fill="none" stroke="var(--ok)" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" />
        {data.map((d, i) => hover === i && (
          <circle key={i} cx={x(i)} cy={yBar(d.profit)} r="3.5" fill="var(--ok)" stroke="var(--surface)" strokeWidth="1.5" />
        ))}
      </svg>
      {hover != null && (
        <div className="chart-tip" style={{ left: `${(x(hover) / w) * 100}%`, top: 6, transform: x(hover) > w * 0.6 ? "translateX(-104%)" : "translateX(4%)" }}>
          <div className="tip-date">{data[hover].label}</div>
          <div className="tip-row"><span className="tip-l"><span className="lg-swatch" style={{ background: "var(--accent)" }} />Доход</span><span className="tip-v">{fmtRub(data[hover].income)}</span></div>
          <div className="tip-row"><span className="tip-l"><span className="lg-swatch" style={{ background: "var(--spend)" }} />Расход</span><span className="tip-v">{fmtRub(data[hover].expense)}</span></div>
          <div className="tip-row"><span className="tip-l"><span className="lg-line" style={{ background: "var(--ok)" }} />Прибыль</span><span className="tip-v" style={{ color: "var(--ok)" }}>{fmtRub(data[hover].profit)}</span></div>
        </div>
      )}
    </div>
  );
}

export function Donut({ data, size = 132, thickness = 18, centerLabel, centerValue }) {
  const total = data.reduce((a, d) => a + d.value, 0);
  const r = (size - thickness) / 2;
  const cx = size / 2, cy = size / 2;
  const circ = 2 * Math.PI * r;
  let offset = 0;
  const segs = data.filter((d) => d.value > 0).map((d) => {
    const frac = total ? d.value / total : 0;
    const seg = { ...d, frac, dash: frac * circ, offset };
    offset += frac * circ;
    return seg;
  });
  return (
    <div className="donut-wrap">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--surface-2)" strokeWidth={thickness} />
        {segs.map((s, i) => (
          <circle key={i} cx={cx} cy={cy} r={r} fill="none" stroke={s.color} strokeWidth={thickness}
            strokeDasharray={`${s.dash} ${circ - s.dash}`} strokeDashoffset={-s.offset}
            transform={`rotate(-90 ${cx} ${cy})`} strokeLinecap="butt" />
        ))}
        {centerValue && (
          <>
            <text x={cx} y={cy - 1} textAnchor="middle" fontSize="17" fontWeight="600" fontFamily="var(--font-mono)" fill="var(--text)">{centerValue}</text>
            <text x={cx} y={cy + 15} textAnchor="middle" fontSize="9.5" fill="var(--text-muted)">{centerLabel}</text>
          </>
        )}
      </svg>
      <div className="donut-legend">
        {data.map((d, i) => {
          const pct = total ? (d.value / total) * 100 : 0;
          return (
            <div className="dl-row" key={i}>
              <span className="dl-dot" style={{ background: d.color }} />
              <span className="dl-label">{d.label}</span>
              <span className="dl-val">{fmtRubK(d.value)}</span>
              <span className="dl-pct">{pct.toFixed(0)}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function Waterfall({ data }) {
  const maxV = Math.max(...data.map((d) => Math.abs(d.value)), data[0]?.value || 1) || 1;
  let running = 0;
  return (
    <div>
      {data.map((d, i) => {
        let left, width, color;
        if (d.type === "total" || d.type === "result") {
          left = 0; width = (d.value / maxV) * 100;
          color = d.type === "result" ? "var(--ok)" : "var(--accent)";
          running = d.value;
        } else {
          const start = running;
          running = running + d.value;
          const lo = Math.min(start, running);
          left = (lo / maxV) * 100;
          width = (Math.abs(d.value) / maxV) * 100;
          color = "var(--spend)";
        }
        const safeLeft = Math.max(0, Math.min(100, left));
        const safeWidth = Math.max(0.6, Math.min(width, 100 - safeLeft));
        return (
          <div className="wf-row" key={i}>
            <span className="wf-label" style={{ fontWeight: d.type === "total" || d.type === "result" ? 600 : 500, color: d.type === "result" ? "var(--ok)" : d.type === "total" ? "var(--text)" : "var(--text-secondary)" }}>
              {d.label}
            </span>
            <div className="wf-track">
              <div className="wf-bar" style={{ left: `${safeLeft}%`, width: `${safeWidth}%`, background: color, opacity: d.type === "neg" ? 0.7 : 1 }} />
            </div>
            <span className="wf-val" style={{ color: d.type === "result" ? "var(--ok)" : d.type === "neg" ? "var(--spend)" : "var(--text)" }}>
              {fmtRub(d.value)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function HealthRing({ value, max = 5, tone, unit, sub }) {
  const pct = Math.min(1, value / max);
  const ringLen = 2 * Math.PI * 28;
  const dash = ringLen * pct;
  return (
    <div className="health-ring">
      <svg className="ring-svg" viewBox="0 0 64 64">
        <circle className="ring-bg" cx="32" cy="32" r="28" fill="none" strokeWidth="5" />
        <circle className={`ring-fg ${tone}`} cx="32" cy="32" r="28" fill="none" strokeWidth="5"
          strokeDasharray={`${dash} ${ringLen}`} transform="rotate(-90 32 32)" strokeLinecap="round" />
      </svg>
      <div className="health-main">
        <div className="kpi-value tnum">{value.toFixed(1)}{unit && <span className="kpi-unit">{unit}</span>}</div>
        {sub && <div className="health-sub">{sub}</div>}
      </div>
    </div>
  );
}

export function StackedMrr({ data, height = 220 }) {
  const [hover, setHover] = useState(null);
  const padL = 52, padR = 14, padT = 12, padB = 24;
  const w = 1000;
  const innerW = w - padL - padR, innerH = height - padT - padB;
  const maxY = Math.ceil(Math.max(...data.map((d) => d.base)) / 200000) * 200000 || 200000;
  const groupW = innerW / data.length;
  const bw = Math.min(34, groupW * 0.6);
  const y = (v) => padT + innerH - (v / maxY) * innerH;
  const x = (i) => padL + (i + 0.5) * groupW;
  return (
    <div style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} preserveAspectRatio="none" onMouseLeave={() => setHover(null)}>
        {Array.from({ length: 5 }).map((_, t) => {
          const v = (maxY / 4) * t; const yy = y(v);
          return <g key={t}>
            <line x1={padL} y1={yy} x2={w - padR} y2={yy} stroke="var(--border)" />
            <text x={padL - 8} y={yy + 3} textAnchor="end" fontSize="10" fontFamily="var(--font-mono)" fill="var(--text-faint)">{(v / 1000).toFixed(0)}k</text>
          </g>;
        })}
        {data.map((d, i) => {
          const cx = x(i);
          const baseY = y(d.base);
          const newH = (d.neu / maxY) * innerH;
          const expH = (d.exp / maxY) * innerH;
          return (
            <g key={i}>
              <rect x={cx - bw / 2} y={baseY} width={bw} height={padT + innerH - baseY} fill="var(--accent)" opacity={hover === i ? 1 : 0.85} rx="1.5" />
              <rect x={cx - bw / 2} y={baseY - newH} width={bw} height={newH} fill="var(--ok)" opacity={hover === i ? 1 : 0.9} />
              <rect x={cx - bw / 2} y={baseY - newH - expH} width={bw} height={expH} fill="var(--info)" opacity={hover === i ? 1 : 0.9} />
              <text x={cx} y={height - 7} textAnchor="middle" fontSize="9.5" fontFamily="var(--font-mono)" fill="var(--text-faint)">{d.month}</text>
              <rect x={cx - groupW / 2} y={padT} width={groupW} height={innerH} fill="transparent" onMouseEnter={() => setHover(i)} />
            </g>
          );
        })}
      </svg>
      {hover != null && (
        <div className="chart-tip" style={{ left: `${(x(hover) / w) * 100}%`, top: 4, transform: x(hover) > w * 0.6 ? "translateX(-104%)" : "translateX(4%)" }}>
          <div className="tip-date">{data[hover].month} · MRR {fmtRubK(data[hover].base)}</div>
          <div className="tip-row"><span className="tip-l"><span className="lg-swatch" style={{ background: "var(--ok)" }} />New</span><span className="tip-v">{fmtRub(data[hover].neu)}</span></div>
          <div className="tip-row"><span className="tip-l"><span className="lg-swatch" style={{ background: "var(--info)" }} />Expansion</span><span className="tip-v">{fmtRub(data[hover].exp)}</span></div>
          <div className="tip-row"><span className="tip-l"><span className="lg-swatch" style={{ background: "var(--bad)" }} />Churned</span><span className="tip-v" style={{ color: "var(--bad)" }}>−{fmtRub(data[hover].chu)}</span></div>
        </div>
      )}
    </div>
  );
}
