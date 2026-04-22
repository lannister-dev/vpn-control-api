import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";

export function UsersPage() {
  const [search, setSearch] = useState("");
  const { data, loading, error } = useQuery(
    () => api.get("/users?limit=100" + (search ? `&search=${encodeURIComponent(search)}` : "")),
    { interval: 30000, deps: [search] },
  );
  const items = data?.items || [];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Пользователи</h1>
          <div className="page-subtitle">Зарегистрированные юзеры, их подписки и устройства</div>
        </div>
      </div>

      <div className="filter-row">
        <input className="input" placeholder="Поиск по UUID / telegram / username" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr><th>ID</th><th>Telegram</th><th>Username</th><th>Создан</th><th>Активен</th></tr>
          </thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id}>
                <td className="mono small">{u.id.slice(0, 12)}…</td>
                <td className="mono">{u.telegram_id || "—"}</td>
                <td>{u.username || "—"}</td>
                <td className="small muted">{fmtDate(u.created_at)}</td>
                <td>{u.is_active ? <span className="chip chip-ok">active</span> : <span className="chip chip-muted">off</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Нет пользователей.</div>}
      </div>
    </div>
  );
}

function fmtDate(s) {
  if (!s) return "";
  try { return new Date(s).toLocaleString(); } catch { return s; }
}
