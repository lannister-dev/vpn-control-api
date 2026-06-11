import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { ConfirmModal } from "../components/ConfirmModal.jsx";
import { PeriodSelector, FinLoading, FinError, periodLabel, rangeFor } from "./finance/kit.jsx";
import { fmtRub, fmtRubK, fmtCur } from "./finance/format.js";
import { KIND_LABELS, KIND_COLORS, KIND_CHIP } from "./finance/labels.js";
import { downloadCsv } from "./finance/csv.js";

const KIND_OPTS = Object.keys(KIND_LABELS).map((v) => ({ v, l: KIND_LABELS[v] }));
const CURRENCIES = ["RUB", "EUR", "USD", "GBP"];
const PERIOD_OPTS = [{ v: "monthly", l: "Ежемесячно" }, { v: "yearly", l: "Ежегодно" }, { v: "weekly", l: "Еженедельно" }];

function TemplateDrawer({ template, onClose, onSaved }) {
  const editing = !!template;
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState(() => template
    ? { name: template.name, kind: template.kind, amount: String(template.amount), currency: template.currency, fx_rate: template.fx_rate ? String(template.fx_rate) : "", period: template.period, next_run_at: (template.next_run_at || "").slice(0, 10) || today, vendor: template.vendor || "", region: template.region || "" }
    : { name: "", kind: "infrastructure", amount: "", currency: "RUB", fx_rate: "", period: "monthly", next_run_at: today, vendor: "", region: "" });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const nonRub = form.currency !== "RUB";

  const save = async () => {
    setSaving(true); setErr(null);
    const body = {
      name: form.name, kind: form.kind, amount: parseFloat(form.amount),
      currency: form.currency, fx_rate: nonRub ? parseFloat(form.fx_rate) : null,
      period: form.period, next_run_at: `${form.next_run_at}T00:00:00Z`,
      vendor: form.vendor || null, region: form.region || null,
    };
    try {
      if (editing) await api.patch(`/finance/expense-templates/${template.id}`, body);
      else await api.post("/finance/expense-templates", body);
      onSaved();
    } catch (e) { setErr(e.message || "ошибка"); setSaving(false); }
  };

  return (
    <div className="slideover-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="slideover">
        <div className="slideover-head">
          <div className="slideover-title-main">
            <div className="slideover-title"><Icon name="repeat" size={16} /> {editing ? "Изменить шаблон" : "Новый шаблон"}</div>
            <div className="slideover-sub">Регулярный расход · авто-генерация по периоду</div>
          </div>
          <button className="btn btn-ghost btn-icon" onClick={onClose}><Icon name="x" size={15} /></button>
        </div>
        <div className="slideover-body">
          <div className="form-field">
            <label className="form-label">Название</label>
            <input type="text" placeholder="Hetzner EU-кластер" value={form.name} onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="form-field">
            <label className="form-label">Категория</label>
            <select value={form.kind} onChange={(e) => set("kind", e.target.value)}>
              {KIND_OPTS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
            </select>
          </div>
          <div className="form-row">
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">Сумма</label>
              <input type="number" placeholder="0" value={form.amount} onChange={(e) => set("amount", e.target.value)} />
            </div>
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">Валюта</label>
              <select value={form.currency} onChange={(e) => set("currency", e.target.value)}>
                {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
          {nonRub && (
            <div className="form-field" style={{ marginTop: 14 }}>
              <label className="form-label">Курс к ₽</label>
              <input type="number" placeholder="напр. 94.20" value={form.fx_rate} onChange={(e) => set("fx_rate", e.target.value)} />
            </div>
          )}
          <div className="form-row" style={{ marginTop: 14 }}>
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">Период</label>
              <select value={form.period} onChange={(e) => set("period", e.target.value)}>
                {PERIOD_OPTS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
              </select>
            </div>
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">Следующее списание</label>
              <input type="date" value={form.next_run_at} onChange={(e) => set("next_run_at", e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">Вендор</label>
              <input type="text" placeholder="Hetzner" value={form.vendor} onChange={(e) => set("vendor", e.target.value)} />
            </div>
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">Регион</label>
              <input type="text" placeholder="DE / —" value={form.region} onChange={(e) => set("region", e.target.value)} />
            </div>
          </div>
          {err && <div className="card-bad" style={{ borderRadius: 6 }}>{err}</div>}
        </div>
        <div className="slideover-foot">
          <button className="btn btn-ghost" onClick={onClose}>Отмена</button>
          <button className="btn btn-primary" disabled={saving || !form.name || !form.amount} onClick={save}><Icon name="check" size={13} /> {saving ? "Сохранение…" : "Сохранить"}</button>
        </div>
      </aside>
    </div>
  );
}

function AddExpenseDrawer({ expense, onClose, onSaved }) {
  const editing = !!expense;
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState(() => expense
    ? { kind: expense.kind, amount: String(expense.amount), currency: expense.currency, fx_rate: expense.fx_rate ? String(expense.fx_rate) : "", incurred_at: (expense.incurred_at || "").slice(0, 10) || today, vendor: expense.vendor || "", region: expense.region || "", description: expense.description || "" }
    : { kind: "infrastructure", amount: "", currency: "RUB", fx_rate: "", incurred_at: today, vendor: "", region: "", description: "" });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const nonRub = form.currency !== "RUB";
  const amountRub = nonRub && form.amount && form.fx_rate ? Math.round(parseFloat(form.amount) * parseFloat(form.fx_rate)) : (form.currency === "RUB" && form.amount ? Math.round(parseFloat(form.amount)) : null);

  const save = async () => {
    setSaving(true); setErr(null);
    const body = {
      kind: form.kind,
      amount: parseFloat(form.amount),
      currency: form.currency,
      fx_rate: nonRub ? parseFloat(form.fx_rate) : null,
      incurred_at: `${form.incurred_at}T00:00:00Z`,
      vendor: form.vendor || null,
      region: form.region || null,
      description: form.description || null,
    };
    try {
      if (editing) await api.patch(`/finance/expenses/${expense.id}`, body);
      else await api.post("/finance/expenses", body);
      onSaved(form.vendor);
    } catch (e) {
      setErr(e.message || "ошибка"); setSaving(false);
    }
  };

  return (
    <div className="slideover-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="slideover">
        <div className="slideover-head">
          <div className="slideover-title-main">
            <div className="slideover-title"><Icon name={editing ? "edit" : "plus"} size={16} /> {editing ? "Изменить расход" : "Новый расход"}</div>
            <div className="slideover-sub">Разовая операция · нормализуется в ₽</div>
          </div>
          <button className="btn btn-ghost btn-icon" onClick={onClose} title="Закрыть"><Icon name="x" size={15} /></button>
        </div>
        <div className="slideover-body">
          <div className="form-field">
            <label className="form-label">Категория</label>
            <select value={form.kind} onChange={(e) => set("kind", e.target.value)}>
              {KIND_OPTS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
            </select>
          </div>
          <div className="form-row">
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">Сумма</label>
              <input type="number" placeholder="0" value={form.amount} onChange={(e) => set("amount", e.target.value)} />
            </div>
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">Валюта</label>
              <select value={form.currency} onChange={(e) => set("currency", e.target.value)}>
                {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
          {nonRub && (
            <div className="form-field" style={{ marginTop: 14 }}>
              <label className="form-label">Курс к ₽ <span className="form-hint">· {form.currency} → RUB на дату</span></label>
              <input type="number" placeholder="напр. 94.20" value={form.fx_rate} onChange={(e) => set("fx_rate", e.target.value)} />
              {amountRub != null && <div className="text-xs muted mt-1 mono">≈ {fmtRub(amountRub)}</div>}
            </div>
          )}
          <div className="form-field" style={{ marginTop: 14 }}>
            <label className="form-label">Дата</label>
            <input type="date" value={form.incurred_at} onChange={(e) => set("incurred_at", e.target.value)} />
          </div>
          <div className="form-row">
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">Вендор</label>
              <input type="text" placeholder="Hetzner" value={form.vendor} onChange={(e) => set("vendor", e.target.value)} />
            </div>
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">Регион</label>
              <input type="text" placeholder="DE / —" value={form.region} onChange={(e) => set("region", e.target.value)} />
            </div>
          </div>
          <div className="form-field" style={{ marginTop: 14 }}>
            <label className="form-label">Описание</label>
            <textarea rows={2} placeholder="Назначение платежа" value={form.description} onChange={(e) => set("description", e.target.value)} />
          </div>
          {err && <div className="card-bad" style={{ borderRadius: 6 }}>{err}</div>}
        </div>
        <div className="slideover-foot">
          <button className="btn btn-ghost" onClick={onClose}>Отмена</button>
          <button className="btn btn-primary" disabled={saving || !form.amount} onClick={save}><Icon name="check" size={13} /> {saving ? "Сохранение…" : "Сохранить"}</button>
        </div>
      </aside>
    </div>
  );
}

export function FinanceExpensesPage() {
  const [period, setPeriod] = useState(() => localStorage.getItem("fin.period") || "30d");
  const [expDrawer, setExpDrawer] = useState(null);
  const [tplDrawer, setTplDrawer] = useState(null);
  const [confirmDel, setConfirmDel] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [toast, setToast] = useState(null);
  const setP = (p) => { setPeriod(p); localStorage.setItem("fin.period", p); };

  const r = rangeFor(period);
  const span = new Date(r.date_to) - new Date(r.date_from);
  const prevFrom = new Date(new Date(r.date_from).getTime() - span).toISOString();
  const qcur = `?date_from=${encodeURIComponent(r.date_from)}&date_to=${encodeURIComponent(r.date_to)}`;

  const summary = useQuery(() => api.get("/finance/expenses/summary" + qcur), { deps: [period] });
  const prevSummary = useQuery(() => api.get(`/finance/expenses/summary?date_from=${encodeURIComponent(prevFrom)}&date_to=${encodeURIComponent(r.date_from)}`), { deps: [period] });
  const list = useQuery(() => api.get("/finance/expenses" + qcur + "&limit=100"), { deps: [period] });
  const templates = useQuery(() => api.get("/finance/expense-templates"), { deps: [] });

  if (summary.loading && !summary.data) return <FinLoading />;
  if (summary.error && !summary.data) return <FinError error={summary.error} />;

  const byKind = (summary.data.items || [])
    .map((x) => ({ kind: x.kind, label: KIND_LABELS[x.kind] || x.kind, value: Number(x.total_rub), color: KIND_COLORS[x.kind] || "var(--text-muted)" }))
    .sort((a, b) => b.value - a.value);
  const total = Number(summary.data.total_rub);
  const prevTotal = Number(prevSummary.data?.total_rub || 0);
  const deltaPct = prevTotal ? ((total - prevTotal) / prevTotal) * 100 : null;
  const maxKind = Math.max(1, ...byKind.map((d) => d.value));

  const rows = list.data?.items || [];
  const tpls = templates.data?.items || [];
  const fmtDate = (s) => new Date(s).toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
  const ping = (m) => { setToast(m); setTimeout(() => setToast(null), 2600); };

  const delTemplate = async (id) => {
    try { await api.del(`/finance/expense-templates/${id}`); templates.refetch(); ping("Шаблон удалён"); } catch (e) { ping("Ошибка: " + e.message); }
  };

  const exportCsv = () => {
    downloadCsv(
      `expenses-${period}.csv`,
      ["incurred_at", "kind", "vendor", "amount", "currency", "amount_rub", "region", "source", "description"],
      rows.map((r2) => [r2.incurred_at, r2.kind, r2.vendor, r2.amount, r2.currency, r2.amount_rub, r2.region, r2.template_id ? "template" : "one-off", r2.description]),
    );
  };

  const doDeleteExpense = async () => {
    if (!confirmDel) return;
    setDeleting(true);
    try {
      await api.del(`/finance/expenses/${confirmDel.id}`);
      setConfirmDel(null); setDeleting(false);
      summary.refetch(); prevSummary.refetch(); list.refetch();
      ping("Расход удалён");
    } catch (e) { setDeleting(false); ping("Ошибка: " + e.message); }
  };

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Расходы</h1>
          <div className="page-subtitle">Операционные затраты · {periodLabel(period)} · источник: Expense API</div>
        </div>
        <div className="page-head-actions">
          <button className="btn" onClick={exportCsv}><Icon name="download" size={13} /> Экспорт CSV</button>
          <PeriodSelector value={period} onChange={setP} />
          <button className="btn btn-primary" onClick={() => setExpDrawer("new")}><Icon name="plus" size={13} /> Добавить расход</button>
        </div>
      </div>

      <div className="sec">
        <div className="card">
          <div className="card-head"><Icon name="receipt" size={14} /><div className="sec-title">Всего за период · по категориям</div></div>
          <div className="card-body">
            <div className="kpi-value tnum" style={{ fontSize: 34 }}>{fmtRub(total)}</div>
            {deltaPct != null && (
              <div className={`kpi-delta ${deltaPct > 0 ? "down" : "up"}`} style={{ marginTop: 10 }}>
                <Icon name={deltaPct > 0 ? "trending-up" : "trending-down"} size={12} />
                <span>{deltaPct > 0 ? "+" : ""}{deltaPct.toFixed(1)}%</span>
                <span className="muted" style={{ marginLeft: 4 }}>vs пред. период ({fmtRubK(prevTotal)})</span>
              </div>
            )}
            <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 2 }}>
              {byKind.map((d) => (
                <div className="hbar-row" key={d.kind}>
                  <span className="hbar-label"><span className="lg-swatch" style={{ background: d.color }} />{d.label}</span>
                  <div className="hbar-track"><div className="hbar-fill" style={{ width: `${(d.value / maxKind) * 100}%`, background: d.color }} /></div>
                  <span className="hbar-val">{fmtRubK(d.value)}</span>
                </div>
              ))}
              {!byKind.length && <div className="empty-state">Нет расходов за период</div>}
            </div>
          </div>
        </div>
      </div>

      <div className="sec">
        <div className="card">
          <div className="card-head"><Icon name="list" size={14} /><div className="sec-title">Операции</div><span className="pill muted">{rows.length}</span></div>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Дата</th><th>Категория</th><th>Вендор</th>
                  <th style={{ textAlign: "right" }}>Сумма</th><th style={{ textAlign: "right" }}>В ₽</th>
                  <th>Регион</th><th>Источник</th><th>Описание</th><th style={{ width: 66 }}></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r2) => (
                  <tr key={r2.id}>
                    <td className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>{fmtDate(r2.incurred_at)}</td>
                    <td><span className={`chip chip-${KIND_CHIP[r2.kind] || "muted"}`}>{KIND_LABELS[r2.kind] || r2.kind}</span></td>
                    <td style={{ fontWeight: 500 }}>{r2.vendor || "—"}</td>
                    <td className="tbl-num">{r2.currency === "RUB" ? <span className="muted">—</span> : fmtCur(r2.amount, r2.currency)}</td>
                    <td className="tbl-num" style={{ fontWeight: 500 }}>{fmtRub(r2.amount_rub)}</td>
                    <td className="mono" style={{ fontSize: 12 }}>{r2.region || "—"}</td>
                    <td>{r2.template_id ? <span className="pill accent"><Icon name="repeat" size={10} /> шаблон</span> : <span className="pill muted">разовый</span>}</td>
                    <td className="muted" style={{ fontSize: 12, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r2.description || ""}</td>
                    <td className="row-actions">
                      <div style={{ display: "flex", gap: 2, justifyContent: "flex-end" }}>
                        <button className="btn btn-ghost btn-icon" style={{ width: 26, height: 26 }} title="Изменить" onClick={() => setExpDrawer(r2)}><Icon name="edit" size={13} /></button>
                        <button className="btn btn-ghost btn-icon" style={{ width: 26, height: 26 }} title="Удалить" onClick={() => setConfirmDel(r2)}><Icon name="trash-2" size={13} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!rows.length && <div className="empty-state">Нет операций</div>}
          </div>
        </div>
      </div>

      <div className="sec">
        <div className="sec-head">
          <Icon name="repeat" size={14} />
          <div className="sec-title">Регулярные платежи</div>
          <div className="sec-sub">{tpls.length} шаблонов</div>
          <div className="sec-spacer" />
          <button className="btn btn-xs" onClick={() => setTplDrawer("new")}><Icon name="plus" size={11} /> Шаблон</button>
        </div>
        {tpls.length === 0 && <div className="empty-state">Нет шаблонов — добавьте регулярный расход</div>}
        <div className="tpl-grid">
          {tpls.map((t) => {
            const monthly = t.currency === "RUB" ? Number(t.amount) : Math.round(Number(t.amount) * Number(t.fx_rate || 1));
            return (
              <div className="tpl-card" key={t.id}>
                <div className="tpl-actions">
                  <button className="btn btn-ghost btn-icon" style={{ width: 24, height: 24 }} title="Изменить" onClick={() => setTplDrawer(t)}><Icon name="edit" size={13} /></button>
                  <button className="btn btn-ghost btn-icon" style={{ width: 24, height: 24 }} title="Удалить" onClick={() => delTemplate(t.id)}><Icon name="trash-2" size={13} /></button>
                </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                    <span className={`chip chip-${KIND_CHIP[t.kind] || "muted"}`}>{KIND_LABELS[t.kind] || t.kind}</span>
                  </div>
                  <div style={{ fontWeight: 600, fontSize: 13.5, marginBottom: 2 }}>{t.name}</div>
                  <div className="kpi-value tnum" style={{ fontSize: 22, marginTop: 6 }}>{fmtRub(monthly)}<span className="kpi-unit">/ {t.period === "yearly" ? "год" : t.period === "weekly" ? "нед" : "мес"}</span></div>
                  {t.currency !== "RUB" && <div className="text-xs muted mono mt-1">{fmtCur(t.amount, t.currency)} × {t.fx_rate}</div>}
                  <div style={{ borderTop: "1px solid var(--border)", marginTop: 12, paddingTop: 10, display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                    <span className="muted">{t.vendor || "—"}</span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><Icon name="calendar" size={11} className="muted" /> {fmtDate(t.next_run_at)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

      {tplDrawer && <TemplateDrawer template={tplDrawer === "new" ? null : tplDrawer} onClose={() => setTplDrawer(null)} onSaved={() => { setTplDrawer(null); templates.refetch(); ping("Шаблон сохранён"); }} />}
      {expDrawer && <AddExpenseDrawer
        expense={expDrawer === "new" ? null : expDrawer}
        onClose={() => setExpDrawer(null)}
        onSaved={(v) => { const wasNew = expDrawer === "new"; setExpDrawer(null); summary.refetch(); prevSummary.refetch(); list.refetch(); ping(wasNew ? `Расход добавлен · ${v || "без вендора"}` : "Расход обновлён"); }}
      />}
      {confirmDel && <ConfirmModal
        title="Удалить расход?"
        tone="danger"
        icon="trash-2"
        confirmLabel="Удалить"
        loading={deleting}
        onConfirm={doDeleteExpense}
        onClose={() => { if (!deleting) setConfirmDel(null); }}
        body={<>Удалить «{confirmDel.vendor || KIND_LABELS[confirmDel.kind] || confirmDel.kind}» на {fmtRub(confirmDel.amount_rub)}? Действие необратимо.</>}
      />}
      {toast && <div className="toast-wrap"><div className="toast"><span className="status-dot ok" /> {toast}</div></div>}
    </div>
  );
}
