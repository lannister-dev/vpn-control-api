import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { HealthRing, StackedMrr } from "./finance/charts.jsx";
import { FinLoading, FinError } from "./finance/kit.jsx";
import { fmtRub, fmtRubK } from "./finance/format.js";

export function FinanceMetricsPage() {
  const m = useQuery(() => api.get("/finance/metrics"), { deps: [] });
  if (m.loading && !m.data) return <FinLoading />;
  if (m.error && !m.data) return <FinError error={m.error} />;
  const d = m.data;

  const cards = [
    { key: "mrr", label: "MRR", value: fmtRubK(d.mrr), sub: "месячный recurring", icon: "repeat" },
    { key: "arr", label: "ARR", value: fmtRubK(d.arr), sub: "годовой run-rate", icon: "trending-up" },
    { key: "arpu", label: "ARPU", value: fmtRub(d.arpu), sub: "на платящего / мес", icon: "user" },
    { key: "churn", label: "Churn", value: `${d.churn_rate}%`, sub: "месячный отток · оценка", icon: "trending-down" },
    { key: "ltv", label: "LTV", value: fmtRub(d.ltv), sub: "ARPU / churn · оценка", icon: "dollar-sign" },
    { key: "cac", label: "CAC", value: fmtRub(d.cac), sub: "маркетинг+рефералка / новый", icon: "user" },
  ];

  const ratio = d.ltv_cac ?? 0;
  const tone = ratio >= 3 ? "" : ratio >= 1 ? "warn" : "bad";
  const toneWord = ratio >= 3 ? "здорово" : ratio >= 1 ? "пограничный" : "убыточно";

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Метрики</h1>
          <div className="page-subtitle">Юнит-экономика · MRR из активных подписок · окно 30 дней</div>
        </div>
        <div className="page-head-actions">
          <span className="pill muted">{d.paying_users} платящих · +{d.new_paying_users} новых</span>
        </div>
      </div>

      <div className="sec">
        <div className="card" style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: "var(--surface-2)" }}>
          <Icon name="info" size={15} className="muted" />
          <div style={{ fontSize: 12.5 }} className="muted">MRR/ARR/ARPU/CAC — из реальных данных. Churn и LTV — оценочные (выведены из изменения числа активных подписок за окно), уточнятся с накоплением истории.</div>
        </div>
      </div>

      <div className="sec" style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {cards.map((c) => (
          <div className="card" key={c.key} style={{ padding: 16 }}>
            <div className="kpi-label" style={{ marginBottom: 10 }}><Icon name={c.icon} size={12} /> <span>{c.label}</span></div>
            <div className="kpi-value tnum" style={{ fontSize: 26 }}>{c.value}</div>
            <div className="text-xs muted mt-1">{c.sub}</div>
          </div>
        ))}
      </div>

      <div className="sec split-2">
        <div className="card">
          <div className="card-head"><Icon name="scale" size={14} /><div className="sec-title">LTV / CAC</div></div>
          <div className="card-body">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
              <HealthRing value={ratio} max={5} tone={tone} sub={[
                <span key="1"><span className="status-dot ok" /> LTV {fmtRub(d.ltv)}</span>,
                <span key="2"><span className="status-dot bad" /> CAC {fmtRub(d.cac)}</span>,
              ]} />
              <div style={{ textAlign: "right" }}>
                <span className={`pill ${ratio >= 3 ? "ok" : ratio >= 1 ? "warn" : "bad"}`} style={{ fontSize: 12 }}>{toneWord}</span>
                <div className="text-xs muted mt-2" style={{ maxWidth: 200 }}>Цель ≥ 3.0. Зелёный ≥ 3, янтарь 1–3, красный &lt; 1.</div>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <Icon name="repeat" size={14} /><div className="sec-title">Динамика MRR</div>
            <div className="combo-legend" style={{ marginLeft: 10 }}>
              <span className="lg"><span className="lg-swatch" style={{ background: "var(--ok)" }} /> New</span>
              <span className="lg"><span className="lg-swatch" style={{ background: "var(--accent)" }} /> База</span>
            </div>
          </div>
          <div className="card-body"><StackedMrr data={d.mrr_series} /></div>
        </div>
      </div>
    </div>
  );
}
