import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { toast } from "../components/Toast.jsx";
import { ConfirmModal } from "../components/ConfirmModal.jsx";

const RUB = "₽";
const AUDIENCE_LABEL = { all: "Все", no_subscription: "Без подписки", has_subscription: "С подпиской", by_plan: "По тарифам" };
const APPLIES_SHORT = { any: "Любой", new_purchase: "Новая", renewal: "Продление" };
const STATUS_META = {
  active: { dot: "ok", label: "Активен" },
  disabled: { dot: "muted", label: "Выключен" },
  expired: { dot: "bad", label: "Истёк" },
  full: { dot: "warn", label: "Лимит исчерпан" },
  pending: { dot: "warn", label: "Запланирован" },
};

const fmtRub = (n) => (n == null ? "—" : new Intl.NumberFormat("ru-RU").format(Math.round(Number(n))) + " " + RUB);
const fmtNum = (n) => (n == null ? "—" : new Intl.NumberFormat("ru-RU").format(Number(n)));
const fmtDate = (s) => (!s ? "—" : new Date(s).toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" }));
const fmtDateTime = (s) => (!s ? "—" : new Date(s).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }));
const fmtDiscount = (p) => (p.discount_type === "percent" ? "−" + p.discount_value + "%" : "−" + fmtRub(p.discount_value));
const isExpired = (p) => p.expires_at && new Date(p.expires_at) < new Date();
const isPending = (p) => p.starts_at && new Date(p.starts_at) > new Date();
const isFull = (p) => p.max_activations != null && p.activation_count >= p.max_activations;
function deriveStatus(p) {
  if (!p.is_active) return "disabled";
  if (isExpired(p)) return "expired";
  if (isFull(p)) return "full";
  if (isPending(p)) return "pending";
  return "active";
}

function CodeCell({ code }) {
  const [copied, setCopied] = useState(false);
  const onCopy = (e) => {
    e.stopPropagation();
    try { navigator.clipboard?.writeText(code); } catch { /* ignore */ }
    toast.ok("Код " + code + " скопирован");
    setCopied(true); setTimeout(() => setCopied(false), 1100);
  };
  return (
    <span className={"promo-code" + (copied ? " copied" : "")} onClick={onCopy} title="Скопировать код">
      {code}<span className="copy-ico"><Icon name={copied ? "check" : "copy"} size={12} /></span>
    </span>
  );
}

function UsageCell({ p }) {
  const unlimited = p.max_activations == null;
  const pct = unlimited ? 0 : Math.min(100, Math.round((p.activation_count / p.max_activations) * 100));
  const cls = pct >= 100 ? "full" : pct >= 80 ? "warn" : "";
  return (
    <div className="usage">
      {!unlimited && <div className="usage-track"><div className={"usage-fill " + cls} style={{ width: pct + "%" }} /></div>}
      <span className="usage-num">{fmtNum(p.activation_count)} / {unlimited ? <span className="inf" title="Без лимита">∞</span> : fmtNum(p.max_activations)}</span>
    </div>
  );
}

function WindowCell({ p }) {
  if (!p.starts_at && !p.expires_at) return <span className="win win-mono">бессрочно</span>;
  if (isExpired(p)) return <span className="win"><span className="win-expired">истёк {fmtDate(p.expires_at)}</span></span>;
  return (
    <div className="win">
      <span className="win-mono">{p.starts_at ? fmtDate(p.starts_at) : "—"}</span> → <span className="win-mono">{p.expires_at ? fmtDate(p.expires_at) : "бессрочно"}</span>
      {isPending(p) && <div><span className="pill warn" style={{ marginTop: 4 }}>с {fmtDate(p.starts_at)}</span></div>}
    </div>
  );
}

