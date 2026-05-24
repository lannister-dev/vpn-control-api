import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client.js";
import { Modal } from "./Modal.jsx";
import { Field } from "./Field.jsx";
import { Icon } from "./Icon.jsx";
import { toast } from "./Toast.jsx";
import { DatePicker } from "./DatePicker.jsx";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function toIsoOrNull(localDateTime) {
  if (!localDateTime) return null;
  const d = new Date(localDateTime);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

export function SubscriptionCreateModal({ userId, userLabel, plans, onClose, onCreated }) {
  const [picked, setPicked] = useState(userId ? { id: userId, label: userLabel } : null);
  const [planId, setPlanId] = useState("");
  const [region, setRegion] = useState("");
  const [maxDevices, setMaxDevices] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [profileKey, setProfileKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [created, setCreated] = useState(null);

  const planOptions = useMemo(() => plans?.items || plans || [], [plans]);

  const submit = async (e) => {
    e?.preventDefault?.();
    if (busy) return;
    setErr("");
    if (!picked?.id) { setErr("Выберите пользователя"); return; }
    const payload = { user_id: picked.id };
    if (planId) payload.plan_id = planId;
    const r = region.trim();
    if (r) payload.preferred_region = r;
    if (maxDevices) {
      const n = Number(maxDevices);
      if (!Number.isInteger(n) || n <= 0 || n > 100) { setErr("Макс. устройств: целое 1–100"); return; }
      payload.max_devices = n;
    }
    if (expiresAt) {
      const iso = toIsoOrNull(expiresAt);
      if (!iso) { setErr("Некорректная дата истечения"); return; }
      payload.expires_at = iso;
    }
    const pk = profileKey.trim();
    if (pk) payload.profile_key = pk;

    setBusy(true);
    try {
      const result = await api.post("/subscriptions", payload);
      toast.ok("Подписка создана");
      setCreated(result);
    } catch (e) {
      const msg = e.status === 404
        ? "Пользователь не найден"
        : (e.message || String(e));
      setErr(msg);
    } finally {
      setBusy(false);
    }
  };

  const finish = () => {
    onCreated?.(created);
    onClose();
  };

  if (created) {
    return (
      <SubscriptionCreatedView created={created} onClose={finish} />
    );
  }

  return (
    <Modal
      title="Новая подписка"
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

        {userId
          ? (
            <Field label="Пользователь">
              <div className="pill" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <Icon name="user" size={12} />
                <span>{userLabel || String(userId).slice(0, 12) + "…"}</span>
              </div>
            </Field>
          )
          : (
            <Field label="Пользователь" hint="UUID или поиск по username / telegram">
              <UserPicker picked={picked} onPick={setPicked} />
            </Field>
          )
        }

        <Field label="Тариф" hint="опционально (без тарифа = пробный)">
          <select value={planId} onChange={(e) => setPlanId(e.target.value)}>
            <option value="">— без тарифа —</option>
            {planOptions.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </Field>

        <Field label="Регион" hint="опционально, например fr / de / fi">
          <input type="text" value={region} onChange={(e) => setRegion(e.target.value)} maxLength={16} placeholder="auto" />
        </Field>

        <Field label="Макс. устройств" hint="опционально, 1–100">
          <input type="number" min="1" max="100" step="1" value={maxDevices} onChange={(e) => setMaxDevices(e.target.value)} placeholder="из тарифа" />
        </Field>

        <Field label="Истекает" hint="опционально, локальное время">
          <DatePicker mode="datetime" value={expiresAt} onChange={setExpiresAt} placeholder="Не указано" />
        </Field>

        <Field label="Profile key" hint="опционально, для разделения профилей">
          <input type="text" value={profileKey} onChange={(e) => setProfileKey(e.target.value)} maxLength={64} />
        </Field>

        <button type="submit" hidden />
      </form>
    </Modal>
  );
}

function SubscriptionCreatedView({ created, onClose }) {
  const copy = (text, label) => {
    if (!text) return;
    navigator.clipboard?.writeText(text).then(
      () => toast.ok(`${label} скопирован`),
      () => toast.bad("Не удалось скопировать"),
    );
  };

  const expires = created.expires_at
    ? new Date(created.expires_at).toLocaleString("ru-RU")
    : "бессрочно";

  return (
    <Modal
      title="Подписка создана"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={() => copy(created.subscription_url, "Ссылка")}>
            <Icon name="copy" size={13} /> Копировать ссылку
          </button>
          <button className="btn btn-primary" onClick={onClose}>Готово</button>
        </>
      }
    >
      <div className="muted small" style={{ marginBottom: 12 }}>
        Передайте пользователю ссылку — она открывается в его VPN-приложении и подключает подписку.
        Истекает: <span className="mono">{expires}</span>.
      </div>

      <Field label="Ссылка для подключения">
        <div style={{ display: "flex", gap: 6 }}>
          <input
            type="text"
            readOnly
            value={created.subscription_url}
            onFocus={(e) => e.target.select()}
            style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}
          />
          <button className="btn" onClick={() => copy(created.subscription_url, "Ссылка")}>
            <Icon name="copy" size={13} />
          </button>
        </div>
      </Field>

      <Field label="Token" hint="нужен только для отладки">
        <div style={{ display: "flex", gap: 6 }}>
          <input
            type="text"
            readOnly
            value={created.token}
            onFocus={(e) => e.target.select()}
            style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}
          />
          <button className="btn" onClick={() => copy(created.token, "Token")}>
            <Icon name="copy" size={13} />
          </button>
        </div>
      </Field>

      <Field label="ID подписки">
        <div style={{ display: "flex", gap: 6 }}>
          <input
            type="text"
            readOnly
            value={created.id}
            onFocus={(e) => e.target.select()}
            style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}
          />
          <button className="btn" onClick={() => copy(created.id, "ID")}>
            <Icon name="copy" size={13} />
          </button>
        </div>
      </Field>
    </Modal>
  );
}

