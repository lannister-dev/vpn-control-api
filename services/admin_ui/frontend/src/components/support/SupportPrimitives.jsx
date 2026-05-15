// Status/priority pills, message bubbles, media thumbs, lightbox, composer,
// template popover. All consume only design tokens from styles.css.
import { useState, useEffect, useRef, useCallback } from "react";
import { Icon } from "../Icon.jsx";
import { TgTicks } from "../TgTicks.jsx";
import { TextEditor, htmlForTelegram } from "../TextEditor.jsx";

/* ──────────────────────────────────────────────────────────
   STATUS PILL — ticket status
   states: new | in_progress | waiting_user | closed
   ────────────────────────────────────────────────────────── */
const TICKET_STATUS = {
  new:           { label: "Новый",        tone: "info"  },
  in_progress:   { label: "В работе",     tone: "accent"},
  waiting_user:  { label: "Ждёт юзера",   tone: "warn"  },
  closed:        { label: "Закрыт",       tone: "muted" },
};
export function TicketStatusPill({ status }) {
  const s = TICKET_STATUS[status] || { label: status, tone: "muted" };
  return (
    <span className={`tk-status tk-status-${s.tone}`}>
      <span className="dot" />
      {s.label}
    </span>
  );
}
export function ticketStatusOptions() {
  return Object.entries(TICKET_STATUS).map(([id, s]) => ({ id, label: s.label }));
}

/* ──────────────────────────────────────────────────────────
   PRIORITY DOT
   ────────────────────────────────────────────────────────── */
const PRIORITY = {
  low:    { tone: "muted", label: "Низкий"  },
  normal: { tone: "ok",    label: "Обычный" },
  high:   { tone: "warn",  label: "Высокий" },
  urgent: { tone: "bad",   label: "Срочный" },
};
export function PriorityDot({ priority, withLabel = false }) {
  const p = PRIORITY[priority] || PRIORITY.normal;
  return (
    <span className={`tk-priority tk-priority-${p.tone}`} title={`Приоритет: ${p.label}`}>
      <span className="dot" />
      {withLabel && <span className="label">{p.label}</span>}
    </span>
  );
}
export function priorityOptions() {
  return Object.entries(PRIORITY).map(([id, p]) => ({ id, label: p.label }));
}

/* ──────────────────────────────────────────────────────────
   CATEGORY TAG — small inline chip
   ────────────────────────────────────────────────────────── */
const CATEGORY_LABELS = {
  payment:     "Оплата",
  technical:   "Техника",
  account:     "Аккаунт",
  speed:       "Скорость",
  connection:  "Подключение",
  refund:      "Возврат",
  other:       "Другое",
};
export function CategoryTag({ category }) {
  const label = CATEGORY_LABELS[category] || category || "—";
  return <span className="tk-cat-tag">{label}</span>;
}
export function categoryOptions() {
  return Object.entries(CATEGORY_LABELS).map(([id, label]) => ({ id, label }));
}

/* ──────────────────────────────────────────────────────────
   RELATIVE TIME helper
   ────────────────────────────────────────────────────────── */
