import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { UserDrawer } from "../components/UserDrawer.jsx";

function fmtDate(s) {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("ru-RU"); } catch { return s; }
}

export function UsersPage() {
  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("");
  const [selected, setSelected] = useState(null);

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
    </div>
  );
}
