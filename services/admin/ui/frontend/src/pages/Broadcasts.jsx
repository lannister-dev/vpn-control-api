// frontend/src/pages/Broadcasts.jsx
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { Modal } from "../components/Modal.jsx";
import { Field } from "../components/Field.jsx";
import { DatePicker } from "../components/DatePicker.jsx";
import { TgTicks } from "../components/TgTicks.jsx";
import { Empty, SkeletonRows } from "../components/Empty.jsx";
import { toast } from "../components/Toast.jsx";
import { FilterChip } from "../components/users/FilterChip.jsx";
import { relTime } from "../components/support/SupportPrimitives.jsx";
import { TextEditor, htmlForTelegram } from "../components/TextEditor.jsx";
import "../components/support/support.css";

const AUDIENCE_PRESETS = [
  { id: "all",         label: "Все",                 icon: "users" },
  { id: "active",      label: "С активной подпиской",icon: "key" },
  { id: "expiring",    label: "Истекают (7д)",       icon: "clock" },
  { id: "by_plan",     label: "По тарифу",           icon: "wallet" },
  { id: "trial",       label: "Триал",               icon: "sparkles" },
  { id: "no_sub",      label: "Без подписки",        icon: "user" },
];

export function BroadcastsPage({ initialAction, onActionConsumed }) {
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    if (initialAction === "new-broadcast") {
      onActionConsumed?.();
    }
  }, [initialAction, onActionConsumed]);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Рассылки</h1>
          <div className="page-subtitle">Создавайте сообщения, выбирайте аудиторию и отправляйте сразу или по расписанию.</div>
        </div>
        <div className="page-head-actions">
          <div className="seg" style={{ width: 220 }}>
            <button data-active={!showHistory} onClick={() => setShowHistory(false)}>Новая</button>
            <button data-active={showHistory} onClick={() => setShowHistory(true)}>История</button>
          </div>
        </div>
      </div>

      <div style={{ display: showHistory ? "none" : "block" }}>
        <BroadcastComposer />
      </div>
      <div style={{ display: showHistory ? "block" : "none" }}>
        <BroadcastHistory />
      </div>
    </div>
  );
}

