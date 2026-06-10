import { useState, useEffect } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { FinError } from "./finance/kit.jsx";

const PROVIDER_OPTS = ["platega", "crypto", "freekassa", "stars", "balance", "free"];

function methodLabel(pm) {
  return pm == null ? "default" : String(pm);
}

export function FinanceRatesPage() {
  const fees = useQuery(() => api.get("/billing/provider-fees"), { deps: [] });
  const [rates, setRates] = useState([]);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ provider: "platega", payment_method: "", fee_percent: "" });
  const [toast, setToast] = useState(null);

  useEffect(() => { if (fees.data?.items) setRates(fees.data.items); }, [fees.data]);

  if (fees.error && !fees.data) return <FinError error={fees.error} />;

  const ping = (m) => { setToast(m); setTimeout(() => setToast(null), 2200); };

  const upsert = async (provider, payment_method, fee_percent) => {
    await api.raw("/billing/provider-fees", { method: "PUT", body: { provider, payment_method, fee_percent } });
  };

  const editFee = (id, val) => setRates((rs) => rs.map((r) => (r.id === id ? { ...r, fee_percent: val } : r)));
  const commitFee = async (r, raw) => {
    const v = parseFloat(String(raw).replace(",", "."));
    if (isNaN(v)) return;
    try {
      await upsert(r.provider, r.payment_method, v);
      ping("Ставка обновлена · применится к будущим платежам");
      fees.refetch();
    } catch (e) { ping("Ошибка: " + e.message); }
  };
  const addRate = async () => {
    if (draft.fee_percent === "") return;
    const pm = draft.payment_method.trim() === "" ? null : parseInt(draft.payment_method, 10);
    try {
      await upsert(draft.provider, pm, parseFloat(draft.fee_percent));
      setAdding(false); setDraft({ provider: "platega", payment_method: "", fee_percent: "" });
      ping("Ставка добавлена"); fees.refetch();
    } catch (e) { ping("Ошибка: " + e.message); }
  };
  const remove = async (id) => {
    try { await api.del(`/billing/provider-fees/${id}`); ping("Ставка удалена"); fees.refetch(); }
    catch (e) { ping("Ошибка: " + e.message); }
  };

  const grouped = PROVIDER_OPTS
    .map((p) => ({ provider: p, items: rates.filter((r) => r.provider === p) }))
    .filter((g) => g.items.length);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Ставки комиссий</h1>
          <div className="page-subtitle">Комиссии провайдеров по методам оплаты · источник: provider fee rates API</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-primary" onClick={() => setAdding(true)}><Icon name="plus" size={13} /> Добавить ставку</button>
        </div>
      </div>

      <div className="sec">
        <div className="card" style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 14px", background: "var(--accent-soft)", border: "1px solid var(--accent-border)", color: "var(--accent-text)" }}>
          <Icon name="lock" size={15} style={{ flexShrink: 0 }} />
          <div style={{ fontSize: 12.5 }}>Изменения применяются только к будущим платежам. История комиссий заморожена и не пересчитывается.</div>
        </div>
      </div>

      <div className="sec">
        <div className="card">
          <div className="card-head">
            <Icon name="percent" size={14} />
            <div className="sec-title">Тарифная сетка</div>
            <span className="pill muted">{rates.length} ставок</span>
            <div className="sec-spacer" />
            <span className="text-xs muted">Кликните по проценту, чтобы изменить</span>
          </div>
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: "30%" }}>Провайдер</th>
                <th>Метод оплаты</th>
                <th style={{ textAlign: "right", width: 160 }}>Комиссия</th>
                <th style={{ width: 60 }}></th>
              </tr>
            </thead>
            <tbody>
              {grouped.map((g) => g.items.map((r, idx) => (
                <tr key={r.id}>
                  <td style={{ fontWeight: idx === 0 ? 600 : 400, color: idx === 0 ? "var(--text)" : "var(--text-muted)" }}>{idx === 0 ? r.provider : ""}</td>
                  <td>
                    {r.payment_method == null
                      ? <span className="pill muted">default · все методы</span>
                      : <span className="mono" style={{ fontSize: 12.5 }}>метод {r.payment_method}</span>}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 2, justifyContent: "flex-end" }}>
                      <input className="inline-edit" type="text" value={r.fee_percent}
                        onChange={(e) => editFee(r.id, e.target.value)}
                        onBlur={(e) => commitFee(r, e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()} />
                      <span className="mono muted" style={{ fontSize: 12.5 }}>%</span>
                    </span>
                  </td>
                  <td className="row-actions">
                    <button className="btn btn-ghost btn-icon" style={{ width: 26, height: 26 }} title="Удалить" onClick={() => remove(r.id)}>
                      <Icon name="trash-2" size={13} />
                    </button>
                  </td>
                </tr>
              )))}
              {adding && (
                <tr style={{ background: "var(--accent-soft)" }}>
                  <td>
                    <select className="select" style={{ minWidth: 0, width: "100%", height: 28 }} value={draft.provider} onChange={(e) => setDraft({ ...draft, provider: e.target.value })}>
                      {PROVIDER_OPTS.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </td>
                  <td>
                    <input className="input" style={{ minWidth: 0, width: "100%", height: 28 }} placeholder="напр. 2 (или пусто = default)" value={draft.payment_method} onChange={(e) => setDraft({ ...draft, payment_method: e.target.value })} autoFocus />
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <input className="inline-edit" style={{ borderColor: "var(--border-strong)" }} type="number" placeholder="0.0" value={draft.fee_percent} onChange={(e) => setDraft({ ...draft, fee_percent: e.target.value })} onKeyDown={(e) => e.key === "Enter" && addRate()} />
                    <span className="mono muted" style={{ fontSize: 12.5 }}>%</span>
                  </td>
                  <td className="row-actions" style={{ opacity: 1 }}>
                    <div style={{ display: "flex", gap: 2, justifyContent: "flex-end" }}>
                      <button className="btn btn-ghost btn-icon" style={{ width: 26, height: 26 }} onClick={addRate} title="Сохранить"><Icon name="check" size={14} /></button>
                      <button className="btn btn-ghost btn-icon" style={{ width: 26, height: 26 }} onClick={() => setAdding(false)} title="Отмена"><Icon name="x" size={14} /></button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {toast && <div className="toast-wrap"><div className="toast"><span className="status-dot ok" /> {toast}</div></div>}
    </div>
  );
}
