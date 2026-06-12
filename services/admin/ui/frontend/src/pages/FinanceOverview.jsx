import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { ComboChart, Donut, Waterfall } from "./finance/charts.jsx";
import { KpiCell, PeriodSelector, FinLoading, FinError, periodLabel, rangeFor } from "./finance/kit.jsx";
import { fmtRub, fmtRubK, fmtPct, fmtDelta } from "./finance/format.js";
import { PROVIDER_LABELS, PROVIDER_COLORS, waterfallLabel } from "./finance/labels.js";

function q(period) {
  const r = rangeFor(period);
  return `?date_from=${encodeURIComponent(r.date_from)}&date_to=${encodeURIComponent(r.date_to)}`;
}

export function FinanceOverviewPage() {
  const [period, setPeriod] = useState(() => localStorage.getItem("fin.period") || "30d");
  const setP = (p) => { setPeriod(p); localStorage.setItem("fin.period", p); };

  const ov = useQuery(() => api.get("/finance/overview" + q(period)), { deps: [period] });
  const inc = useQuery(() => api.get("/finance/income" + q(period) + "&limit=1"), { deps: [period] });

  if (ov.loading && !ov.data) return <FinLoading />;
  if (ov.error && !ov.data) return <FinError error={ov.error} />;

  const k = ov.data;
  const daily = (k.daily || []).map((d) => ({
    ...d,
    label: new Date(d.date).toLocaleDateString("ru-RU", { day: "2-digit", month: "short" }),
  }));
  const waterfall = (k.waterfall || []).map((w) => ({ ...w, label: waterfallLabel(w.key) }));
  const spark = (key) => daily.map((d) => d[key]);

  const byProvider = ((inc.data && inc.data.by_provider) || []).map((d) => ({
    label: PROVIDER_LABELS[d.key] || d.key,
    value: d.value,
    color: PROVIDER_COLORS[d.key] || "var(--text-muted)",
  }));

  const cell = (kpi, fmt, sub) => ({
    value: fmt(kpi.value),
    delta: fmtDelta(kpi.delta_pct),
    deltaSub: sub,
    deltaTone: kpi.tone,
  });

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Финансы · Обзор</h1>
          <div className="page-subtitle">P&L и юнит-экономика · период {periodLabel(period)} · по дате оплаты</div>
        </div>
        <div className="page-head-actions">
          <PeriodSelector value={period} onChange={setP} />
        </div>
      </div>

      <div className="sec">
        <div className="kpi-hero" data-cells="6">
          <KpiCell primary icon="dollar-sign" label="Чистая прибыль" {...cell(k.profit, fmtRub, "vs пред. период")} spark={spark("profit")} sparkColor="var(--ok)" />
          <KpiCell icon="trending-up" label="Gross" {...cell(k.gross, fmtRubK, "vs пред.")} spark={spark("income")} sparkColor="var(--accent)" />
          <KpiCell icon="percent" label="Комиссии" {...cell(k.commissions, fmtRubK, "")} />
          <KpiCell icon="banknote" label="Net" {...cell(k.net, fmtRubK, "vs пред.")} />
          <KpiCell icon="receipt" label="Расходы" {...cell(k.expenses, fmtRubK, "vs пред.")} spark={spark("expense")} sparkColor="var(--spend)" />
          <KpiCell icon="scale" label="Маржа" {...cell(k.margin, (v) => fmtPct(v), "")} />
        </div>
      </div>

      <div className="sec">
        <div className="card">
          <div className="card-head">
            <Icon name="bar-chart" size={14} />
            <div className="sec-title">Доход / расход / прибыль по дням</div>
            <div className="combo-legend" style={{ marginLeft: 12 }}>
              <span className="lg"><span className="lg-swatch" style={{ background: "var(--accent)" }} /> Доход</span>
              <span className="lg"><span className="lg-swatch" style={{ background: "var(--spend)" }} /> Расход</span>
              <span className="lg"><span className="lg-line" style={{ background: "var(--ok)" }} /> Прибыль</span>
            </div>
          </div>
          <div className="card-body">
            {daily.length ? <ComboChart data={daily} /> : <div className="empty-state">Нет данных за период</div>}
          </div>
        </div>
      </div>

      <div className="sec split-2">
        <div className="card">
          <div className="card-head">
            <Icon name="git-merge" size={14} />
            <div className="sec-title">Водопад прибыли</div>
            <div className="sec-sub">от Gross к чистой прибыли · {periodLabel(period)}</div>
          </div>
          <div className="card-body"><Waterfall data={waterfall} /></div>
        </div>

        <div className="card">
          <div className="card-head">
            <Icon name="pie-chart" size={14} />
            <div className="sec-title">Структура выручки</div>
            <div className="sec-sub">по провайдерам</div>
          </div>
          <div className="card-body">
            {byProvider.length ? <Donut data={byProvider} centerValue={fmtRubK(k.gross.value)} centerLabel="gross" /> : <div className="empty-state">Нет данных</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