/* ─────────────── Composer ─────────────── */
function BroadcastComposer() {
  const plans = useQuery(() => api.get("/plans").catch(() => ({ items: [] })), { interval: 60000 });
  const [audience, setAudience] = useState("all");
  const [planId, setPlanId] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [buttons, setButtons] = useState([]); // [{text, url}]
  const [schedule, setSchedule] = useState("now");
  const [scheduledAt, setScheduledAt] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  // Audience size — preview
  const audienceQs = useMemo(() => {
    const qs = new URLSearchParams();
    qs.set("audience", audience);
    if (audience === "by_plan" && planId) qs.set("plan_id", planId);
    return qs.toString();
  }, [audience, planId]);
  const sizeQ = useQuery(
    () => api.get(`/support/broadcasts/audience-size?${audienceQs}`).catch(() => ({ count: estimateAudience(audience) })),
    { interval: 0, deps: [audienceQs] },
  );
  const audienceCount = sizeQ.data?.count ?? 0;

  const onPickFile = (e) => {
    const f = e.target.files?.[0];
    if (f) setFile(f);
    e.target.value = "";
  };

  const addButton = () => {
    if (buttons.length >= 5) return;
    setButtons((b) => [...b, { text: "", url: "" }]);
  };
  const updateButton = (i, key, val) => {
    setButtons((b) => b.map((row, idx) => (idx === i ? { ...row, [key]: val } : row)));
  };
  const removeButton = (i) => setButtons((b) => b.filter((_, idx) => idx !== i));

  const save = async (isDraft = false) => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("audience", audience);
      if (audience === "by_plan" && planId) fd.append("plan_id", planId);
      fd.append("text", htmlForTelegram(text));
      fd.append("buttons", JSON.stringify(buttons.filter((b) => b.text && b.url)));
      if (file) fd.append("media", file);
      fd.append("status", isDraft ? "draft" : (schedule === "now" ? "sending" : "scheduled"));
      if (schedule === "schedule" && scheduledAt) fd.append("scheduled_at", new Date(scheduledAt).toISOString());

      await api.raw("/support/broadcasts", { method: "POST", headers: {}, body: fd });
      toast.ok(isDraft ? "Черновик сохранён" : (schedule === "now" ? "Рассылка отправлена" : "Рассылка запланирована"));
      if (!isDraft) {
        setText(""); setFile(null); setButtons([]); setSchedule("now"); setScheduledAt("");
      }
    } catch (e) {
      toast.bad(e?.message || "Не удалось сохранить рассылку");
    }
    finally { setBusy(false); setConfirmOpen(false); }
  };

  return (
    <div className="br-grid">
      {/* LEFT: composer */}
      <div className="br-col">
        <section className="card br-section">
          <div className="br-section-head">
            <Icon name="users" size={14} /> Аудитория
            <span className="br-audience-count">
              Получат: <span className="mono">{audienceCount.toLocaleString("ru-RU")}</span>
            </span>
          </div>
          <div className="br-audience-chips">
            {AUDIENCE_PRESETS.map((p) => (
              <FilterChip
                key={p.id}
                icon={p.icon}
                label={p.label}
                applied={audience === p.id}
                onClick={() => setAudience(p.id)}
              />
            ))}
          </div>
          {audience === "by_plan" && (
            <div style={{ marginTop: 10 }}>
              <select className="select" value={planId} onChange={(e) => setPlanId(e.target.value)}>
                <option value="">— выберите тариф —</option>
                {(plans.data?.items || []).map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
          )}
        </section>

        <section className="card br-section">
          <div className="br-section-head">
            <Icon name="message-square" size={14} /> Текст сообщения
            <span className="muted small">HTML · {text.replace(/<[^>]+>/g, "").length} симв.</span>
          </div>
          <TextEditor
            value={text}
            onChange={setText}
            placeholder="Привет, {user_name}! Мы добавили новые регионы для тарифа Pro: …"
            minHeight={160}
          />
        </section>

        <section className="card br-section">
          <div className="br-section-head">
            <Icon name="paperclip" size={14} /> Медиа
            <span className="muted small">опционально, 1 файл — фото / видео / документ</span>
          </div>
          {!file ? (
            <label className="br-drop">
              <Icon name="paperclip" size={20} />
              <span>Перетащите файл сюда или нажмите, чтобы выбрать</span>
              <input type="file" style={{ display: "none" }} onChange={onPickFile} />
            </label>
          ) : (
            <div className="br-file-chip">
              <Icon name={file.type?.startsWith("image/") ? "image" : file.type?.startsWith("video/") ? "video" : "file"} size={13} />
              <span className="name">{file.name}</span>
              <span className="muted small">{formatBytes(file.size)}</span>
              <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => setFile(null)}>
                <Icon name="x" size={12} />
              </button>
            </div>
          )}
        </section>

        <section className="card br-section">
          <div className="br-section-head">
            <Icon name="external-link" size={14} /> Inline кнопки
            <span className="muted small">до 5 кнопок</span>
            <button className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }} disabled={buttons.length >= 5} onClick={addButton}>
              <Icon name="plus" size={12} /> Добавить
            </button>
          </div>
          {buttons.length === 0 && <div className="muted small">Без кнопок</div>}
          {buttons.map((b, i) => (
            <div key={i} className="br-btn-row">
              <input
                className="input"
                placeholder="Текст кнопки"
                value={b.text}
                onChange={(e) => updateButton(i, "text", e.target.value)}
                maxLength={64}
              />
              <input
                className="input"
                placeholder="https://… или t.me/…"
                value={b.url}
                onChange={(e) => updateButton(i, "url", e.target.value)}
              />
              <button className="btn btn-ghost btn-icon" onClick={() => removeButton(i)} title="Убрать">
                <Icon name="x" size={13} />
              </button>
            </div>
          ))}
        </section>

        <section className="card br-section">
          <div className="br-section-head">
            <Icon name="calendar" size={14} /> Отправка
          </div>
          <div className="seg" style={{ width: 280 }}>
            <button data-active={schedule === "now"} onClick={() => setSchedule("now")}>Сейчас</button>
            <button data-active={schedule === "schedule"} onClick={() => setSchedule("schedule")}>Запланировать</button>
          </div>
          {schedule === "schedule" && (
            <div style={{ marginTop: 10 }}>
              <Field label="Дата и время">
                <DatePicker mode="datetime" value={scheduledAt} onChange={setScheduledAt} />
              </Field>
            </div>
          )}
        </section>

        <div className="br-actions">
          <button className="btn" onClick={() => save(true)} disabled={busy || (!text.trim() && !file)}>
            <Icon name="save" size={13} /> Сохранить черновик
          </button>
          <button
            className="btn btn-primary"
            onClick={() => setConfirmOpen(true)}
            disabled={busy || (!text.trim() && !file) || (schedule === "schedule" && !scheduledAt) || audienceCount === 0}
          >
            <Icon name="send" size={13} />
            {schedule === "schedule" ? "Запланировать" : "Отправить сейчас"}
          </button>
        </div>
      </div>

      {/* RIGHT: preview */}
      <div className="br-col">
        <div className="card br-preview-wrap">
          <div className="br-section-head">
            <Icon name="eye" size={14} /> Превью сообщения
            <span className="muted small">как увидит юзер в Telegram</span>
          </div>
          <div className="br-preview">
            <div className="br-bubble">
              {file && (
                <div className="br-bubble-media">
                  {file.type?.startsWith("image/")
                    ? <ImagePreview file={file} />
                    : file.type?.startsWith("video/")
                      ? <div className="br-bubble-vid"><Icon name="video" size={24} /></div>
                      : <div className="br-bubble-doc"><Icon name="file" size={16} /> {file.name}</div>}
                </div>
              )}
              <div className="br-bubble-text txed-preview">
                {text.trim()
                  ? <span dangerouslySetInnerHTML={{ __html: htmlForTelegram(text) }} />
                  : <span className="muted">Текст сообщения…</span>}
              </div>
              {buttons.filter((b) => b.text && b.url).length > 0 && (
                <div className="br-bubble-buttons">
                  {buttons.filter((b) => b.text && b.url).map((b, i) => (
                    <a key={i} href={b.url} className="br-inline-btn" target="_blank" rel="noopener noreferrer">
                      {b.text}
                    </a>
                  ))}
                </div>
              )}
              <div className="br-bubble-meta">
                <span className="mono">
                  {(scheduledAt && schedule === "schedule"
                    ? new Date(scheduledAt)
                    : new Date()
                  ).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
                </span>
                <TgTicks status={schedule === "schedule" ? "pending" : "delivered"} size={11} />
              </div>
            </div>
            <div className="br-bot-note">от @vpn_bot · бот</div>
          </div>
        </div>

        <div className="card br-summary">
          <div className="br-section-head">
            <Icon name="info" size={14} /> Сводка
          </div>
          <dl className="kv">
            <dt>Аудитория</dt>
            <dd>{AUDIENCE_PRESETS.find((p) => p.id === audience)?.label}{audience === "by_plan" && planId ? ` · ${(plans.data?.items || []).find((p) => p.id === planId)?.name}` : ""}</dd>
            <dt>Получателей</dt>
            <dd className="mono">{audienceCount.toLocaleString("ru-RU")}</dd>
            <dt>Размер сообщения</dt>
            <dd className="mono">{text.replace(/<[^>]+>/g, "").length} симв.{file ? `, +1 файл (${formatBytes(file.size)})` : ""}</dd>
            <dt>Когда</dt>
            <dd>{schedule === "now" ? "Сразу" : scheduledAt ? new Date(scheduledAt).toLocaleString("ru-RU") : <span className="muted">—</span>}</dd>
          </dl>
        </div>
      </div>

      {confirmOpen && (
        <Modal
          title={schedule === "schedule" ? "Запланировать рассылку?" : "Отправить рассылку?"}
          onClose={() => setConfirmOpen(false)}
          footer={
            <>
              <button className="btn btn-ghost" onClick={() => setConfirmOpen(false)} disabled={busy}>Отмена</button>
              <button className="btn btn-primary" onClick={() => save(false)} disabled={busy}>
                {busy ? "Отправка…" : "Подтвердить"}
              </button>
            </>
          }
        >
          <p style={{ fontSize: 13.5, lineHeight: 1.5, color: "var(--text)" }}>
            Сообщение будет отправлено <b className="mono">{audienceCount.toLocaleString("ru-RU")}</b> пользователям.
          </p>
          <p style={{ fontSize: 12.5, color: "var(--text-muted)" }}>
            Telegram ограничивает скорость рассылки до 30 сообщений в секунду — фактическая доставка займёт примерно <span className="mono">{Math.ceil(audienceCount / 30 / 60)}</span> мин.
            Это действие нельзя отменить после старта.
          </p>
        </Modal>
      )}
    </div>
  );
}