function Row({ p, plans, onOpen, onEdit, onToggle, onDelete }) {
  const s = deriveStatus(p);
  const dim = s === "disabled" || s === "expired";
  const active = p.is_active && !isExpired(p);
  const planNames = (p.plan_ids || []).map((id) => plans.find((x) => x.id === id)?.name).filter(Boolean);
  return (
    <tr style={{ cursor: "pointer" }} data-dim={dim || undefined} onClick={() => onOpen(p)}>
      <td style={{ minWidth: 150 }}>
        <CodeCell code={p.code} />
        {p.description && <div className="muted truncate" style={{ fontSize: 11, maxWidth: 220, marginTop: 2 }}>{p.description}</div>}
      </td>
      <td><span className="disc-chip">{fmtDiscount(p)}{p.max_discount_rub != null && <span className="disc-cap">до {fmtRub(p.max_discount_rub)}</span>}</span></td>
      <td style={{ minWidth: 130 }}>
        <span className={"pill " + (p.audience === "all" ? "muted" : "info")}>{AUDIENCE_LABEL[p.audience]}</span>
        {p.audience === "by_plan" && planNames.length > 0 && <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>{planNames.join(", ")}</div>}
      </td>
      <td><span className="muted" style={{ fontSize: 12.5 }}>{APPLIES_SHORT[p.applies_to]}</span></td>
      <td style={{ minWidth: 150 }}><UsageCell p={p} /></td>
      <td style={{ minWidth: 160 }}><WindowCell p={p} /></td>
      <td><span className="status-cell"><span className={"status-dot " + STATUS_META[s].dot} />{STATUS_META[s].label}</span></td>
      <td style={{ width: 116 }}>
        <div className="row-actions" style={{ display: "inline-flex", gap: 2 }}>
          <button className="btn btn-ghost btn-icon btn-xs" title="Редактировать" onClick={(e) => { e.stopPropagation(); onEdit(p); }}><Icon name="edit" size={13} /></button>
          <button className="btn btn-ghost btn-icon btn-xs" title={active ? "Выключить" : "Включить"} onClick={(e) => { e.stopPropagation(); onToggle(p); }}><Icon name="power" size={13} /></button>
          <button className="btn btn-ghost btn-icon btn-xs" title="Удалить" style={{ color: "var(--bad)" }} onClick={(e) => { e.stopPropagation(); onDelete(p); }}><Icon name="trash-2" size={13} /></button>
        </div>
      </td>
    </tr>
  );
}

const FILTERS = [
  { id: "all", label: "Все" },
  { id: "active", label: "Активные" },
  { id: "expiring", label: "Истекают" },
  { id: "disabled", label: "Выключенные" },
  { id: "expired", label: "Истёкшие" },
];

