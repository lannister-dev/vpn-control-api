import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";

const ROLE_TONE = { admin: "bad", operator: "warn", viewer: "ok" };

export function AdminUsersPage() {
  const { data, loading, error } = useQuery(() => api.get("/auth/admin/users?limit=100"), { interval: 60000 });
  const items = data?.items || [];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Админы</h1>
          <div className="page-subtitle">Пользователи панели, роли и статусы</div>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr><th>Username</th><th>Роль</th><th>Telegram</th><th>Создан</th><th>Статус</th></tr>
          </thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id}>
                <td><strong>{u.username}</strong></td>
                <td><span className={"chip chip-" + (ROLE_TONE[u.role] || "muted")}>{u.role}</span></td>
                <td className="mono">{u.telegram_id || "—"}</td>
                <td className="small muted">{u.created_at ? new Date(u.created_at).toLocaleString() : "—"}</td>
                <td>{u.is_active ? <span className="chip chip-ok">active</span> : <span className="chip chip-muted">disabled</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
      </div>
    </div>
  );
}
