import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { Donut } from "./finance/charts.jsx";
import { PeriodSelector, FinLoading, FinError, periodLabel, rangeFor } from "./finance/kit.jsx";
import { fmtRub, fmtRubK } from "./finance/format.js";
import { downloadCsv } from "./finance/csv.js";
import {
  PROVIDER_LABELS, PROVIDER_COLORS,
  ORDER_TYPE_LABELS, ORDER_TYPE_COLORS,
  PERIOD_LABELS, PERIOD_COLORS, STATUS_META,
} from "./finance/labels.js";

function q(period) {
  const r = rangeFor(period);
  return `?date_from=${encodeURIComponent(r.date_from)}&date_to=${encodeURIComponent(r.date_to)}&limit=200`;
}

const TYPE_FILTERS = [
  { key: "plan_purchase", label: "Покупка" },
  { key: "subscription_renewal", label: "Продление" },
  { key: "device_slots", label: "Слоты" },
  { key: "top_up", label: "Пополнение" },
];
const PROVIDER_FILTERS = [
  { key: "platega", label: "Platega" },
  { key: "crypto", label: "Crypto" },
  { key: "stars", label: "Stars" },
  { key: "freekassa", label: "FreeKassa" },
  { key: "balance", label: "С баланса" },
  { key: "free", label: "Пробный" },
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

export function FinanceIncomePage() {
  const [period, setPeriod] = useState(() => localStorage.getItem("fin.period") || "30d");
  const [statusFilter, setStatusFilter] = useState("all");
  const [exTypes, setExTypes] = useState(() => loadSet("fin.income.exType"));
  const [exProvs, setExProvs] = useState(() => loadSet("fin.income.exProv"));
  const setP = (p) => { setPeriod(p); localStorage.setItem("fin.period", p); };

  const makeToggle = (setter, storeKey) => (key) => setter((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    localStorage.setItem(storeKey, JSON.stringify([...next]));
    return next;
  });
  const toggleType = makeToggle(setExTypes, "fin.income.exType");
  const toggleProv = makeToggle(setExProvs, "fin.income.exProv");
  const resetFilters = () => {
    setExTypes(new Set()); setExProvs(new Set());
    localStorage.removeItem("fin.income.exType"); localStorage.removeItem("fin.income.exProv");
  };

  const inc = useQuery(() => api.get("/finance/income" + q(period)), { deps: [period] });
  if (inc.loading && !inc.data) return <FinLoading />;
  if (inc.error && !inc.data) return <FinError error={inc.error} />;
  const d = inc.data;

  const map = (arr, labels, colors) => (arr || []).map((x) => ({
    label: labels[x.key] || x.key, value: x.value, color: colors[x.key] || "var(--text-muted)",
  }));
  const byProvider = map(d.by_provider, PROVIDER_LABELS, PROVIDER_COLORS);
  const byType = map(d.by_order_type, ORDER_TYPE_LABELS, ORDER_TYPE_COLORS);
  const byPeriod = map(d.by_period, PERIOD_LABELS, PERIOD_COLORS);

  const allRows = d.transactions || [];
  const rows = allRows.filter((r) =>
    !exTypes.has(r.order_type) &&
    !exProvs.has(r.provider) &&
    (statusFilter === "all" || r.status === statusFilter)
  );
  const excludedCount = exTypes.size + exProvs.size;
  const subtotalGross = rows.reduce((a, r) => a + Number(r.amount_rub || 0), 0);
  const subtotalNet = rows.reduce((a, r) => a + Number(r.net_rub ?? r.amount_rub ?? 0), 0);
  const fmtTime = (iso) => iso ? new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
  const sum = (arr) => arr.reduce((a, x) => a + x.value, 0);

  const exportCsv = () => {
    downloadCsv(
      `income-${period}.csv`,
      ["paid_at", "user", "provider", "order_type", "period_months", "amount_rub", "fee_rub", "net_rub", "status"],
      rows.map((r) => [r.paid_at, r.user, r.provider, r.order_type, r.period_months, r.amount_rub, r.fee_rub, r.net_rub, r.status]),
    );
  };

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Доходы</h1>
          <div className="page-subtitle">Входящие платежи · {periodLabel(period)} · источник: PaymentOrder API</div>
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
              <div style={{ fontSize: 12, opacity: 0.85 }}>Часть платежей приходит без поля fee_rub — net по ним оценочный, выручка может быть занижена.</div>
            </div>
          </div>
        </div>
      )}

      <div className="sec split-3">
        <div className="card">
          <div className="card-head"><Icon name="credit-card" size={14} /><div className="sec-title">По провайдерам</div></div>
          <div className="card-body"><Donut data={byProvider} size={120} centerValue={fmtRubK(sum(byProvider))} centerLabel="всего" /></div>
        </div>
        <div className="card">
          <div className="card-head"><Icon name="layout-dashboard" size={14} /><div className="sec-title">По типу заказа</div></div>
          <div className="card-body"><Donut data={byType} size={120} centerValue={fmtRubK(sum(byType))} centerLabel="выручка" /></div>
        </div>
        <div className="card">
          <div className="card-head"><Icon name="calendar" size={14} /><div className="sec-title">По длине периода</div></div>
          <div className="card-body"><Donut data={byPeriod} size={120} centerValue={fmtRubK(sum(byPeriod))} centerLabel="выручка" /></div>
        </div>
      </div>

      <div className="sec">
        <div className="card" style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 14px", background: "var(--surface-2)" }}>
          <Icon name="wallet" size={15} className="muted" />
          <div style={{ flex: 1, fontSize: 12.5 }}>
            <span style={{ fontWeight: 500 }}>Пополнения баланса (top_up): {fmtRub(d.topup_volume)}</span>
            <span className="muted"> — предоплаченный баланс (обязательство), не выручка. Исключено из gross. Признаётся при списании.</span>
          </div>
          <span className="pill muted">liability</span>
        </div>
      </div>

      <div className="sec">
        <div className="card">
          <div className="card-head">
            <Icon name="list" size={14} />
            <div className="sec-title">Транзакции</div>
            <span className="pill muted">{rows.length}{excludedCount ? ` из ${allRows.length}` : ""}</span>
            <div className="sec-spacer" />
            <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ minWidth: 130 }}>
              <option value="all">Все статусы</option>
              {Object.keys(STATUS_META).map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="fin-filterbar">
            <span className="ff-label">Исключить:</span>
            {TYPE_FILTERS.map((t) => (
              <button key={t.key} type="button" className="ff-chip" data-off={exTypes.has(t.key) || undefined} onClick={() => toggleType(t.key)}>{t.label}</button>
            ))}
            <span className="ff-sep" />
            {PROVIDER_FILTERS.map((p) => (
              <button key={p.key} type="button" className="ff-chip" data-off={exProvs.has(p.key) || undefined} onClick={() => toggleProv(p.key)}>{p.label}</button>
            ))}
            {excludedCount > 0 && <button className="btn btn-ghost btn-xs" onClick={resetFilters}>Сбросить</button>}
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Оплачен</th><th>Пользователь</th><th>Провайдер</th><th>Тип</th>
                  <th style={{ textAlign: "right" }}>Gross</th>
                  <th style={{ textAlign: "right" }}>Комиссия</th>
                  <th style={{ textAlign: "right" }}>Net</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} data-muted={r.is_top_up || undefined}>
                    <td className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>{fmtTime(r.paid_at)}</td>
                    <td style={{ fontWeight: 500 }}>{r.user || "—"}</td>
                    <td><ProvCell provider={r.provider} /></td>
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
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ padding: "10px 14px", borderTop: "1px solid var(--border)", display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" }}>
            <div className="footnote" style={{ fontWeight: 500, color: "var(--text)" }}>
              Выборка: {rows.length} · gross {fmtRub(subtotalGross)} · net {fmtRub(subtotalNet)}
            </div>
            <div className="sec-spacer" />
            <div className="footnote"><span className="fn-mark">*</span> Клик по виду исключает его из выборки и подытога. Диаграммы выше — за весь период, без учёта фильтра.</div>
            <div className="footnote"><span className="fn-mark">†</span> «— н/д» — провайдер не вернул fee_rub; net оценочный.</div>
          </div>
        </div>
      </div>
    </div>
  );
}
