import { Icon } from "../components/Icon.jsx";
import { HealthRing, StackedMrr } from "./finance/charts.jsx";

const CARDS = [
  { key: "mrr", label: "MRR", value: "₽948k", sub: "месячный recurring", delta: "+6.2%", tone: "up", icon: "repeat" },
  { key: "arr", label: "ARR", value: "₽11.38M", sub: "годовой run-rate", delta: "+6.2%", tone: "up", icon: "trending-up" },
  { key: "arpu", label: "ARPU", value: "₽214", sub: "на активного / мес", delta: "+1.8%", tone: "up", icon: "user" },
  { key: "churn", label: "Churn", value: "4.2%", sub: "месячный отток", delta: "−0.4 пп", tone: "up", icon: "trending-down" },
  { key: "ltv", label: "LTV", value: "₽5 090", sub: "за весь срок", delta: "+3.1%", tone: "up", icon: "dollar-sign" },
  { key: "cac", label: "CAC", value: "₽1 340", sub: "стоимость привлечения", delta: "+5.0%", tone: "down", icon: "user" },
];

const MRR_SERIES = (() => {
  const months = ["Июл", "Авг", "Сен", "Окт", "Ноя", "Дек", "Янв", "Фев", "Мар", "Апр", "Май", "Июн"];
  let base = 612000;
  const seeds = [41, 53, 29, 47, 38, 61, 44, 35, 57, 49, 42, 60];
  return months.map((m, i) => {
    const neu = 38000 + seeds[i] * 400;
    const exp = 12000 + ((seeds[i] * 233) % 14000);
    const chu = 18000 + ((seeds[i] * 197) % 16000);
    base = base + neu + exp - chu;
    return { month: m, base, neu, exp, chu };
  });
})();

export function FinanceMetricsPage() {
  const ratio = 3.8;
  const tone = ratio >= 3 ? "" : ratio >= 1 ? "warn" : "bad";
  const toneWord = ratio >= 3 ? "здорово" : ratio >= 1 ? "пограничный" : "убыточно";

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Метрики</h1>
          <div className="page-subtitle">Юнит-экономика и подписочные метрики · 30 дней</div>
        </div>
        <div className="page-head-actions">
          <span className="planned-tag" style={{ position: "static", padding: "4px 8px" }}>планируемый rollup</span>
        </div>
      </div>

      <div className="sec">
        <div className="card" style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: "var(--surface-2)", borderStyle: "dashed" }}>
          <Icon name="info" size={15} className="muted" />
          <div style={{ fontSize: 12.5 }} className="muted">Метрики ниже считаются из планируемого ночного rollup. Сейчас отображаются репрезентативные данные — карточки помечены <span className="planned-tag" style={{ position: "static", display: "inline-block" }}>план</span>.</div>
        </div>
      </div>

      <div className="sec" style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {CARDS.map((c) => (
          <div className="card" key={c.key} style={{ padding: 16, position: "relative" }}>
            <span className="planned-tag">план</span>
            <div className="kpi-label" style={{ marginBottom: 10 }}><Icon name={c.icon} size={12} /> <span>{c.label}</span></div>
            <div className="kpi-value tnum" style={{ fontSize: 26 }}>{c.value}</div>
            <div className="text-xs muted mt-1">{c.sub}</div>
            <div className={`kpi-delta ${c.tone}`} style={{ marginTop: 8 }}>
              <Icon name={c.tone === "up" ? "trending-up" : c.tone === "down" ? "trending-down" : "trending-flat"} size={12} />
              <span>{c.delta}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="sec split-2">
        <div className="card">
          <div className="card-head"><Icon name="scale" size={14} /><div className="sec-title">LTV / CAC</div><span className="planned-tag" style={{ position: "static" }}>план</span></div>
          <div className="card-body">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
              <HealthRing value={ratio} max={5} tone={tone} sub={[
                <span key="1"><span className="status-dot ok" /> LTV ₽5 090</span>,
                <span key="2"><span className="status-dot bad" /> CAC ₽1 340</span>,
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
              <span className="lg"><span className="lg-swatch" style={{ background: "var(--info)" }} /> Expansion</span>
              <span className="lg"><span className="lg-swatch" style={{ background: "var(--accent)" }} /> База</span>
            </div>
            <span className="planned-tag" style={{ position: "static", marginLeft: "auto" }}>план</span>
          </div>
          <div className="card-body"><StackedMrr data={MRR_SERIES} /></div>
        </div>
      </div>
    </div>
  );
}
