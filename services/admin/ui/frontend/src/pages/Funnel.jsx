import { useState } from "react";

import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";

const PERIODS = [
  { v: 7, l: "7 дней" },
  { v: 30, l: "30 дней" },
  { v: 90, l: "90 дней" },
];

function pct(part, whole) {
  if (!whole) return "—";
  return `${Math.round((part / whole) * 100)}%`;
}

export function FunnelPage() {
  const [days, setDays] = useState(30);
  const q = useQuery(
    () => api.get(`/support/funnel?days=${days}`).catch(() => null),
    { interval: 0, deps: [days] },
  );
  const d = q.data || {};

  const stages = [
    { key: "registered", label: "Регистрации", value: d.registered, sub: null },
    {
      key: "trial_started",
      label: "Активировали триал",
      value: d.trial_started,
      sub: null,
    },
    {
      key: "connected",
      label: "Подключились",
      value: d.connected,
      sub: pct(d.connected, d.trial_started) + " от триалов",
    },
    {
      key: "purchased",
      label: "Оплатили",
      value: d.purchased,
      sub: pct(d.purchased, d.trial_started) + " от триалов",
    },
    {
      key: "renewed",
      label: "Продлили",
      value: d.renewed,
      sub: "повторные оплаты",
    },
  ];

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Воронка</h1>
          <div className="page-subtitle">
            Активация и монетизация за период. Главная метрика — подключились (первое
            подключение).
          </div>
        </div>
        <div className="page-head-actions">
          <div className="seg" style={{ minWidth: 220 }}>
            {PERIODS.map((p) => (
              <button
                key={p.v}
                data-active={days === p.v || undefined}
                onClick={() => setDays(p.v)}
              >
                {p.l}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          gap: 12,
        }}
      >
        {stages.map((s) => (
          <div key={s.key} className="card" style={{ padding: 16 }}>
            <div className="muted" style={{ fontSize: 12 }}>{s.label}</div>
            <div style={{ fontSize: 28, fontWeight: 600, marginTop: 4 }}>
              {s.value ?? "—"}
            </div>
            {s.sub && (
              <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>{s.sub}</div>
            )}
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 12, padding: 16 }}>
        <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
          Где течёт
        </div>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <div>
            <div className="muted" style={{ fontSize: 11 }}>Активация (триал→подключение)</div>
            <div style={{ fontSize: 20, fontWeight: 600 }}>
              {pct(d.connected, d.trial_started)}
            </div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: 11 }}>Конверсия (триал→оплата)</div>
            <div style={{ fontSize: 20, fontWeight: 600 }}>
              {pct(d.purchased, d.trial_started)}
            </div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: 11 }}>Оплата от подключившихся</div>
            <div style={{ fontSize: 20, fontWeight: 600 }}>
              {pct(d.purchased, d.connected)}
            </div>
          </div>
        </div>
        <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>
          Низкая активация → проблема в онбординге/доведении до подключения. Низкая
          конверсия при высокой активации → проблема в цене/оффере.
        </div>
      </div>
    </div>
  );
}
