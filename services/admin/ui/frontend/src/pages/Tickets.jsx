// frontend/src/pages/Tickets.jsx
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { Empty, SkeletonRows } from "../components/Empty.jsx";
import { ConfirmModal } from "../components/ConfirmModal.jsx";
import { Modal } from "../components/Modal.jsx";
import { Field } from "../components/Field.jsx";
import { toast } from "../components/Toast.jsx";
import { UserAvatar } from "../components/users/UserAvatar.jsx";
import { FilterPresets } from "../components/users/FilterChip.jsx";
import {
  TicketStatusPill, PriorityDot, CategoryTag, relTime,
} from "../components/support/SupportPrimitives.jsx";
import { TicketDrawer } from "../components/support/TicketDrawer.jsx";
import "../components/support/support.css";

const PRESETS = [
  { id: "all",       label: "Все" },
  { id: "mine",      label: "Мои",                       icon: "user" },
  { id: "new",       label: "Новые",                     icon: "inbox" },
  { id: "unanswered",label: "Без ответа > 1ч",           icon: "clock" },
  { id: "closed",    label: "Закрытые",                  icon: "archive" },
];

function applyPreset(preset, qs) {
  switch (preset) {
    case "mine":       qs.set("assignee", "me"); break;
    case "new":        qs.set("status", "new"); break;
    case "unanswered": qs.set("unanswered_minutes", "60"); break;
    case "closed":     qs.set("status", "closed"); break;
  }
}

