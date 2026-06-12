import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { Donut } from "./finance/charts.jsx";
import { PeriodSelector, FinLoading, FinError, periodLabel, rangeFor } from "./finance/kit.jsx";
import { fmtRub, fmtRubK, fmtNum } from "./finance/format.js";
import { downloadCsv } from "./finance/csv.js";
import {
  PROVIDER_LABELS, PROVIDER_COLORS,
  ORDER_TYPE_LABELS, ORDER_TYPE_COLORS,
  PERIOD_LABELS, PERIOD_COLORS, STATUS_META,
  FUNDING, fundingOf,
} from "./finance/labels.js";

function q(period) {
  const r = rangeFor(period);
  return `?date_from=${encodeURIComponent(r.date_from)}&date_to=${encodeURIComponent(r.date_to)}&limit=500`;
}

const TYPE_FILTERS = [
  { key: "plan_purchase", label: "Покупка" },
  { key: "subscription_renewal", label: "Продление" },
  { key: "device_slots", label: "Слоты" },
  { key: "top_up", label: "Пополнение" },
];
const FUNDING_FILTERS = [
  { key: "cash", label: "Живые деньги" },
  { key: "balance", label: "С баланса" },
  { key: "free", label: "Пробные" },
];

function loadSet(storeKey) {
  try { return new Set(JSON.parse(localStorage.getItem(storeKey) || "[]")); }
  catch { return new Set(); }
}

function ProvCell({ provider }) {
  const color = PROVIDER_COLORS[provider] || "var(--text-muted)";
  const glyph = (PROVIDER_LABELS[provider] || provider).slice(0, 2).toUpperCase();
  return (
    <span className="prov-cell">
      <span className="method-glyph" style={{ background: color }}>{glyph}</span>
      <span style={{ fontWeight: 500 }}>{PROVIDER_LABELS[provider] || provider}</span>
    </span>
  );
}

function groupDonut(rows, keyFn, labels, colors) {
  const m = new Map();
  for (const r of rows) {
    const k = keyFn(r);
    if (k == null) continue;
    m.set(k, (m.get(k) || 0) + Number(r.amount_rub || 0));
  }
  return [...m.entries()]
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => ({ label: labels[k] || String(k), value: v, color: colors[k] || "var(--text-muted)" }));
}

