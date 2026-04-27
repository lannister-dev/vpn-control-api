import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { Modal } from "../components/Modal.jsx";
import { Field } from "../components/Field.jsx";
import { toast } from "../components/Toast.jsx";
import { UserDrawer } from "../components/UserDrawer.jsx";

function fmtDate(s) {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("ru-RU"); } catch { return s; }
}

export function UsersPage() {
  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("");
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);

  const qs = new URLSearchParams({ limit: "100" });
  if (search) qs.set("search", search);
  if (activeFilter) qs.set("is_active", activeFilter);

  const { data, loading, error, refetch } = useQuery(
    () => api.get(`/users?${qs.toString()}`),
    { interval: 30000, deps: [search, activeFilter] },
  );
  const items = data?.items || [];

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Пользователи</h1>
          <div className="page-subtitle">
            {data?.total ?? 0} всего{activeFilter === "true" ? " (только активные)" : activeFilter === "false" ? " (только отключённые)" : ""}
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={refetch}><Icon name="refresh" size={13} /> Обновить</button>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            <Icon name="plus" size={13} /> Создать
          </button>
        </div>
      </div>

      <div className="filterbar">
        <div className="input-search-wrap">
          <Icon name="search" size={13} className="input-search-icon" />
          <input className="input" placeholder="Поиск UUID / telegram / username…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="select" value={activeFilter} onChange={(e) => setActiveFilter(e.target.value)}>
          <option value="">Любой статус</option>
          <option value="true">Активные</option>
          <option value="false">Отключённые</option>
        </select>
        <div style={{ marginLeft: "auto" }}>
          <span className="muted text-xs">{items.length} / {data?.total ?? 0}</span>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              <th>Пользователь</th>
              <th>Telegram</th>
              <th style={{ textAlign: "right" }}>Баланс</th>
              <th>Создан</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            {items.map((u) => {
              const initials = (u.username || `tg${u.telegram_id}`).slice(0, 2).toUpperCase();
              return (
                <tr key={u.id} style={{ cursor: "pointer" }} onClick={() => setSelected(u)}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div className="user-avatar" style={{ width: 28, height: 28, fontSize: 11 }}>{initials}</div>
                      <div>
                        <div style={{ fontWeight: 500 }}>
                          {u.username ? `@${u.username}` : <span className="muted">—</span>}
                        </div>
                        <div className="mono muted" style={{ fontSize: 11 }}>{String(u.id).slice(0, 12)}…</div>
                      </div>
                    </div>
                  </td>
                  <td className="mono">{u.telegram_id}</td>
                  <td className="tbl-num mono">{u.balance ?? 0} ₽</td>
                  <td className="small muted">{fmtDate(u.created_at)}</td>
                  <td>{u.is_active ? <span className="pill ok">active</span> : <span className="pill">disabled</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Нет пользователей.</div>}
      </div>

      {selected && <UserDrawer user={selected} onClose={() => setSelected(null)} />}
      {creating && (
        <UserCreateModal
          onClose={() => setCreating(false)}
          onCreated={(u) => { setCreating(false); refetch(); setSelected(u); }}
        />
      )}
    </div>
  );
}

function UserCreateModal({ onClose, onCreated }) {
  const [f, setF] = useState({ telegram_id: "", username: "", tag: "", description: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));

  const submit = async (e) => {
    e?.preventDefault?.();
    if (busy) return;
    setErr("");
    const tgRaw = String(f.telegram_id).trim();
    if (!tgRaw) { setErr("Telegram ID обязателен"); return; }
    const tg = Number(tgRaw);
    if (!Number.isInteger(tg) || tg <= 0) { setErr("Telegram ID должен быть положительным целым числом"); return; }
    const payload = { telegram_id: tg };
    const username = f.username.trim().replace(/^@/, "");
    if (username) payload.username = username;
    const tag = f.tag.trim();
    if (tag) payload.tag = tag;
    const description = f.description.trim();
    if (description) payload.description = description;
    setBusy(true);
    try {
      const created = await api.post("/users", payload);
      toast.ok("Пользователь создан");
      onCreated(created);
    } catch (e) {
      const msg = e.status === 409
        ? "Пользователь с таким Telegram ID уже существует"
        : (e.message || String(e));
      setErr(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Новый пользователь"
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
        <Field label="Telegram ID" hint="обязательно">
          <input
            type="number"
            inputMode="numeric"
            min="1"
            step="1"
            autoFocus
            value={f.telegram_id}
            onChange={set("telegram_id")}
            placeholder="например, 123456789"
          />
        </Field>
        <Field label="Username" hint="без @, опционально">
          <input type="text" value={f.username} onChange={set("username")} placeholder="username" />
        </Field>
        <Field label="Тег" hint="опционально">
          <input type="text" value={f.tag} onChange={set("tag")} placeholder="vip / partner / …" />
        </Field>
        <Field label="Описание" hint="опционально">
          <textarea rows={3} value={f.description} onChange={set("description")} />
        </Field>
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}