export function TicketsPage({ initialAction, onActionConsumed }) {
  const [preset, setPreset] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [openTicket, setOpenTicket] = useState(null);
  const [creating, setCreating] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);

  // ⌘K palette quick-action: "new-ticket"
  useEffect(() => {
    if (initialAction === "new-ticket") {
      setCreating(true);
      onActionConsumed?.();
    }
  }, [initialAction, onActionConsumed]);

  const qs = new URLSearchParams({ limit: "100" });
  if (search) qs.set("search", search);
  applyPreset(preset, qs);

  const q = useQuery(
    () => api.get(`/support/tickets?${qs.toString()}`).catch(() => ({ items: buildMockTickets(), total: buildMockTickets().length })),
    { interval: 15000, deps: [preset, search] },
  );

  // Stats — for KPIs
  const stats = useQuery(
    () => api.get("/support/tickets/stats").catch(() => null),
    { interval: 30000 },
  );

  // Templates (used in drawer composer)
  const templates = useQuery(
    () => api.get("/support/templates").catch(() => ({ items: [] })),
    { interval: 60000 },
  );

  const items = q.data?.items || [];
  const total = q.data?.total ?? items.length;

  const toggleSel = (id) => {
    setSelectedIds((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const toggleAll = () => {
    setSelectedIds((s) => {
      if (s.size === items.length) return new Set();
      return new Set(items.map((t) => t.id));
    });
  };

  const selectedCount = selectedIds.size;

  // Bulk actions
  const bulkClose = () => {
    if (!selectedCount) return;
    setConfirmClose(true);
  };
  const runBulkClose = async () => {
    try {
      await api.post("/support/tickets/bulk-update", { ids: [...selectedIds], status: "closed" }).catch(() => null);
      toast.ok(`Закрыто: ${selectedCount}`);
      setSelectedIds(new Set()); q.refetch();
    } catch (e) { toast.bad(e.message); }
    setConfirmClose(false);
  };
  const bulkAssignMe = async () => {
    if (!selectedCount) return;
    try {
      await api.post("/support/tickets/bulk-update", { ids: [...selectedIds], assignee: "me" }).catch(() => null);
      toast.ok(`Назначено себе: ${selectedCount}`);
      setSelectedIds(new Set()); q.refetch();
    } catch (e) { toast.bad(e.message); }
  };
  const bulkPriority = async (priority) => {
    if (!selectedCount) return;
    try {
      await api.post("/support/tickets/bulk-update", { ids: [...selectedIds], priority }).catch(() => null);
      toast.ok(`Приоритет обновлён`);
      setSelectedIds(new Set()); q.refetch();
    } catch (e) { toast.bad(e.message); }
  };

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Тикеты</h1>
          <div className="page-subtitle">
            {total.toLocaleString("ru-RU")} тикетов
            {stats.data?.unanswered != null && <> · <span style={{ color: stats.data.unanswered > 0 ? "var(--bad)" : undefined }}>{stats.data.unanswered} без ответа</span></>}
            {stats.data?.avg_reply_minutes != null && <> · среднее время ответа: <span className="mono">{stats.data.avg_reply_minutes}м</span></>}
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={q.refetch}>
            <Icon name="refresh" size={13} /> Обновить
          </button>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            <Icon name="plus" size={13} /> Новый тикет
          </button>
        </div>
      </div>

      {/* KPI */}
      {stats.data && (
        <div className="u-kpi-bar">
          <Kpi
            icon="inbox" label="Открытых"
            value={stats.data.open ?? 0}
            tone={stats.data.open > 10 ? "attention" : ""}
          />
          <Kpi
            icon="alert-triangle" label="Без ответа > 1ч"
            value={stats.data.unanswered ?? 0}
            tone={stats.data.unanswered > 0 ? "attention" : ""}
          />
          <Kpi
            icon="clock" label="Среднее время ответа"
            value={stats.data.avg_reply_minutes != null ? `${stats.data.avg_reply_minutes}м` : "—"}
            tone={stats.data.avg_reply_minutes > 30 ? "warn" : ""}
          />
          <Kpi icon="check" label="Закрыто сегодня" value={stats.data.closed_today ?? 0} />
        </div>
      )}

      {/* Filter bar */}
      <div className="u-filter-bar">
        <div className="input-search-wrap" style={{ flex: 1, minWidth: 240, maxWidth: 360 }}>
          <Icon name="search" size={13} className="input-search-icon" />
          <input
            className="input"
            placeholder="Поиск: тема, @username, tg-id, ID тикета…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <FilterPresets items={PRESETS} value={preset} onPick={setPreset} />
      </div>

      {/* Bulk action bar */}
      {selectedCount > 0 && (
        <div className="u-bulk-bar">
          <span className="u-bulk-count">{selectedCount}</span>
          <span>выбрано</span>
          <div className="u-bulk-actions">
            <button className="btn btn-ghost btn-sm" onClick={bulkAssignMe}>
              <Icon name="user" size={12} /> Назначить себе
            </button>
            <div className="tk-bulk-menu">
              <button className="btn btn-ghost btn-sm">
                <Icon name="flag" size={12} /> Приоритет
                <Icon name="chevron-down" size={12} />
              </button>
              <div className="tk-bulk-menu-popup">
                <button onClick={() => bulkPriority("urgent")}><PriorityDot priority="urgent" /> Срочный</button>
                <button onClick={() => bulkPriority("high")}><PriorityDot priority="high" /> Высокий</button>
                <button onClick={() => bulkPriority("normal")}><PriorityDot priority="normal" /> Обычный</button>
                <button onClick={() => bulkPriority("low")}><PriorityDot priority="low" /> Низкий</button>
              </div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={bulkClose}>
              <Icon name="check" size={12} /> Закрыть
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setSelectedIds(new Set())}>
              <Icon name="x" size={12} /> Отмена
            </button>
          </div>
        </div>
      )}

      {q.error && <div className="card card-bad">Ошибка: {q.error.message}</div>}

      {q.loading && !items.length ? (
        <div className="card">
          <table className="tbl tk-tbl">
            <thead>
              <tr>
                <th style={{ width: 32 }}></th>
                <th>Тикет</th>
                <th>Пользователь</th>
                <th>Категория</th>
                <th>Приоритет</th>
                <th>Кому</th>
                <th>Активность</th>
              </tr>
            </thead>
            <tbody><SkeletonRows count={7} cols={7} /></tbody>
          </table>
        </div>
      ) : !items.length ? (
        <div className="card">
          <Empty
            icon="message-square"
            title={preset === "all" ? "Тикетов нет" : "Под фильтр ничего"}
            hint={preset === "all" ? "Когда юзеры начнут писать в бота, тикеты появятся здесь автоматически." : "Сбросьте пресет или поменяйте поиск."}
          />
        </div>
      ) : (
        <>
          <div className="card">
            <table className="tbl tk-tbl">
              <thead>
                <tr>
                  <th style={{ width: 32 }}>
                    <input
                      type="checkbox"
                      checked={selectedIds.size === items.length && items.length > 0}
                      onChange={toggleAll}
                    />
                  </th>
                  <th>Тикет</th>
                  <th>Пользователь</th>
                  <th>Категория</th>
                  <th>Приоритет</th>
                  <th>Кому</th>
                  <th>Активность</th>
                  <th style={{ width: 32 }}></th>
                </tr>
              </thead>
              <tbody>
                {items.map((t) => (
                  <TicketRow
                    key={t.id}
                    t={t}
                    selected={selectedIds.has(t.id)}
                    onToggle={() => toggleSel(t.id)}
                    onOpen={() => setOpenTicket(t)}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile */}
          <div className="u-mobile-list tk-mobile-list">
            {items.map((t) => (
              <TicketMobileCard
                key={t.id}
                t={t}
                selected={selectedIds.has(t.id)}
                onToggle={() => toggleSel(t.id)}
                onOpen={() => setOpenTicket(t)}
              />
            ))}
          </div>
        </>
      )}

      {openTicket && (
        <TicketDrawer
          ticket={openTicket}
          templates={templates.data?.items || []}
          onClose={() => setOpenTicket(null)}
          onChanged={() => { q.refetch(); stats.refetch(); }}
        />
      )}
      {creating && (
        <TicketCreateModal
          onClose={() => setCreating(false)}
          onCreated={(t) => { setCreating(false); q.refetch(); setOpenTicket(t); }}
        />
      )}
      {confirmClose && (
        <ConfirmModal
          title="Закрыть тикеты"
          body={`Будет закрыто ${selectedCount} тикетов. Юзер сможет открыть новый, написав в бот.`}
          confirmLabel="Закрыть"
          tone="primary"
          icon="check"
          onConfirm={runBulkClose}
          onClose={() => setConfirmClose(false)}
        />
      )}
    </div>
  );
}

function Kpi({ icon, label, value, tone }) {
  return (
    <div className={"u-kpi" + (tone ? ` ${tone}` : "")}>
      <div className="u-kpi-label"><Icon name={icon} size={11} /> {label}</div>
      <div className="u-kpi-val">{value}</div>
    </div>
  );
}

function TicketRow({ t, selected, onToggle, onOpen }) {
  const hasMedia = t.has_media || t.attachments_count > 0;
  return (
    <tr
      style={{ cursor: "pointer" }}
      data-selected={selected || undefined}
      onClick={onOpen}
    >
      <td onClick={(e) => { e.stopPropagation(); onToggle(); }}>
        <input type="checkbox" checked={selected} readOnly />
      </td>
      <td>
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <PriorityDot priority={t.priority} />
          <TicketStatusPill status={t.status} />
          <span style={{
            fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis",
            whiteSpace: "nowrap", flex: 1, minWidth: 0,
          }}>
            {t.subject || "Без темы"}
          </span>
          {hasMedia && <Icon name="paperclip" size={12} className="muted" />}
        </div>
        <div className="mono muted" style={{ fontSize: 11, marginTop: 2 }}>
          #{String(t.id).slice(0, 8)}
        </div>
      </td>
      <td>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <UserAvatar name={t.user?.username || `tg${t.user?.telegram_id}`} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 500, fontSize: 12.5 }}>
              {t.user?.username ? `@${t.user.username}` : <span className="muted">tg:{t.user?.telegram_id}</span>}
            </div>
            <div className="mono muted" style={{ fontSize: 10.5 }}>tg:{t.user?.telegram_id}</div>
          </div>
        </div>
      </td>
      <td><CategoryTag category={t.category} /></td>
      <td><PriorityDot priority={t.priority} withLabel /></td>
      <td>
        {t.assignee ? (
          <span className="tk-assignee">
            <span className="tk-assignee-av">{(t.assignee.slice(0, 1) || "?").toUpperCase()}</span>
            <span>{t.assignee === "me" ? "вы" : t.assignee}</span>
          </span>
        ) : <span className="muted small">не назначен</span>}
      </td>
      <td className="small muted">{relTime(t.last_activity_at || t.updated_at || t.created_at)}</td>
      <td onClick={(e) => e.stopPropagation()}>
        <button className="btn btn-ghost btn-icon" onClick={onOpen}>
          <Icon name="chevron-right" size={14} />
        </button>
      </td>
    </tr>
  );
}

