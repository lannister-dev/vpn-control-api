import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client.js";
import { useQuery } from "../../hooks/useQuery.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { Drawer } from "../Drawer.jsx";
import { Icon } from "../Icon.jsx";
import { toast } from "../Toast.jsx";
import { UserAvatar } from "../users/UserAvatar.jsx";
import { BalancePill } from "../users/BalancePill.jsx";
import { DaysCountdown, daysLeft } from "../users/DaysCountdown.jsx";
import { UserDrawer } from "../UserDrawer.jsx";
import {
  TicketStatusPill, PriorityDot, CategoryTag,
  MessageBubble, Lightbox, Composer, relTime,
  ticketStatusOptions, priorityOptions, categoryOptions,
} from "./SupportPrimitives.jsx";

function fmtDateTime(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("ru-RU"); } catch { return iso; }
}

/**
 * TicketDrawer — Telegram-style chat drawer for a single ticket.
 *
 * Props:
 *  - ticket: {
 *      id, subject, status, priority, category, assignee?,
 *      user: { id, username, telegram_id, balance, plan_name?, expires_at?, lifetime_spend? }
 *      created_at, last_activity_at
 *    }
 *  - templates: array<{ id, title, tag, body }>
 *  - onClose, onChanged
 */
export function TicketDrawer({ ticket, templates = [], onClose, onChanged }) {
  const [openUser, setOpenUser] = useState(null);
  const [ctxOpen, setCtxOpen] = useState(false);
  const [lightbox, setLightbox] = useState(null); // { media, index }
  const [confirmAction, setConfirmAction] = useState(null);
  const scrollerRef = useRef(null);

  // Fresh ticket + user data
  const detail = useQuery(
    () => api.get(`/support/tickets/${ticket.id}`).catch(() => null),
    { interval: 0, deps: [ticket.id] },
  );
  // Messages — poll every 5s while open
  const messagesQ = useQuery(
    () => api.get(`/support/tickets/${ticket.id}/messages?limit=200`).catch(() => ({ items: buildMockMessages(ticket) })),
    { interval: 5000, deps: [ticket.id] },
  );

  const live = { ...ticket, ...(detail.data || {}) };
  const user = live.user || {};
  const messages = messagesQ.data?.items || [];

  // Auto-scroll on new message
  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages.length]);

  // ── Actions
  const updateTicket = async (patch) => {
    try {
      await api.patch(`/support/tickets/${ticket.id}`, patch);
      detail.refetch();
      onChanged?.();
    } catch (e) {
      toast.bad(e.message || "Ошибка обновления тикета");
    }
  };

  const sendMessage = async (payload) => {
    const text = (payload?.text || "").trim();
    if (!text) {
      toast.bad("Сообщение не может быть пустым");
      return;
    }
    try {
      const fd = new FormData();
      fd.append("text", text);
      if (payload.is_note) fd.append("is_note", "true");
      const resp = await api.raw(`/support/tickets/${ticket.id}/messages`, {
        method: "POST",
        headers: {},
        body: fd,
      });
      if (!resp?.ok) {
        let detail = "Не удалось отправить";
        try {
          const body = await resp.json();
          detail = body?.detail || detail;
        } catch { /* ignore */ }
        toast.bad(detail);
        return;
      }
      toast.ok(payload.is_note ? "Заметка сохранена" : "Сообщение отправлено");
      messagesQ.refetch();
      onChanged?.();
    } catch (e) {
      toast.bad(e?.message || "Не удалось отправить");
    }
  };

  const grantDay = () =>
    setConfirmAction({
      title: "Продлить подписку на 1 день",
      body: "Подписка пользователя будет продлена на 1 сутки за счёт сервиса. Это действие отразится в чате тикета.",
      confirmLabel: "Продлить на 1 день",
      tone: "primary",
      icon: "plus",
      run: async () => {
        await api.post(`/support/tickets/${ticket.id}/grant-day`);
        toast.ok("Бесплатный день выдан");
        detail.refetch();
        messagesQ.refetch();
        onChanged?.();
      },
    });

  const refund = () =>
    setConfirmAction({
      title: "Возврат денег",
      body: "Последний оплаченный заказ будет возвращён на баланс пользователя. Заказ помечается как возвращённый. Действие необратимо.",
      confirmLabel: "Сделать возврат",
      tone: "danger",
      icon: "rotate-cw",
      run: async () => {
        await api.post(`/support/tickets/${ticket.id}/refund`);
        toast.ok("Возврат зачислен на баланс");
        detail.refetch();
        messagesQ.refetch();
        onChanged?.();
      },
    });

  const closeTicket = () =>
    setConfirmAction({
      title: "Закрыть тикет",
      body: "Тикет переведётся в статус «Закрыт». Юзер больше не увидит сообщений в этом разговоре до тех пор, пока не напишет снова.",
      confirmLabel: "Закрыть тикет",
      tone: "primary",
      icon: "check",
      run: async () => {
        await updateTicket({ status: "closed" });
        toast.ok("Тикет закрыт");
      },
    });
  const assignToMe = async () => {
    await updateTicket({ assignee: "me" });
  };

  const head = (
    <div className="tk-head">
      <UserAvatar name={user.username || `tg${user.telegram_id}`} size="md" />
      <div className="tk-head-main">
        <div className="tk-head-title">
          <span className="tk-head-id mono">#{String(ticket.id).slice(0, 8)}</span>
          <span className="tk-head-subject" title={live.subject || ""}>
            {live.subject || "Без темы"}
          </span>
          <TicketStatusPill status={live.status} />
        </div>
        <div className="tk-head-sub">
          <button
            type="button"
            className="tk-head-user"
            onClick={() => setOpenUser(user)}
            title="Открыть профиль"
          >
            {user.username ? `@${user.username}` : `tg:${user.telegram_id}`}
          </button>
          <span className="muted">·</span>
          <PriorityDot priority={live.priority} withLabel />
          <span className="muted">·</span>
          <CategoryTag category={live.category} />
          {live.assignee && (
            <>
              <span className="muted">·</span>
              <span className="muted small">{live.assignee === "me" ? "на вас" : live.assignee}</span>
            </>
          )}
          <span className="muted">·</span>
          <span className="muted small" title={fmtDateTime(live.created_at)}>
            создан {relTime(live.created_at)}
          </span>
        </div>
      </div>
    </div>
  );

  const actions = (
    <button className="btn btn-ghost btn-icon" onClick={() => setOpenUser(user)} title="Профиль пользователя">
      <Icon name="user" size={15} />
    </button>
  );

  return (
    <>
      <Drawer head={head} onClose={onClose} actions={actions} width={760} className="tk-drawer">
        {/* User summary card: KPIs + quick actions */}
        <div className="tk-summary">
          <div className="tk-summary-kpis">
            <div className="tk-kpi-cell">
              <div className="tk-kpi-label">Подписка</div>
              <div className="tk-kpi-val">
                {user.plan_name ? <span>{user.plan_name}</span> : <span className="muted">нет</span>}
              </div>
            </div>
            <div className="tk-kpi-cell">
              <div className="tk-kpi-label">Баланс</div>
              <div className="tk-kpi-val"><BalancePill amount={user.balance} /></div>
            </div>
            <div className="tk-kpi-cell">
              <div className="tk-kpi-label">Истекает</div>
              <div className="tk-kpi-val">
                <DaysCountdown days={daysLeft(user.expires_at)} />
              </div>
            </div>
            <div className="tk-kpi-cell">
              <div className="tk-kpi-label">Lifetime</div>
              <div className="tk-kpi-val mono">
                {user.lifetime_spend != null ? `${Number(user.lifetime_spend).toLocaleString("ru-RU")} ₽` : "—"}
              </div>
            </div>
          </div>
          <div className="tk-summary-actions">
            <button className="btn btn-sm" onClick={grantDay} title="Активировать дополнительный день подписки">
              <Icon name="plus" size={12} /> День бесплатно
            </button>
            <button className="btn btn-sm" onClick={refund}>
              <Icon name="rotate-cw" size={12} /> Возврат
            </button>
            {live.status !== "closed" ? (
              <>
                {live.status !== "in_progress" && (
                  <button className="btn btn-sm btn-ghost" onClick={() => updateTicket({ status: "in_progress" })}>
                    В работу
                  </button>
                )}
                <button className="btn btn-sm btn-primary" onClick={closeTicket}>
                  <Icon name="check" size={12} /> Закрыть тикет
                </button>
              </>
            ) : (
              <button className="btn btn-sm" onClick={() => updateTicket({ status: "in_progress" })}>
                <Icon name="rotate-cw" size={12} /> Переоткрыть
              </button>
            )}
          </div>
        </div>

        {/* Meta strip: status / priority / category */}
        <div className="tk-meta-strip">
          <MetaDropdown
            label="Статус"
            value={live.status}
            options={ticketStatusOptions()}
            onChange={(v) => updateTicket({ status: v })}
          />
          <MetaDropdown
            label="Приоритет"
            value={live.priority}
            options={priorityOptions()}
            onChange={(v) => updateTicket({ priority: v })}
          />
          <MetaDropdown
            label="Категория"
            value={live.category}
            options={categoryOptions()}
            onChange={(v) => updateTicket({ category: v })}
          />
          <button className="tk-context-toggle" onClick={() => setCtxOpen((v) => !v)} type="button">
            <Icon name={ctxOpen ? "chevron-down" : "chevron-right"} size={12} />
            <span>Контекст</span>
          </button>
        </div>
        {ctxOpen && <ContextPanel user={user} />}

        {/* Chat scroller */}
        <div className="tk-chat-scroller" ref={scrollerRef}>
          {messagesQ.loading && messages.length === 0 && (
            <div className="muted" style={{ padding: 20, textAlign: "center" }}>Загрузка…</div>
          )}
          {!messagesQ.loading && messages.length === 0 && (
            <div className="tk-chat-empty">
              <div className="tk-chat-empty-icon"><Icon name="message-square" size={20} /></div>
              <div>Сообщений пока нет</div>
              <div className="muted small">Напишите первое сообщение или внутреннюю заметку.</div>
            </div>
          )}
          {messages.map((m, idx) => {
            const prev = idx > 0 ? messages[idx - 1] : null;
            const showDateSep = !prev || !sameDay(prev.created_at, m.created_at);
            return (
              <div key={m.id || idx}>
                {showDateSep && <div className="tk-date-sep"><span>{formatDateSep(m.created_at)}</span></div>}
                <MessageBubble
                  message={m}
                  isOperator={m.from === "operator"}
                  onOpenMedia={(media, index) => setLightbox({ media, index })}
                />
              </div>
            );
          })}
        </div>

        {/* Composer */}
        <Composer
          templates={templates}
          user={{
            username: user.username,
            telegram_id: user.telegram_id,
            plan_name: user.plan_name,
            days_left: daysLeft(user.expires_at),
            balance: user.balance,
          }}
          onSend={sendMessage}
          onAddNote={sendMessage}
        />
      </Drawer>

      {openUser && <UserDrawer user={openUser} onClose={() => setOpenUser(null)} />}
      {lightbox && (
        <Lightbox media={lightbox.media} index={lightbox.index} onClose={() => setLightbox(null)} />
      )}
      {confirmAction && (
        <ConfirmAction action={confirmAction} onClose={() => setConfirmAction(null)} />
      )}
    </>
  );
}

