import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Modal } from "../components/Modal.jsx";
import { Field } from "../components/Field.jsx";
import { Icon } from "../components/Icon.jsx";
import { toast } from "../components/Toast.jsx";

const ROLE_TONE = { admin: "bad", operator: "warn", viewer: "ok" };

const fmt = (s) => s ? new Date(s).toLocaleDateString() : "—";

export function AdminUsersPage() {
  const { data, loading, error, refetch } = useQuery(() => api.get("/auth/admin/users?limit=100"), { interval: 60000 });
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);
  const items = data?.items || [];

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Админы</h1>
          <div className="page-subtitle">Пользователи панели, роли и статусы</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            <Icon name="plus" size={13} /> Создать
          </button>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card">
        <table className="tbl">
          <thead><tr><th>Username</th><th>Роль</th><th>Telegram</th><th>Создан</th><th>Статус</th><th></th></tr></thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id}>
                <td style={{ fontWeight: 500 }}>{u.username}</td>
                <td><span className={"pill " + (ROLE_TONE[u.role] || "")}>{u.role}</span></td>
                <td className="mono">{u.telegram_id || "—"}</td>
                <td className="small muted">{fmt(u.created_at)}</td>
                <td>{u.is_active ? <span className="pill ok">active</span> : <span className="pill">disabled</span>}</td>
                <td className="row-actions"><button className="row-btn" onClick={() => setEditing(u)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {(loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
      </div>

      {creating && <AdminUserCreate onClose={() => { setCreating(false); refetch(); }} />}
      {editing && <AdminUserEdit user={editing} onClose={() => { setEditing(null); refetch(); }} />}
    </div>
  );
}

function AdminUserCreate({ onClose }) {
  const [f, setF] = useState({ username: "", password: "", telegram_id: "", role: "viewer" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const save = async () => {
    setBusy(true); setErr("");
    try {
      if (!f.username) throw new Error("Username обязателен");
      const payload = { username: f.username.trim(), role: f.role };
      if (f.password) payload.password = f.password;
      if (f.telegram_id) payload.telegram_id = Number(f.telegram_id);
      await api.post("/auth/admin/users", payload);
      toast.ok("Пользователь создан");
      onClose();
    } catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));
  return (
    <Modal
      title="Новый admin user"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose}>Отмена</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>Создать</button>
        </>
      }
    >
      {err && <div className="form-error">{err}</div>}
      <Field label="Username"><input type="text" value={f.username} onChange={set("username")} /></Field>
      <Field label="Пароль" hint="мин. 8 символов"><input type="password" value={f.password} onChange={set("password")} /></Field>
      <Field label="Telegram ID" hint="опционально"><input type="number" value={f.telegram_id} onChange={set("telegram_id")} /></Field>
      <Field label="Роль">
        <select value={f.role} onChange={set("role")}>
          <option value="viewer">viewer</option>
          <option value="operator">operator</option>
          <option value="admin">admin</option>
        </select>
      </Field>
    </Modal>
  );
}

function AdminUserEdit({ user, onClose }) {
  const [role, setRole] = useState(user.role);
  const [active, setActive] = useState(user.is_active);
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const save = async () => {
    setBusy(true); setErr("");
    try {
      await api.patch(`/auth/admin/users/${user.id}`, { role, is_active: active });
      toast.ok("Обновлено");
      onClose();
    } catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  const resetPass = async () => {
    if (!newPassword || newPassword.length < 8) { setErr("Пароль минимум 8 символов"); return; }
    setBusy(true); setErr("");
    try {
      await api.post(`/auth/admin/users/${user.id}/reset-password`, { new_password: newPassword });
      setNewPassword("");
      toast.ok("Пароль сброшен");
    } catch (e) { setErr(e.message || String(e)); toast.bad(e.message || String(e)); }
    finally { setBusy(false); }
  };

  const revokeSessions = async () => {
    if (!confirm("Отозвать все сессии этого пользователя?")) return;
    setBusy(true);
    try {
      const r = await api.post(`/auth/admin/users/${user.id}/revoke-sessions`);
      toast.ok(`Отозвано сессий: ${r.revoked}`);
    } catch (e) { setErr(e.message || String(e)); toast.bad(e.message || String(e)); }
    finally { setBusy(false); }
  };

  const del = async () => {
    if (!confirm(`Удалить пользователя ${user.username}? Необратимо.`)) return;
    setBusy(true);
    try { await api.del(`/auth/admin/users/${user.id}`); onClose(); }
    catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <Modal
      title={`Админ: ${user.username}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-danger" onClick={del} disabled={busy} style={{ marginRight: "auto" }}>Удалить</button>
          <button className="btn btn-ghost" onClick={onClose}>Отмена</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>Сохранить</button>
        </>
      }
    >
      {err && <div className="form-error">{err}</div>}
      <Field label="Роль">
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="viewer">viewer</option>
          <option value="operator">operator</option>
          <option value="admin">admin</option>
        </select>
      </Field>
      <label className="form-check">
        <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Активен
      </label>
      <hr style={{ border: 0, borderTop: "1px solid var(--border)", margin: "16px 0" }} />
      <Field label="Сброс пароля" hint="мин. 8 символов">
        <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
      </Field>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-ghost" onClick={resetPass} disabled={busy || !newPassword}>Сбросить пароль</button>
        <button className="btn btn-ghost" onClick={revokeSessions} disabled={busy}>Отозвать сессии</button>
      </div>
    </Modal>
  );
}