export function relTime(iso) {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return `${s}с`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}м`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}ч`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}д`;
  return new Date(iso).toLocaleDateString("ru-RU");
}

/* ──────────────────────────────────────────────────────────
   MESSAGE BUBBLE — chat bubble with media + meta
   ────────────────────────────────────────────────────────── */
export function MessageBubble({
  message,
  isOperator,
  onOpenMedia,
}) {
  const { kind = "text", text, media, created_at, delivered, read, author, is_note } = message;

  // System events (centered, italic)
  if (kind === "system") {
    return (
      <div className="tk-sys-event">
        <span>{text}</span>
        <span className="time">· {relTime(created_at)}</span>
      </div>
    );
  }

  return (
    <div className={"tk-msg-row " + (isOperator ? "tk-msg-row-op" : "tk-msg-row-user")}>
      {!isOperator && author && (
        <div className="tk-msg-avatar" title={author.label}>
          {(author.label || "?").slice(0, 1).toUpperCase()}
        </div>
      )}
      <div className={"tk-msg-bubble " + (isOperator ? "tk-bubble-op" : "tk-bubble-user") + (is_note ? " tk-bubble-note" : "")}>
        {is_note && (
          <div className="tk-bubble-note-tag">
            <Icon name="lock" size={11} /> Внутренняя заметка
          </div>
        )}
        {media && media.length > 0 && (
          <div className={"tk-media tk-media-" + (media.length > 1 ? "many" : "one")}>
            {media.map((m, i) => (
              <MediaThumb key={i} media={m} onClick={() => onOpenMedia && onOpenMedia(media, i)} />
            ))}
          </div>
        )}
        {text && (
          /<[a-z][\s\S]*>/i.test(text)
            ? <div className="tk-msg-text txed-preview" dangerouslySetInnerHTML={{ __html: text }} />
            : <div className="tk-msg-text" style={{ whiteSpace: "pre-wrap" }}>{text}</div>
        )}
        <div className="tk-msg-meta">
          <span>{new Date(created_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</span>
          {isOperator && (
            <TgTicks
              status={read ? "read" : delivered ? "delivered" : "sent"}
              size={11}
            />
          )}
        </div>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   MEDIA THUMB — single image/video/document/voice
   ────────────────────────────────────────────────────────── */
export function MediaThumb({ media, onClick }) {
  const { kind, url, thumb_url, file_name, file_size, duration } = media;
  if (kind === "image") {
    return (
      <button className="tk-media-img" onClick={onClick} type="button">
        <img src={thumb_url || url} alt={file_name || ""} loading="lazy" />
      </button>
    );
  }
  if (kind === "video") {
    return (
      <button className="tk-media-vid" onClick={onClick} type="button">
        {thumb_url ? <img src={thumb_url} alt="" /> : <div className="tk-media-vid-fallback"><Icon name="video" size={24} /></div>}
        <span className="tk-media-vid-play"><Icon name="play-circle" size={26} /></span>
        {duration && <span className="tk-media-vid-dur">{fmtDuration(duration)}</span>}
      </button>
    );
  }
  if (kind === "voice" || kind === "audio") {
    return <VoiceMessage media={media} />;
  }
  // document
  return (
    <a className="tk-media-doc" href={url} target="_blank" rel="noopener noreferrer">
      <span className="tk-media-doc-icon"><Icon name="file-text" size={18} /></span>
      <span className="tk-media-doc-meta">
        <span className="tk-media-doc-name">{file_name || "Документ"}</span>
        <span className="tk-media-doc-size">{fmtBytes(file_size)}</span>
      </span>
      <Icon name="download" size={13} />
    </a>
  );
}

function VoiceMessage({ media }) {
  const { duration, url } = media;
  const [playing, setPlaying] = useState(false);
  const [pos, setPos] = useState(0);
  const [meta, setMeta] = useState({ duration: duration || 0 });
  const [err, setErr] = useState(null);
  const audioRef = useRef(null);
  const waveRef = useRef(null);

  const bars = useMemo(() => {
    const n = 32;
    const seed = Math.round((meta.duration || duration || 1) * 17);
    return Array.from({ length: n }).map((_, i) => {
      const v = Math.sin(i * 0.51 + seed) * Math.cos(i * 0.27 + seed * 1.3);
      return 0.32 + Math.abs(v) * 0.68;
    });
  }, [meta.duration, duration]);

  const onLoadedMeta = () => {
    const a = audioRef.current;
    if (a && Number.isFinite(a.duration)) setMeta({ duration: a.duration });
  };
  const onTime = () => {
    const a = audioRef.current;
    if (!a) return;
    setPos(a.duration ? a.currentTime / a.duration : 0);
  };
  const onEnded = () => { setPlaying(false); setPos(0); };
  const onErr = () => {
    const a = audioRef.current;
    const code = a?.error?.code;
    const codes = { 1: "ABORTED", 2: "NETWORK", 3: "DECODE", 4: "SRC_NOT_SUPPORTED" };
    setErr(codes[code] || ("err " + (code || "?")));
    setPlaying(false);
  };

  const toggle = async () => {
    const a = audioRef.current;
    if (!a) return;
    if (playing) { a.pause(); setPlaying(false); return; }
    try {
      setErr(null);
      a.load();
      await a.play();
      setPlaying(true);
    } catch (e) {
      setErr(e?.message?.slice(0, 60) || "play failed");
      setPlaying(false);
    }
  };

  const seekFromClick = (e) => {
    const a = audioRef.current;
    const wave = waveRef.current;
    if (!a || !wave || !a.duration) return;
    const r = wave.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    a.currentTime = f * a.duration;
    setPos(f);
  };

  if (!url) return <div className="tk-voice muted small">голосовое (нет URL)</div>;

  const totalSec = meta.duration || duration || 0;
  const playedSec = totalSec * pos;
  const shownSec = playing || pos > 0 ? playedSec : totalSec;

  return (
    <>
      <div className="tk-voice">
        <audio
          ref={audioRef}
          src={url}
          preload="metadata"
          onLoadedMetadata={onLoadedMeta}
          onTimeUpdate={onTime}
          onEnded={onEnded}
          onError={onErr}
          style={{ display: "none" }}
        />
        <button className="tk-voice-play" onClick={toggle} type="button" title={playing ? "Пауза" : "Воспроизвести"}>
          <Icon name={playing ? "pause" : "play"} size={14} />
        </button>
        <div className="tk-voice-wave" ref={waveRef} onClick={seekFromClick}>
          {bars.map((h, i) => (
            <span
              key={i}
              className="tk-voice-bar"
              data-played={(i / bars.length) <= pos || undefined}
              style={{ height: Math.round(h * 18) + 6 }}
            />
          ))}
        </div>
        <span className="tk-voice-time">{fmtDuration(shownSec)}</span>
      </div>
      {err && (
        <div className="muted small" style={{ marginTop: 4, color: "var(--bad)" }}>
          Ошибка плеера: {err}. <a href={url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)" }}>скачать файл</a>
        </div>
      )}
    </>
  );
}

/* ──────────────────────────────────────────────────────────
   LIGHTBOX — image/video viewer
   ────────────────────────────────────────────────────────── */
export function Lightbox({ media, index = 0, onClose }) {
  const [i, setI] = useState(index);
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft") setI((v) => Math.max(0, v - 1));
      else if (e.key === "ArrowRight") setI((v) => Math.min(media.length - 1, v + 1));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [media.length, onClose]);
  const cur = media[i];
  if (!cur) return null;
  return (
    <div className="tk-lightbox" onClick={onClose}>
      <button className="tk-lb-close" onClick={onClose}><Icon name="x" size={20} /></button>
      {media.length > 1 && (
        <>
          <button className="tk-lb-nav tk-lb-prev"
            onClick={(e) => { e.stopPropagation(); setI((v) => Math.max(0, v - 1)); }}
            disabled={i === 0}>
            <Icon name="chevron-left" size={24} />
          </button>
          <button className="tk-lb-nav tk-lb-next"
            onClick={(e) => { e.stopPropagation(); setI((v) => Math.min(media.length - 1, v + 1)); }}
            disabled={i === media.length - 1}>
            <Icon name="chevron-right" size={24} />
          </button>
        </>
      )}
      <div className="tk-lb-stage" onClick={(e) => e.stopPropagation()}>
        {cur.kind === "video"
          ? <video src={cur.url} controls autoPlay />
          : <img src={cur.url} alt={cur.file_name || ""} />}
        {(cur.file_name || cur.file_size) && (
          <div className="tk-lb-meta">
            {cur.file_name && <span>{cur.file_name}</span>}
            {cur.file_size && <span className="muted">· {fmtBytes(cur.file_size)}</span>}
            {media.length > 1 && <span className="muted">· {i + 1}/{media.length}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   COMPOSER — chat input with attachments, emoji, templates, voice
   ────────────────────────────────────────────────────────── */
export function Composer({
  templates = [],
  onSend,
  onAddNote,
  user,        // for variable interpolation
  disabled = false,
}) {
  const [html, setHtml] = useState("");
  const [files, setFiles] = useState([]);
  const [showTemplates, setShowTemplates] = useState(false);
  const [showEmoji, setShowEmoji] = useState(false);
  const fileInputRef = useRef(null);

  const stripTags = (s) => (s || "").replace(/<[^>]+>/g, "").trim();

  const interpolate = (raw) => {
    if (!user) return raw;
    return raw
      .replace(/\{user_name\}/g, user.username ? `@${user.username}` : `tg${user.telegram_id || ""}`)
      .replace(/\{plan\}/g, user.plan_name || "—")
      .replace(/\{days_left\}/g, user.days_left != null ? String(user.days_left) : "—")
      .replace(/\{balance\}/g, user.balance != null ? `${user.balance} ₽` : "—");
  };

  const send = useCallback((asNote = false) => {
    const cleaned = htmlForTelegram(html);
    if (!stripTags(cleaned) && files.length === 0) return;
    const payload = { text: cleaned, files: [...files], is_note: asNote };
    if (asNote) onAddNote?.(payload);
    else onSend?.(payload);
    setHtml("");
    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, [html, files, onSend, onAddNote]);

  const pickTemplate = (tpl) => {
    const next = interpolate(tpl.body);
    setHtml((cur) => (cur ? cur + "<p></p>" + next : next));
    setShowTemplates(false);
  };

  const canSend = !disabled && (!!stripTags(html) || files.length > 0);

  const onPickFiles = (e) => {
    const picked = Array.from(e.target.files || []);
    if (!picked.length) return;
    setFiles((cur) => [...cur, ...picked]);
  };
  const removeFile = (idx) => setFiles((cur) => cur.filter((_, i) => i !== idx));

  return (
    <div className="tk-composer">
      <TextEditor
        value={html}
        onChange={setHtml}
        placeholder="Напишите ответ юзеру или внутреннюю заметку…"
        minHeight={70}
      />
      {files.length > 0 && (
        <div className="tk-composer-files">
          {files.map((f, i) => (
            <div key={i} className="tk-composer-file">
              <Icon name={f.type.startsWith("image/") ? "image" : f.type.startsWith("video/") ? "video" : "paperclip"} size={12} />
              <span className="tk-composer-file-name">{f.name}</span>
              <span className="muted small">{Math.round(f.size / 1024)} KB</span>
              <button type="button" className="tk-composer-file-x" onClick={() => removeFile(i)} title="Убрать">×</button>
            </div>
          ))}
        </div>
      )}
      <div className="tk-composer-bar">
        <div className="tk-composer-icons">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            style={{ display: "none" }}
            onChange={onPickFiles}
          />
          <button
            type="button"
            className="tk-comp-btn"
            title="Прикрепить файлы"
            onClick={() => fileInputRef.current?.click()}
          >
            <Icon name="paperclip" size={14} />
          </button>
          <button
            type="button"
            className="tk-comp-btn"
            title="Эмодзи"
            onClick={() => setShowEmoji((v) => !v)}
          >
            <Icon name="smile" size={14} />
          </button>
          <button
            type="button"
            className="tk-comp-btn"
            title={"Шаблоны (" + templates.length + ")"}
            data-active={showTemplates || undefined}
            onClick={() => setShowTemplates((v) => !v)}
          >
            <Icon name="file-text" size={14} />
          </button>
          {showTemplates && (
            <TemplatesPopover
              templates={templates}
              onPick={pickTemplate}
              onClose={() => setShowTemplates(false)}
            />
          )}
          {showEmoji && (
            <EmojiPopover
              onPick={(e) => {
                setHtml((h) => (h || "") + e);
                setShowEmoji(false);
              }}
              onClose={() => setShowEmoji(false)}
            />
          )}
        </div>

        <span className="tk-composer-hint muted small">форматирование в тулбаре редактора</span>

        <div className="tk-composer-actions">
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            title="Внутренняя заметка — видна только админам, юзеру не уходит"
            disabled={!canSend}
            onClick={() => send(true)}
          >
            <Icon name="lock" size={12} /> Заметка
          </button>
          <button
            type="button"
            className="btn btn-sm btn-primary"
            disabled={!canSend}
            onClick={() => send(false)}
          >
            <Icon name="send" size={12} /> Отправить
          </button>
        </div>
      </div>
    </div>
  );
}

function EmojiPopover({ onPick, onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    const off = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    document.addEventListener("mousedown", off);
    return () => document.removeEventListener("mousedown", off);
  }, [onClose]);
  const items = ["👍","🙏","🙂","😊","🤝","🔥","💯","🎉","✅","❌","⚠️","🤔","😅","😎","🙌","💪","🚀","✨","📩","🛠"];
  return (
    <div ref={ref} className="tk-emoji-pop">
      {items.map((e) => (
        <button key={e} className="tk-emoji-btn" type="button" onClick={() => onPick(e)}>{e}</button>
      ))}
    </div>
  );
}

export function TemplatesPopover({ templates, onPick, onClose }) {
  const ref = useRef(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    const off = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    document.addEventListener("mousedown", off);
    return () => document.removeEventListener("mousedown", off);
  }, [onClose]);
  const filtered = q.trim()
    ? templates.filter((t) => (t.title + " " + t.body).toLowerCase().includes(q.toLowerCase()))
    : templates;
  return (
    <div ref={ref} className="tk-templates-pop">
      <div className="tk-templates-search">
        <Icon name="search" size={12} />
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Поиск по шаблонам…"
        />
      </div>
      <div className="tk-templates-list">
        {filtered.length === 0 && <div className="muted small" style={{ padding: 12, textAlign: "center" }}>Ничего не найдено</div>}
        {filtered.map((t) => (
          <button key={t.id} type="button" className="tk-template-item" onClick={() => onPick(t)}>
            <div className="tk-template-head">
              {t.tag && <span className="tk-cat-tag">{t.tag}</span>}
              <span className="tk-template-title">{t.title}</span>
            </div>
            <div className="tk-template-body">{t.body}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   utils
   ────────────────────────────────────────────────────────── */
import { useMemo } from "react";
function fmtBytes(b) {
  if (b == null) return "";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0; let n = Number(b);
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (n >= 100 || i === 0 ? Math.round(n) : n.toFixed(1)) + " " + u[i];
}
function fmtDuration(sec) {
  if (sec == null) return "0:00";
  const s = Math.max(0, Math.round(sec));
  const m = Math.floor(s / 60);
  const r = String(s % 60).padStart(2, "0");
  return `${m}:${r}`;
}

export { fmtBytes, fmtDuration };