function sameDay(a, b) {
  const da = new Date(a); const db = new Date(b);
  return da.getFullYear() === db.getFullYear() && da.getMonth() === db.getMonth() && da.getDate() === db.getDate();
}
function formatDateSep(iso) {
  const d = new Date(iso);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const that = new Date(d); that.setHours(0, 0, 0, 0);
  const diffDays = Math.round((today - that) / (24 * 3600 * 1000));
  if (diffDays === 0) return "Сегодня";
  if (diffDays === 1) return "Вчера";
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

function ContextPanel({ user }) {
  const subs = useQuery(
    () => api.get(`/subscriptions/by-user/${user.id}`).catch(() => []),
    { interval: 0, deps: [user.id] },
  );
  const list = Array.isArray(subs.data) ? subs.data : (subs.data?.items || []);
  const sub = list[0]; // most recent

  // Devices on first sub
  const devices = useQuery(
    () => sub ? api.get(`/subscriptions/${sub.id}/devices`).catch(() => []) : Promise.resolve([]),
    { interval: 0, deps: [sub?.id] },
  );
  const devs = Array.isArray(devices.data) ? devices.data : [];
  const activeDevs = devs.filter((d) => d.is_active);

  return (
    <div className="tk-context-panel">
      <div className="tk-ctx-row">
        <div className="tk-ctx-label">Тариф</div>
        <div className="tk-ctx-val">{sub?.plan_name || <span className="muted">—</span>}</div>
      </div>
      <div className="tk-ctx-row">
        <div className="tk-ctx-label">Регион</div>
        <div className="tk-ctx-val mono">{sub?.preferred_region || <span className="muted">авто</span>}</div>
      </div>
      <div className="tk-ctx-row">
        <div className="tk-ctx-label">Entry-нода</div>
        <div className="tk-ctx-val mono small">{sub?.entry_node_id ? String(sub.entry_node_id).slice(0, 12) + "…" : "—"}</div>
      </div>
      <div className="tk-ctx-row">
        <div className="tk-ctx-label">Активные устройства</div>
        <div className="tk-ctx-val">
          {activeDevs.length === 0 && <span className="muted">—</span>}
          {activeDevs.length > 0 && (
            <div className="tk-ctx-devs">
              {activeDevs.slice(0, 6).map((d) => (
                <span key={d.id} className="tk-ctx-dev" title={d.user_agent || ""}>
                  <Icon name={(d.user_agent || "").toLowerCase().includes("iphone") ? "smartphone" : "monitor"} size={11} />
                  <span className="mono small">{String(d.hwid_hash || d.id).slice(0, 10)}</span>
                </span>
              ))}
              {activeDevs.length > 6 && <span className="muted small">+{activeDevs.length - 6}</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetaDropdown({ label, value, options, onChange }) {
  return (
    <div className="tk-meta-cell">
      <div className="tk-meta-label">{label}</div>
      <select
        className="tk-meta-select"
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.id} value={o.id}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

/* Fallback mock messages for when the backend endpoint isn't deployed yet */
function buildMockMessages(t) {
  const now = Date.now();
  return [
    {
      id: "m1",
      from: "user",
      kind: "text",
      text: t.subject || "Не подключается VPN на iPhone — постоянно «не удалось установить соединение».",
      created_at: new Date(now - 38 * 60_000).toISOString(),
      author: { label: t.user?.username || "u" },
    },
    {
      id: "m2",
      from: "user",
      kind: "text",
      media: [
        { kind: "image", url: "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 320 200'><rect width='100%25' height='100%25' fill='%231c2026'/><text x='50%25' y='50%25' fill='%23b0b4bb' text-anchor='middle' font-family='Inter' font-size='14'>screenshot.png</text></svg>", thumb_url: null, file_name: "screenshot.png", file_size: 184320 },
      ],
      created_at: new Date(now - 36 * 60_000).toISOString(),
      author: { label: t.user?.username || "u" },
    },
    {
      id: "m3",
      from: "system",
      kind: "system",
      text: "Назначено: k.shirokova",
      created_at: new Date(now - 30 * 60_000).toISOString(),
    },
    {
      id: "m4",
      from: "operator",
      kind: "text",
      text: "Добрый день! Попробуйте удалить профиль и установить заново по новой ссылке.",
      created_at: new Date(now - 28 * 60_000).toISOString(),
      delivered: true,
      read: true,
    },
    {
      id: "m5",
      from: "user",
      kind: "text",
      media: [{ kind: "voice", url: null, duration: 8 }],
      created_at: new Date(now - 16 * 60_000).toISOString(),
      author: { label: t.user?.username || "u" },
    },
  ];
}

function ConfirmAction({ action, onClose }) {
  const [loading, setLoading] = useState(false);
  const onConfirm = async () => {
    setLoading(true);
    try {
      await action.run();
      onClose();
    } catch (e) {
      toast.bad(e?.detail || e?.message || "Ошибка");
      setLoading(false);
    }
  };
  return (
    <ConfirmModal
      title={action.title}
      body={action.body}
      confirmLabel={action.confirmLabel}
      tone={action.tone}
      icon={action.icon}
      loading={loading}
      onConfirm={onConfirm}
      onClose={onClose}
    />
  );
}