function PromoList({ promos, plans, loading, onOpen, onCreate, onEdit, onToggle, onDelete }) {
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  const counts = useMemo(() => {
    const c = { all: promos.length, active: 0, expiring: 0, disabled: 0, expired: 0 };
    const soon = new Date(); soon.setDate(soon.getDate() + 7);
    promos.forEach((p) => {
      const s = deriveStatus(p);
      if (s === "disabled") c.disabled++;
      else if (s === "expired") c.expired++;
      if (p.is_active && !isExpired(p)) c.active++;
      if (p.expires_at && new Date(p.expires_at) <= soon && new Date(p.expires_at) >= new Date()) c.expiring++;
    });
    return c;
  }, [promos]);

  const filtered = useMemo(() => {
    const soon = new Date(); soon.setDate(soon.getDate() + 7);
    const q = search.trim().toUpperCase();
    return promos.filter((p) => {
      if (q && !(p.code.includes(q) || (p.description || "").toUpperCase().includes(q))) return false;
      const s = deriveStatus(p);
      if (filter === "active") return p.is_active && !isExpired(p);
      if (filter === "disabled") return s === "disabled";
      if (filter === "expired") return s === "expired";
      if (filter === "expiring") return p.expires_at && new Date(p.expires_at) <= soon && new Date(p.expires_at) >= new Date() && p.is_active;
      return true;
    });
  }, [promos, filter, search]);

  const totalActivations = promos.reduce((a, p) => a + (p.activation_count || 0), 0);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Промокоды</h1>
          <div className="page-subtitle">{promos.length} кодов · {counts.active} активных</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-primary" onClick={onCreate}><Icon name="plus" size={13} /> Создать промокод</button>
        </div>
      </div>

      <div className="kpi-hero" style={{ marginBottom: 22 }} data-cells="4">
        <div className="kpi-cell primary"><div className="kpi-label"><Icon name="tag" size={12} /> Активных промокодов</div><div className="kpi-value tnum">{counts.active}</div><div className="text-xs muted mt-1">{counts.expiring > 0 ? counts.expiring + " истекают за 7 дней" : "со здоровым сроком"}</div></div>
        <div className="kpi-cell"><div className="kpi-label"><Icon name="activity" size={11} /> Всего активаций</div><div className="kpi-value tnum">{fmtNum(totalActivations)}</div></div>
        <div className="kpi-cell"><div className="kpi-label"><Icon name="clock" size={11} /> Истекают (7д)</div><div className="kpi-value tnum">{counts.expiring}</div></div>
        <div className="kpi-cell"><div className="kpi-label"><Icon name="percent" size={11} /> Всего кодов</div><div className="kpi-value tnum">{promos.length}</div></div>
      </div>

      <div className="card">
        <div className="card-head">
          <div className="seg" style={{ display: "inline-grid", gridAutoFlow: "column", gridTemplateColumns: "none" }}>
            {FILTERS.map((f) => (
              <button key={f.id} data-active={filter === f.id} onClick={() => setFilter(f.id)}>{f.label}{counts[f.id] != null && <span style={{ marginLeft: 6, opacity: 0.6 }} className="tnum">{counts[f.id]}</span>}</button>
            ))}
          </div>
          <div className="sec-spacer" />
          <input className="input" placeholder="Поиск по коду…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ minWidth: 200, height: 30, fontFamily: search ? "var(--font-mono)" : "inherit" }} />
        </div>
        {loading && !promos.length ? (
          <div className="empty-state">Загрузка…</div>
        ) : filtered.length === 0 ? (
          <div className="empty-state">{promos.length ? "Ничего не найдено" : "Промокодов пока нет — создайте первый"}</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead><tr><th>Код</th><th>Скидка</th><th>Аудитория</th><th>Применение</th><th>Использовано</th><th>Окно</th><th>Статус</th><th /></tr></thead>
              <tbody>{filtered.map((p) => <Row key={p.id} p={p} plans={plans} onOpen={onOpen} onEdit={onEdit} onToggle={onToggle} onDelete={onDelete} />)}</tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function PromoDetail({ promo, onBack, onEdit, onToggle, onDelete }) {
  const stats = useQuery(() => api.get(`/promo/${promo.id}/stats`), { deps: [promo.id] });
  const acts = useQuery(() => api.get(`/promo/${promo.id}/activations?limit=50`), { deps: [promo.id] });
  const s = stats.data;
  const rows = acts.data?.items || [];
  const st = deriveStatus(promo);
  const unlimited = promo.max_activations == null;
  const pct = unlimited ? 0 : Math.min(100, Math.round((promo.activation_count / promo.max_activations) * 100));

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <button className="btn btn-ghost btn-xs" onClick={onBack} style={{ marginBottom: 8 }}><Icon name="chevron-left" size={13} /> К списку</button>
          <h1 className="page-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="promo-code" style={{ fontSize: 20 }}>{promo.code}</span>
            <span className="status-cell"><span className={"status-dot " + STATUS_META[st].dot} />{STATUS_META[st].label}</span>
          </h1>
          {promo.description && <div className="page-subtitle">{promo.description}</div>}
        </div>
        <div className="page-head-actions">
          <button className="btn" onClick={() => onEdit(promo)}><Icon name="edit" size={13} /> Изменить</button>
          <button className="btn" onClick={() => onToggle(promo)}><Icon name="power" size={13} /> {promo.is_active ? "Выключить" : "Включить"}</button>
          <button className="btn btn-danger" onClick={() => onDelete(promo)}><Icon name="trash-2" size={13} /> Удалить</button>
        </div>
      </div>

      <div className="sec">
        <div className="kpi-hero" data-cells="4">
          <div className="kpi-cell primary"><div className="kpi-label"><Icon name="activity" size={12} /> Активаций</div><div className="kpi-value tnum">{s ? fmtNum(s.activations) : "—"}</div></div>
          <div className="kpi-cell"><div className="kpi-label"><Icon name="users" size={11} /> Уникальных юзеров</div><div className="kpi-value tnum">{s ? fmtNum(s.unique_users) : "—"}</div></div>
          <div className="kpi-cell"><div className="kpi-label"><Icon name="receipt" size={11} /> Отдано скидок</div><div className="kpi-value tnum" style={{ color: "var(--warn)" }}>{s ? fmtRub(s.total_discount_rub) : "—"}</div></div>
          <div className="kpi-cell"><div className="kpi-label"><Icon name="trending-up" size={11} /> Выручка с промо</div><div className="kpi-value tnum" style={{ color: "var(--ok)" }}>{s ? fmtRub(s.revenue_after_rub) : "—"}</div></div>
        </div>
      </div>

      <div className="sec split-2">
        <div className="card">
          <div className="card-head"><Icon name="sliders" size={14} /><div className="sec-title">Параметры</div></div>
          <div className="card-body">
            <dl className="kv">
              <dt>Скидка</dt><dd><span className="disc-chip">{fmtDiscount(promo)}{promo.max_discount_rub != null && <span className="disc-cap">до {fmtRub(promo.max_discount_rub)}</span>}</span></dd>
              <dt>Аудитория</dt><dd>{AUDIENCE_LABEL[promo.audience]}</dd>
              <dt>Применение</dt><dd>{APPLIES_SHORT[promo.applies_to]}</dd>
              <dt>Мин. сумма</dt><dd className="mono">{promo.min_amount_rub != null ? fmtRub(promo.min_amount_rub) : "—"}</dd>
              <dt>На юзера</dt><dd className="mono">{promo.max_per_user}</dd>
              <dt>Окно</dt><dd>{promo.starts_at || promo.expires_at ? `${fmtDate(promo.starts_at)} → ${promo.expires_at ? fmtDate(promo.expires_at) : "бессрочно"}` : "бессрочно"}</dd>
            </dl>
            <div className="usage-bar-wrap" style={{ marginTop: 14 }}>
              {!unlimited && <div className="usage-bar-track"><div className="usage-bar-fill" style={{ width: pct + "%" }} /></div>}
              <span className="usage-bar-meta">{fmtNum(promo.activation_count)} / {unlimited ? "∞" : fmtNum(promo.max_activations)}</span>
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-head"><Icon name="activity" size={14} /><div className="sec-title">Активации</div><span className="pill muted">{acts.data?.total ?? rows.length}</span></div>
          <div style={{ overflowX: "auto", maxHeight: 360 }}>
            <table className="tbl">
              <thead><tr><th>Дата</th><th>Юзер</th><th style={{ textAlign: "right" }}>Было</th><th style={{ textAlign: "right" }}>Скидка</th><th style={{ textAlign: "right" }}>Стало</th></tr></thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.id}>
                    <td className="mono" style={{ fontSize: 12 }}>{fmtDateTime(a.created_at)}</td>
                    <td className="mono" style={{ fontSize: 12 }}>{a.user_id}</td>
                    <td className="tbl-num">{fmtRub(a.amount_before)}</td>
                    <td className="tbl-num" style={{ color: "var(--warn)" }}>{fmtRub(a.discount_applied)}</td>
                    <td className="tbl-num" style={{ color: "var(--ok)", fontWeight: 500 }}>{fmtRub(a.amount_after)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!rows.length && <div className="empty-state">Активаций ещё не было</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

const AUDIENCE_OPTS = Object.entries(AUDIENCE_LABEL);

function PromoForm({ promo, existingCodes, plans, onClose, onSaved }) {
  const editing = !!promo;
  const today = "";
  const toDate = (iso) => { try { return iso ? new Date(iso).toISOString().slice(0, 10) : ""; } catch { return ""; } };
  const [d, setD] = useState(() => promo ? {
    code: promo.code, description: promo.description || "", discount_type: promo.discount_type,
    discount_value: String(promo.discount_value), max_discount_rub: promo.max_discount_rub != null ? String(promo.max_discount_rub) : "",
    audience: promo.audience, plan_ids: promo.plan_ids ? [...promo.plan_ids] : [], applies_to: promo.applies_to,
    min_amount_rub: promo.min_amount_rub != null ? String(promo.min_amount_rub) : "", max_activations: promo.max_activations != null ? String(promo.max_activations) : "",
    max_per_user: String(promo.max_per_user), starts_at: toDate(promo.starts_at), expires_at: toDate(promo.expires_at),
  } : {
    code: "", description: "", discount_type: "percent", discount_value: "", max_discount_rub: "",
    audience: "all", plan_ids: [], applies_to: "any", min_amount_rub: "", max_activations: "", max_per_user: "1", starts_at: today, expires_at: today,
  });
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setD((s) => ({ ...s, [k]: v }));
  const togglePlan = (id) => setD((s) => ({ ...s, plan_ids: s.plan_ids.includes(id) ? s.plan_ids.filter((x) => x !== id) : [...s.plan_ids, id] }));

  useEffect(() => {
    const onEsc = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [onClose]);

  function validate() {
    const e = {};
    const code = d.code.trim().toUpperCase();
    if (!editing) {
      if (!code) e.code = "Укажите код";
      else if (!/^[A-Z0-9_-]{3,}$/.test(code)) e.code = "Латиница, цифры, _ и -, минимум 3 символа";
      else if (existingCodes.includes(code)) e.code = "Код уже существует";
    }
    const val = Number(d.discount_value);
    if (!d.discount_value || isNaN(val) || val <= 0) e.discount_value = "Укажите значение скидки";
    else if (d.discount_type === "percent" && val > 100) e.discount_value = "Процент ≤ 100";
    if (d.audience === "by_plan" && d.plan_ids.length === 0) e.plan_ids = "Выберите тариф";
    if (d.starts_at && d.expires_at && new Date(d.expires_at) < new Date(d.starts_at)) e.expires_at = "Окончание раньше начала";
    return e;
  }

  async function submit() {
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length) { toast.bad("Проверьте поля формы"); return; }
    const body = {
      description: d.description.trim() || null,
      discount_type: d.discount_type, discount_value: Number(d.discount_value),
      max_discount_rub: d.discount_type === "percent" && d.max_discount_rub ? Number(d.max_discount_rub) : null,
      audience: d.audience, plan_ids: d.audience === "by_plan" ? d.plan_ids : null,
      applies_to: d.applies_to,
      min_amount_rub: d.min_amount_rub ? Number(d.min_amount_rub) : null,
      max_activations: d.max_activations ? Number(d.max_activations) : null,
      max_per_user: d.max_per_user ? Number(d.max_per_user) : 1,
      starts_at: d.starts_at ? new Date(d.starts_at).toISOString() : null,
      expires_at: d.expires_at ? new Date(d.expires_at).toISOString() : null,
    };
    setSaving(true);
    try {
      if (editing) await api.patch(`/promo/${promo.id}`, body);
      else await api.post("/promo", { ...body, code: d.code.trim().toUpperCase() });
      toast.ok("Промокод " + (d.code || promo.code).toUpperCase() + (editing ? " обновлён" : " создан"));
      onSaved();
    } catch (err) {
      if (err?.status === 409) setErrors((x) => ({ ...x, code: "Код уже существует" }));
      toast.bad(err?.message || "Не удалось сохранить");
      setSaving(false);
    }
  }

  return (
    <div className="slideover-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <aside className="slideover" onMouseDown={(e) => e.stopPropagation()}>
        <div className="slideover-head">
          <div className="slideover-title-main">
            <div className="slideover-title"><Icon name="tag" size={17} /> {editing ? "Редактировать промокод" : "Новый промокод"}</div>
            <div className="slideover-sub">{editing ? "Изменения применятся сразу" : "Код станет доступен мгновенно"}</div>
          </div>
          <button className="btn btn-ghost btn-icon" onClick={onClose} title="Закрыть"><Icon name="x" size={15} /></button>
        </div>
        <div className="slideover-body">
          <div className="form-field">
            <label className="form-label">Код <span className="form-hint">верхний регистр</span></label>
            <input type="text" value={d.code} placeholder="WELCOME25" disabled={editing}
              className={"mono" + (errors.code ? " is-error" : "")}
              onChange={(e) => { set("code", e.target.value.toUpperCase()); if (errors.code) setErrors((x) => ({ ...x, code: null })); }} />
            {errors.code && <div className="field-error"><Icon name="alert-circle" size={12} /> {errors.code}</div>}
          </div>
          <div className="form-field">
            <label className="form-label">Описание <span className="form-hint">внутренняя заметка</span></label>
            <input type="text" value={d.description} placeholder="Где используется" onChange={(e) => set("description", e.target.value)} />
          </div>

          <div className="form-group-title"><Icon name="percent" size={13} /> Скидка</div>
          <div className="form-row">
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">Тип</label>
              <div className="seg">
                <button type="button" data-active={d.discount_type === "percent"} onClick={() => set("discount_type", "percent")}>Процент</button>
                <button type="button" data-active={d.discount_type === "fixed"} onClick={() => set("discount_type", "fixed")}>Фикс {RUB}</button>
              </div>
            </div>
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">{d.discount_type === "percent" ? "Значение" : "Сумма"}</label>
              <input type="number" value={d.discount_value} placeholder={d.discount_type === "percent" ? "25" : "100"}
                className={errors.discount_value ? "is-error" : ""}
                onChange={(e) => { set("discount_value", e.target.value); if (errors.discount_value) setErrors((x) => ({ ...x, discount_value: null })); }} />
              {errors.discount_value && <div className="field-error"><Icon name="alert-circle" size={12} /> {errors.discount_value}</div>}
            </div>
          </div>
          {d.discount_type === "percent" && (
            <div className="form-field" style={{ marginTop: 14 }}>
              <label className="form-label">Макс. скидка ₽ <span className="form-hint">потолок для процента</span></label>
              <input type="number" value={d.max_discount_rub} placeholder="без потолка" onChange={(e) => set("max_discount_rub", e.target.value)} />
            </div>
          )}

          <div className="form-group-title" style={{ marginTop: 16 }}><Icon name="users" size={13} /> Аудитория</div>
          <div className="form-field">
            <label className="form-label">Кому доступен</label>
            <select value={d.audience} onChange={(e) => set("audience", e.target.value)}>
              {AUDIENCE_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          {d.audience === "by_plan" && (
            <div className="form-field">
              <label className="form-label">Тарифы</label>
              <div className="plan-multi">
                {plans.map((pl) => (
                  <div key={pl.id} className="plan-opt" data-on={d.plan_ids.includes(pl.id)} onClick={() => togglePlan(pl.id)}>
                    <span className="opt-check">{d.plan_ids.includes(pl.id) && <Icon name="check" size={10} />}</span>
                    {pl.name}<span className="opt-price">{pl.price_rub}{RUB}</span>
                  </div>
                ))}
              </div>
              {errors.plan_ids && <div className="field-error"><Icon name="alert-circle" size={12} /> {errors.plan_ids}</div>}
            </div>
          )}
          <div className="form-field">
            <label className="form-label">Применение</label>
            <div className="seg">
              {[["any", "Любой"], ["new_purchase", "Новая"], ["renewal", "Продление"]].map(([v, l]) => (
                <button key={v} type="button" data-active={d.applies_to === v} onClick={() => set("applies_to", v)}>{l}</button>
              ))}
            </div>
          </div>

          <div className="form-group-title" style={{ marginTop: 16 }}><Icon name="sliders" size={13} /> Лимиты</div>
          <div className="form-row">
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">Мин. сумма ₽</label>
              <input type="number" value={d.min_amount_rub} placeholder="0" onChange={(e) => set("min_amount_rub", e.target.value)} />
            </div>
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">На пользователя</label>
              <input type="number" value={d.max_per_user} placeholder="1" onChange={(e) => set("max_per_user", e.target.value)} />
            </div>
          </div>
          <div className="form-field" style={{ marginTop: 14 }}>
            <label className="form-label">Всего активаций <span className="form-hint">пусто = без лимита</span></label>
            <input type="number" value={d.max_activations} placeholder="∞ без лимита" onChange={(e) => set("max_activations", e.target.value)} />
          </div>

          <div className="form-group-title" style={{ marginTop: 16 }}><Icon name="calendar" size={13} /> Срок действия</div>
          <div className="form-row">
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">Начало</label>
              <input type="date" value={d.starts_at} onChange={(e) => set("starts_at", e.target.value)} />
            </div>
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label className="form-label">Окончание</label>
              <input type="date" value={d.expires_at} className={errors.expires_at ? "is-error" : ""}
                onChange={(e) => { set("expires_at", e.target.value); if (errors.expires_at) setErrors((x) => ({ ...x, expires_at: null })); }} />
              {errors.expires_at && <div className="field-error"><Icon name="alert-circle" size={12} /> {errors.expires_at}</div>}
            </div>
          </div>
        </div>
        <div className="slideover-foot">
          <button className="btn btn-ghost" onClick={onClose} disabled={saving}>Отмена</button>
          <button className="btn btn-primary" onClick={submit} disabled={saving}><Icon name="check" size={13} /> {saving ? "Сохранение…" : editing ? "Сохранить" : "Создать"}</button>
        </div>
      </aside>
    </div>
  );
}

export function PromoPage() {
  const q = useQuery(() => api.get("/promo"), {});
  const plansQ = useQuery(() => api.get("/plans").catch(() => ({ items: [] })), {});
  const [detail, setDetail] = useState(null);
  const [form, setForm] = useState(null); // null | "new" | promo
  const [confirmDel, setConfirmDel] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const promos = q.data?.items || [];
  const plans = plansQ.data?.items || [];
  const current = detail ? promos.find((p) => p.id === detail) : null;
  useEffect(() => { if (detail && q.data && !current) setDetail(null); }, [detail, q.data, current]);

  const toggle = async (p) => {
    try { await api.patch(`/promo/${p.id}`, { is_active: !p.is_active }); toast.ok("Промокод " + p.code + (p.is_active ? " выключен" : " включён")); q.refetch(); }
    catch (e) { toast.bad(e?.message || "Ошибка"); }
  };
  const doDelete = async () => {
    if (!confirmDel) return;
    setDeleting(true);
    try {
      await api.del(`/promo/${confirmDel.id}`);
      if (detail === confirmDel.id) setDetail(null);
      toast.bad("Промокод " + confirmDel.code + " удалён");
      setConfirmDel(null); setDeleting(false); q.refetch();
    } catch (e) { setDeleting(false); toast.bad(e?.message || "Ошибка"); }
  };

  return (
    <>
      {current
        ? <PromoDetail promo={current} onBack={() => setDetail(null)} onEdit={setForm} onToggle={toggle} onDelete={setConfirmDel} />
        : <PromoList promos={promos} plans={plans} loading={q.loading} onOpen={(p) => setDetail(p.id)} onCreate={() => setForm("new")} onEdit={setForm} onToggle={toggle} onDelete={setConfirmDel} />}
      {form && (
        <PromoForm
          promo={form === "new" ? null : form}
          existingCodes={promos.map((p) => p.code)}
          plans={plans}
          onClose={() => setForm(null)}
          onSaved={() => { setForm(null); q.refetch(); }}
        />
      )}
      {confirmDel && (
        <ConfirmModal
          title="Удалить промокод?"
          tone="danger"
          icon="trash-2"
          confirmLabel="Удалить"
          loading={deleting}
          onConfirm={doDelete}
          onClose={() => { if (!deleting) setConfirmDel(null); }}
          body={<>Код <b className="mono">{confirmDel.code}</b> будет удалён. История активаций сохранится.</>}
        />
      )}
    </>
  );
}