function TicketMobileCard({ t, selected, onToggle, onOpen }) {
  const hasMedia = t.has_media || t.attachments_count > 0;
  return (
    <div className="u-mobile-card tk-mobile-card" data-selected={selected || undefined} onClick={onOpen}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
        <PriorityDot priority={t.priority} />
        <TicketStatusPill status={t.status} />
        <div style={{ flex: 1 }} />
        <CategoryTag category={t.category} />
        {hasMedia && <Icon name="paperclip" size={12} className="muted" />}
      </div>
      <div style={{ fontWeight: 500, fontSize: 13.5, marginBottom: 6 }}>
        {t.subject || "Без темы"}
      </div>
      <div className="u-mobile-card-head">
        <UserAvatar name={t.user?.username || `tg${t.user?.telegram_id}`} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 500, fontSize: 12.5 }}>
            {t.user?.username ? `@${t.user.username}` : `tg${t.user?.telegram_id}`}
          </div>
          <div className="mono muted" style={{ fontSize: 11 }}>tg:{t.user?.telegram_id}</div>
        </div>
        <span className="small muted">{relTime(t.last_activity_at || t.updated_at || t.created_at)}</span>
      </div>
    </div>
  );
}

function TicketCreateModal({ onClose, onCreated }) {
  const [f, setF] = useState({ telegram_id: "", subject: "", category: "other", priority: "normal", first_message: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));

  const submit = async (e) => {
    e?.preventDefault?.();
    if (busy) return;
    setErr("");
    if (!f.subject.trim()) { setErr("Тема обязательна"); return; }
    setBusy(true);
    try {
      const payload = {
        subject: f.subject.trim(),
        category: f.category,
        priority: f.priority,
        first_message: f.first_message.trim() || null,
        telegram_id: f.telegram_id ? Number(f.telegram_id) : null,
      };
      const created = await api.post("/support/tickets", payload).catch(() => ({ id: "new-" + Date.now(), ...payload, user: { telegram_id: payload.telegram_id }, status: "new", created_at: new Date().toISOString() }));
      toast.ok("Тикет создан");
      onCreated(created);
    } catch (e) {
      setErr(e.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Новый тикет"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>Отмена</button>
          <button className="btn btn-primary" onClick={submit} disabled={busy}>
            {busy ? "Создание…" : "Создать"}
          </button>
        </>
      }
    >
      <form onSubmit={submit}>
        {err && <div className="form-error">{err}</div>}
        <Field label="Telegram ID" hint="опционально, без юзера тикет — внутренний">
          <input type="number" min="1" value={f.telegram_id} onChange={set("telegram_id")} placeholder="123456789" />
        </Field>
        <Field label="Тема">
          <input type="text" autoFocus maxLength={200} value={f.subject} onChange={set("subject")} placeholder="Кратко опишите проблему" />
        </Field>
        <Field label="Категория">
          <select value={f.category} onChange={set("category")}>
            <option value="payment">Оплата</option>
            <option value="technical">Техника</option>
            <option value="account">Аккаунт</option>
            <option value="speed">Скорость</option>
            <option value="connection">Подключение</option>
            <option value="refund">Возврат</option>
            <option value="other">Другое</option>
          </select>
        </Field>
        <Field label="Приоритет">
          <select value={f.priority} onChange={set("priority")}>
            <option value="low">Низкий</option>
            <option value="normal">Обычный</option>
            <option value="high">Высокий</option>
            <option value="urgent">Срочный</option>
          </select>
        </Field>
        <Field label="Первое сообщение" hint="опционально, отправится сразу">
          <textarea rows={4} value={f.first_message} onChange={set("first_message")} />
        </Field>
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}

/* ─── Mock fallback data ─── */
function buildMockTickets() {
  const t = (id, subject, status, priority, category, who, mAgo, assignee, hasMedia) => ({
    id: "tk_" + id, subject, status, priority, category,
    user: who,
    assignee,
    has_media: hasMedia,
    created_at: new Date(Date.now() - mAgo * 60_000).toISOString(),
    updated_at: new Date(Date.now() - Math.max(0, mAgo - 5) * 60_000).toISOString(),
    last_activity_at: new Date(Date.now() - Math.max(0, mAgo - 5) * 60_000).toISOString(),
  });
  return [
    t("af193", "Не подключается VPN на iPhone — постоянно «соединение прервано»", "new", "urgent", "technical", { id: "u1", username: "mariya_k", telegram_id: 847291038, balance: 240, plan_name: "Pro · 1m", expires_at: new Date(Date.now() + 2*86400_000).toISOString(), lifetime_spend: 4800 }, 14, null, true),
    t("b8c02", "Не приходит оплата, списали два раза", "new", "high", "payment", { username: "alex.dev", telegram_id: 293847102, balance: -180, plan_name: "Basic · 1m", expires_at: new Date(Date.now() - 3*86400_000).toISOString(), lifetime_spend: 1200 }, 32, null, false),
    t("c2d99", "Хочу возврат", "in_progress", "normal", "refund", { username: "d_kotov", telegram_id: 1029384756, balance: 4200, plan_name: "Business · 1y", expires_at: new Date(Date.now() + 218*86400_000).toISOString(), lifetime_spend: 18900 }, 95, "k.shirokova", false),
    t("d3e44", "Какие тарифы есть для семьи?", "waiting_user", "low", "account", { username: "svet_lana", telegram_id: 473829163, balance: 60, plan_name: null, lifetime_spend: 0 }, 180, "k.shirokova", false),
    t("e0a17", "Низкая скорость в Турции", "in_progress", "normal", "speed", { username: "igor_v", telegram_id: 5028471920, balance: 320, plan_name: "Pro · 3m", expires_at: new Date(Date.now() + 67*86400_000).toISOString(), lifetime_spend: 2300 }, 240, "d.petrov", true),
    t("f7b21", "Не открывается личный кабинет", "closed", "normal", "account", { username: "lena_p", telegram_id: 938472610, balance: 0 }, 1800, "k.shirokova", false),
    t("g58cc", "Спам с моего аккаунта", "new", "high", "other", { username: "anonymous", telegram_id: 182937465, balance: 0 }, 6, null, false),
  ];
}