function estimateAudience(audience) {
  return { all: 4128, active: 1842, expiring: 18, by_plan: 0, trial: 102, no_sub: 612 }[audience] || 0;
}

function ImagePreview({ file }) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    const url = URL.createObjectURL(file);
    setSrc(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  if (!src) return null;
  return <img src={src} alt="" />;
}

function formatBytes(b) {
  if (b == null) return "";
  const u = ["B", "KB", "MB", "GB"]; let i = 0; let n = b;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (n >= 100 || i === 0 ? Math.round(n) : n.toFixed(1)) + " " + u[i];
}

/** Minimal MarkdownV2-like rendering for preview: bold *…*, italic _…_, code `…`. */
function renderMarkdownV2(text) {
  const parts = [];
  const re = /(\*[^*\n]+\*|_[^_\n]+_|`[^`\n]+`)/g;
  let last = 0;
  let m;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(<span key={key++}>{text.slice(last, m.index)}</span>);
    const t = m[1];
    if (t.startsWith("*")) parts.push(<b key={key++}>{t.slice(1, -1)}</b>);
    else if (t.startsWith("_")) parts.push(<i key={key++}>{t.slice(1, -1)}</i>);
    else parts.push(<code key={key++} className="mono">{t.slice(1, -1)}</code>);
    last = m.index + t.length;
  }
  if (last < text.length) parts.push(<span key={key++}>{text.slice(last)}</span>);
  return <>{parts.map((p, i) => <span key={i} style={{ whiteSpace: "pre-wrap" }}>{p}</span>)}</>;
}

/* ─────────────── History ─────────────── */
function BroadcastHistory() {
  const q = useQuery(
    () => api.get("/support/broadcasts?limit=50").catch(() => ({ items: buildMockBroadcasts() })),
    { interval: 30000 },
  );
  const items = q.data?.items || [];
  const [opened, setOpened] = useState(null);

  return (
    <div className="card">
      <table className="tbl">
        <thead>
          <tr>
            <th>Дата</th>
            <th>Аудитория</th>
            <th>Превью</th>
            <th style={{ textAlign: "right" }}>Доставлено</th>
            <th style={{ textAlign: "right" }}>Ошибки</th>
            <th style={{ textAlign: "right" }}>Click rate</th>
            <th>Статус</th>
          </tr>
        </thead>
        <tbody>
          {q.loading && items.length === 0 && <SkeletonRows count={6} cols={7} />}
          {!q.loading && items.length === 0 && (
            <tr><td colSpan={7}>
              <Empty icon="send" title="Рассылок ещё не было" hint="Создайте первую — она появится здесь со статистикой." />
            </td></tr>
          )}
          {items.map((b) => {
            const total = (b.delivered || 0) + (b.errors || 0);
            const clickRate = total > 0 ? Math.round(((b.clicks || 0) / total) * 1000) / 10 : null;
            return (
              <tr key={b.id} onClick={() => setOpened(b)} style={{ cursor: "pointer" }} title="Открыть рассылку">
                <td className="small">
                  <div>{new Date(b.sent_at || b.created_at).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</div>
                  <div className="muted small">{relTime(b.sent_at || b.created_at)}</div>
                </td>
                <td className="small">{b.audience_label || b.audience}</td>
                <td className="small muted" style={{ maxWidth: 360, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={b.preview}>
                  {b.preview}
                </td>
                <td className="tbl-num mono">{b.delivered?.toLocaleString("ru-RU") ?? "—"}</td>
                <td className="tbl-num mono" style={{ color: b.errors > 0 ? "var(--bad)" : undefined }}>
                  {b.errors?.toLocaleString("ru-RU") ?? "—"}
                </td>
                <td className="tbl-num mono">{clickRate != null ? `${clickRate}%` : "—"}</td>
                <td><StatusPill status={b.status} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {opened && <BroadcastDetail broadcast={opened} onClose={() => setOpened(null)} onChanged={() => { setOpened(null); q.refetch(); }} />}
    </div>
  );
}

function BroadcastDetail({ broadcast: b, onClose, onChanged }) {
  const total = (b.delivered || 0) + (b.errors || 0);
  const clickRate = total > 0 ? Math.round(((b.clicks || 0) / total) * 1000) / 10 : null;
  const [busy, setBusy] = useState(false);
  const canCancel = b.status === "scheduled";
  const cancel = async () => {
    if (!canCancel) return;
    if (!window.confirm("Отменить запланированную рассылку?")) return;
    setBusy(true);
    try {
      await api.post(`/support/broadcasts/${b.id}/cancel`);
      toast.ok("Рассылка отменена");
      onChanged?.();
    } catch (e) {
      toast.err(e?.message || "Не удалось отменить");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={`Рассылка · ${new Date(b.sent_at || b.created_at).toLocaleString("ru-RU")}`} onClose={onClose}>
      <div className="kv-table-wrap" style={{ marginBottom: 14 }}>
        <dl className="kv">
          <dt>Статус</dt><dd><StatusPill status={b.status} /></dd>
          <dt>Аудитория</dt><dd>{b.audience_label || b.audience}</dd>
          <dt>Доставлено</dt><dd className="mono">{b.delivered?.toLocaleString("ru-RU") ?? "—"}</dd>
          <dt>Ошибок</dt><dd className="mono" style={{ color: b.errors > 0 ? "var(--bad)" : undefined }}>{b.errors?.toLocaleString("ru-RU") ?? "—"}</dd>
          {clickRate != null && <><dt>Click rate</dt><dd className="mono">{clickRate}%</dd></>}
          {b.scheduled_at && <><dt>Запланирована</dt><dd>{new Date(b.scheduled_at).toLocaleString("ru-RU")}</dd></>}
        </dl>
      </div>
      {b.media_url && (
        <div style={{ marginBottom: 12 }}>
          {b.media_kind === "image"
            ? <img src={b.media_url} alt="" style={{ maxWidth: "100%", borderRadius: 8, border: "1px solid var(--border)" }} />
            : <div className="muted small"><Icon name="paperclip" size={11} /> Медиа · {b.media_kind}</div>}
        </div>
      )}
      <div className="card" style={{ padding: 12, background: "var(--surface-2)" }}>
        <div className="muted small" style={{ marginBottom: 6 }}>Текст сообщения</div>
        <div
          className="txed-preview"
          style={{ whiteSpace: "pre-wrap" }}
          dangerouslySetInnerHTML={{ __html: b.text_body || b.preview || "<span style='color:var(--text-muted)'>пусто</span>" }}
        />
      </div>
      {canCancel && (
        <div style={{ marginTop: 12, display: "flex", justifyContent: "flex-end" }}>
          <button className="btn btn-ghost btn-sm" onClick={cancel} disabled={busy}>
            {busy ? "Отменяется…" : "Отменить рассылку"}
          </button>
        </div>
      )}
      {Array.isArray(b.inline_buttons) && b.inline_buttons.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div className="muted small" style={{ marginBottom: 6 }}>
            Кнопки <span style={{ color: "var(--text-faint)" }}>({b.inline_buttons.length})</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {b.inline_buttons.map((btn, i) => (
              <a
                key={i}
                href={btn.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: "flex", flexDirection: "column", gap: 2,
                  padding: "8px 12px",
                  background: "var(--accent-soft)",
                  border: "1px solid var(--accent-border, var(--border))",
                  borderRadius: 8,
                  textDecoration: "none",
                  color: "var(--accent, var(--text))",
                }}
              >
                <span style={{ fontWeight: 500, fontSize: 13 }}>{btn.text}</span>
                <span className="mono small muted" style={{ wordBreak: "break-all" }}>{btn.url}</span>
              </a>
            ))}
          </div>
        </div>
      )}
    </Modal>
  );
}

function StatusPill({ status }) {
  const map = {
    draft:     { label: "Черновик",      tone: "" },
    scheduled: { label: "Запланирована", tone: "info" },
    sending:   { label: "Отправляется",  tone: "warn" },
    sent:      { label: "Отправлена",    tone: "ok" },
    failed:    { label: "Ошибка",        tone: "bad" },
    cancelled: { label: "Отменена",      tone: "" },
  };
  const s = map[status] || { label: status, tone: "" };
  return <span className={`pill ${s.tone} small`}>{s.label}</span>;
}

function buildMockBroadcasts() {
  const now = Date.now();
  const day = 86400_000;
  return [
    { id: "b1", sent_at: new Date(now - 0.5 * day).toISOString(), audience: "all", audience_label: "Все · 4 128", preview: "Привет! Мы открыли регионы в Японии и Сингапуре для Pro.", delivered: 4071, errors: 57, clicks: 612, status: "sent" },
    { id: "b2", sent_at: new Date(now - 2 * day).toISOString(), audience: "expiring", audience_label: "Истекают (7д)", preview: "Ваша подписка скоро истекает. Продлите со скидкой 15% по промокоду …", delivered: 18, errors: 0, clicks: 11, status: "sent" },
    { id: "b3", sent_at: new Date(now - 4 * day).toISOString(), audience: "trial", audience_label: "Триал", preview: "Спасибо, что попробовали! Pro на месяц — 299₽ вместо 490.", delivered: 102, errors: 1, clicks: 38, status: "sent" },
    { id: "b4", sent_at: null, audience: "by_plan", audience_label: "Тариф Business · 84", preview: "Технические работы в субботу с 02:00 до 04:00 МСК", delivered: 0, errors: 0, clicks: 0, status: "scheduled" },
    { id: "b5", sent_at: null, audience: "all", audience_label: "Все", preview: "Черновик про обновление приложения", delivered: 0, errors: 0, clicks: 0, status: "draft" },
  ];
}