function UserPicker({ picked, onPick }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    if (picked) return;
    if (timer.current) clearTimeout(timer.current);
    const query = q.trim();
    if (!query) { setResults([]); return; }
    if (UUID_RE.test(query)) { setResults([]); return; }
    timer.current = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await api.get(`/users?search=${encodeURIComponent(query)}&limit=8`);
        setResults(data?.items || []);
        setOpen(true);
      } catch { setResults([]); }
      finally { setLoading(false); }
    }, 250);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [q, picked]);

  if (picked) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className="pill" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Icon name="user" size={12} />
          <span>{picked.label || (picked.username ? `@${picked.username}` : `tg:${picked.telegram_id || picked.id}`)}</span>
        </span>
        <button type="button" className="btn btn-ghost" onClick={() => { onPick(null); setQ(""); }}>
          Сменить
        </button>
      </div>
    );
  }

  const onChange = (e) => {
    const v = e.target.value;
    setQ(v);
    const query = v.trim();
    if (UUID_RE.test(query)) {
      onPick({ id: query, label: String(query).slice(0, 12) + "…" });
    }
  };

  return (
    <div style={{ position: "relative" }}>
      <input
        type="text"
        value={q}
        onChange={onChange}
        autoFocus
        placeholder="UUID, username или telegram ID"
        onFocus={() => results.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && (loading || results.length > 0) && (
        <div className="dropdown" style={{
          position: "absolute", top: "100%", left: 0, right: 0, marginTop: 4,
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6,
          boxShadow: "0 4px 14px rgba(0,0,0,.18)", zIndex: 10, maxHeight: 240, overflowY: "auto",
        }}>
          {loading && <div className="muted small" style={{ padding: 10 }}>Поиск…</div>}
          {!loading && results.map((u) => (
            <div
              key={u.id}
              onMouseDown={() => onPick({
                id: u.id,
                username: u.username,
                telegram_id: u.telegram_id,
                label: u.username ? `@${u.username}` : `tg:${u.telegram_id}`,
              })}
              style={{ padding: "8px 10px", cursor: "pointer", display: "flex", justifyContent: "space-between", gap: 8 }}
              className="dropdown-item"
            >
              <span>{u.username ? `@${u.username}` : <span className="muted">—</span>}</span>
              <span className="mono small muted">{u.telegram_id}</span>
            </div>
          ))}
          {!loading && !results.length && q.trim() && (
            <div className="muted small" style={{ padding: 10 }}>Ничего не найдено</div>
          )}
        </div>
      )}
    </div>
  );
}