export function FinanceIncomePage() {
  const [period, setPeriod] = useState(() => localStorage.getItem("fin.period") || "30d");
  const [statusFilter, setStatusFilter] = useState("all");
  const [fundSel, setFundSel] = useState(() => loadSet("fin.income.fund"));
  const [typeSel, setTypeSel] = useState(() => loadSet("fin.income.type"));
  const setP = (p) => { setPeriod(p); localStorage.setItem("fin.period", p); };

  const makeToggle = (setter, storeKey) => (key) => setter((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    localStorage.setItem(storeKey, JSON.stringify([...next]));
    return next;
  });
  const toggleFund = makeToggle(setFundSel, "fin.income.fund");
  const toggleType = makeToggle(setTypeSel, "fin.income.type");
  const resetFilters = () => {
    setFundSel(new Set()); setTypeSel(new Set());
    localStorage.removeItem("fin.income.fund"); localStorage.removeItem("fin.income.type");
  };

  const inc = useQuery(() => api.get("/finance/income" + q(period)), { deps: [period] });
  if (inc.loading && !inc.data) return <FinLoading />;
  if (inc.error && !inc.data) return <FinError error={inc.error} />;
  const d = inc.data;

  const allRows = d.transactions || [];
  const filterActive = fundSel.size > 0 || typeSel.size > 0;
  const rows = allRows.filter((r) =>
    (fundSel.size === 0 || fundSel.has(fundingOf(r.provider))) &&
    (typeSel.size === 0 || typeSel.has(r.order_type)) &&
    (statusFilter === "all" || r.status === statusFilter)
  );
  // Revenue = recognised purchases (exclude balance top-ups).
  const revRows = rows.filter((r) => !r.is_top_up);

  const cashSum = revRows.filter((r) => fundingOf(r.provider) === "cash").reduce((a, r) => a + Number(r.amount_rub || 0), 0);
  const balanceSum = revRows.filter((r) => fundingOf(r.provider) === "balance").reduce((a, r) => a + Number(r.amount_rub || 0), 0);
  const trialCount = rows.filter((r) => fundingOf(r.provider) === "free").length;
  const topupSum = rows.filter((r) => r.is_top_up).reduce((a, r) => a + Number(r.amount_rub || 0), 0);

  const byProvider = groupDonut(revRows, (r) => r.provider, PROVIDER_LABELS, PROVIDER_COLORS);
  const byType = groupDonut(revRows, (r) => r.order_type, ORDER_TYPE_LABELS, ORDER_TYPE_COLORS);
  const byPeriod = groupDonut(
    revRows.filter((r) => [1, 3, 6, 12].includes(r.period_months)),
    (r) => r.period_months, PERIOD_LABELS, PERIOD_COLORS,
  );
  const byFunding = groupDonut(revRows, (r) => fundingOf(r.provider), Object.fromEntries(Object.entries(FUNDING).map(([k, v]) => [k, v.label])), Object.fromEntries(Object.entries(FUNDING).map(([k, v]) => [k, v.color])));

  const subtotalNet = revRows.reduce((a, r) => a + Number(r.net_rub ?? r.amount_rub ?? 0), 0);
  const fmtTime = (iso) => iso ? new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
  const sum = (arr) => arr.reduce((a, x) => a + x.value, 0);

  const exportCsv = () => {
    downloadCsv(
      `income-${period}.csv`,
      ["paid_at", "user", "provider", "funding", "order_type", "period_months", "amount_rub", "fee_rub", "net_rub", "status"],
      rows.map((r) => [r.paid_at, r.user, r.provider, fundingOf(r.provider), r.order_type, r.period_months, r.amount_rub, r.fee_rub, r.net_rub, r.status]),
    );
  };

  const kpis = [
    { label: "Живые деньги", value: fmtRub(cashSum), sub: "оплачено через платёжки", color: "var(--ok)", icon: "dollar-sign" },
    { label: "С баланса", value: fmtRub(balanceSum), sub: "списано с баланса (вкл. рефералку)", color: "var(--info)", icon: "wallet" },
    { label: "Пробные", value: fmtNum(trialCount), sub: "бесплатных активаций", color: "var(--text-muted)", icon: "zap" },
    { label: "Пополнения", value: fmtRub(topupSum), sub: "top-up · обязательство, не доход", color: "var(--text-muted)", icon: "credit-card" },
  ];

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Доходы</h1>
          <div className="page-subtitle">Входящие платежи · {periodLabel(period)} · «живые деньги» = реальная оплата, «с баланса» — не новые деньги</div>
        </div>
        <div className="page-head-actions">
          <button className="btn" onClick={exportCsv}><Icon name="download" size={13} /> Экспорт CSV</button>
          <PeriodSelector value={period} onChange={setP} />
        </div>
      </div>

      {d.uncaptured_pct > 0 && (
        <div className="sec">
          <div className="card card-bad" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Icon name="alert-triangle" size={16} style={{ flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600 }}>Комиссия не зафиксирована для {d.uncaptured_pct}% объёма</div>
              <div style={{ fontSize: 12, opacity: 0.85 }}>Часть платежей приходит без поля fee_rub — net по ним оценочный.</div>
            </div>
          </div>
        </div>
      )}

      {/* Filter bar — drives KPIs, donuts and the table below */}
      <div className="sec">
        <div className="card">
          <div className="fin-filterbar">
            <span className="ff-label">Источник:</span>
            {FUNDING_FILTERS.map((f) => (
              <button key={f.key} type="button" className="ff-chip" data-on={fundSel.has(f.key) || undefined} onClick={() => toggleFund(f.key)}>{f.label}</button>
            ))}
            <span className="ff-sep" />
            <span className="ff-label">Тип:</span>
            {TYPE_FILTERS.map((t) => (
              <button key={t.key} type="button" className="ff-chip" data-on={typeSel.has(t.key) || undefined} onClick={() => toggleType(t.key)}>{t.label}</button>
            ))}
            <div className="sec-spacer" />
            <span className="text-xs muted">{filterActive ? `показано ${rows.length} из ${allRows.length}` : `все ${allRows.length} операций`}</span>
            {filterActive && <button className="btn btn-ghost btn-xs" onClick={resetFilters}>Сбросить</button>}
          </div>
          <div className="card-body" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 0, padding: 0 }}>
            {kpis.map((k, i) => (
              <div key={k.label} className="kpi-cell" style={{ borderRight: i < 3 ? "1px solid var(--border)" : "none" }}>
                <div className="kpi-label"><Icon name={k.icon} size={12} /> <span>{k.label}</span></div>
                <div className="kpi-value tnum" style={{ fontSize: 24, color: k.color }}>{k.value}</div>
                <div className="text-xs muted mt-1">{k.sub}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="sec split-3">
        <div className="card">
          <div className="card-head"><Icon name="dollar-sign" size={14} /><div className="sec-title">По источнику</div></div>
          <div className="card-body"><Donut data={byFunding} size={120} centerValue={fmtRubK(sum(byFunding))} centerLabel="выручка" /></div>
        </div>
        <div className="card">
          <div className="card-head"><Icon name="credit-card" size={14} /><div className="sec-title">По провайдерам</div></div>
          <div className="card-body"><Donut data={byProvider} size={120} centerValue={fmtRubK(sum(byProvider))} centerLabel="всего" /></div>
        </div>
        <div className="card">
          <div className="card-head"><Icon name="calendar" size={14} /><div className="sec-title">По длине периода</div></div>
          <div className="card-body"><Donut data={byPeriod} size={120} centerValue={fmtRubK(sum(byPeriod))} centerLabel="выручка" /></div>
        </div>
      </div>

      <div className="sec">
        <div className="card">
          <div className="card-head">
            <Icon name="list" size={14} />
            <div className="sec-title">Транзакции</div>
            <span className="pill muted">{rows.length}</span>
            <div className="sec-spacer" />
            <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ minWidth: 130 }}>
              <option value="all">Все статусы</option>
              {Object.keys(STATUS_META).map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Оплачен</th><th>Пользователь</th><th>Провайдер</th><th>Источник</th><th>Тип</th>
                  <th style={{ textAlign: "right" }}>Gross</th>
                  <th style={{ textAlign: "right" }}>Комиссия</th>
                  <th style={{ textAlign: "right" }}>Net</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const f = fundingOf(r.provider);
                  return (
                    <tr key={r.id} data-muted={r.is_top_up || undefined}>
                      <td className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>{fmtTime(r.paid_at)}</td>
                      <td style={{ fontWeight: 500 }}>{r.user || "—"}</td>
                      <td><ProvCell provider={r.provider} /></td>
                      <td><span className="chip" style={{ background: "transparent", color: FUNDING[f].color, border: `1px solid ${FUNDING[f].color}` }}>{FUNDING[f].label}</span></td>
                      <td>
                        {r.is_top_up
                          ? <span className="chip chip-muted">пополнение</span>
                          : <span style={{ fontSize: 12.5 }}>{ORDER_TYPE_LABELS[r.order_type] || r.order_type}{r.period_months ? <span className="muted"> · {r.period_months}м</span> : ""}</span>}
                      </td>
                      <td className="tbl-num" style={{ color: r.is_top_up ? "var(--text-muted)" : "var(--text)" }}>{fmtRub(r.amount_rub)}</td>
                      <td className="tbl-num" style={{ color: r.fee_rub == null ? "var(--text-faint)" : "var(--warn)" }}>{r.fee_rub == null ? "— н/д" : fmtRub(r.fee_rub)}</td>
                      <td className="tbl-num" style={{ color: r.net_rub == null ? "var(--text-faint)" : (r.is_top_up ? "var(--text-muted)" : "var(--ok)"), fontWeight: 500 }}>{r.net_rub == null ? "≈" + fmtRub(r.amount_rub) : fmtRub(r.net_rub)}</td>
                      <td><span className={`pill ${(STATUS_META[r.status] || STATUS_META.completed).cls}`}>{r.status}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div style={{ padding: "10px 14px", borderTop: "1px solid var(--border)", display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" }}>
            <div className="footnote" style={{ fontWeight: 500, color: "var(--text)" }}>
              Выручка по выборке: <span style={{ color: "var(--ok)" }}>живые {fmtRub(cashSum)}</span> · с баланса {fmtRub(balanceSum)} · net {fmtRub(subtotalNet)}
            </div>
            <div className="sec-spacer" />
            <div className="footnote"><span className="fn-mark">*</span> Фильтр включающий: кликни источник/тип, чтобы оставить только их. Колёса и KPI пересчитываются под фильтр.</div>
          </div>
        </div>
      </div>
    </div>
  );
}
