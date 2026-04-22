import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { Spark } from "../components/Spark.jsx";

function spark(seed, len = 20, base = 50, vol = 30) {
  let x = seed || 7;
  const out = [];
  for (let i = 0; i < len; i++) {
    x = (x * 9301 + 49297) % 233280;
    out.push(base + ((x / 233280) - 0.5) * vol * 2);
  }
  return out;
}

export function UsersPage() {
  const [search, setSearch] = useState("");
  const { data, loading, error, refetch } = useQuery(
    () => api.get("/users?limit=100" + (search ? `&search=${encodeURIComponent(search)}` : "")),
    { interval: 30000, deps: [search] },
  );
  const items = data?.items || [];

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Пользователи</h1>
          <div className="page-subtitle">{items.length} юзеров · telegram / username / подписки</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={refetch}><Icon name="refresh" size={13} /> Обновить</button>
          <button className="btn"><Icon name="download" size={13} /> Экспорт</button>
        </div>
      </div>

      <div className="filterbar">
        <div className="input-search-wrap">
          <Icon name="search" size={13} className="input-search-icon" />
          <input className="input" placeholder="Поиск UUID / telegram / username…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div style={{ marginLeft: "auto" }}>
          <span className="muted text-xs">{items.length} записей</span>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              <th>Telegram</th>
              <th>Username</th>
              <th>UUID</th>
              <th>Создан</th>
              <th>Статус</th>
              <th style={{ width: 120 }}>Активность</th>
            </tr>
          </thead>
          <tbody>
            {items.map((u) => {
              const seed = parseInt(String(u.id).replace(/-/g, "").slice(0, 6), 16) || 7;
              return (
                <tr key={u.id}>
                  <td className="mono">{u.telegram_id || "—"}</td>
                  <td style={{ fontWeight: 500 }}>{u.username || <span className="muted">—</span>}</td>
                  <td className="mono muted" style={{ fontSize: 11 }}>{String(u.id).slice(0, 12)}…</td>
                  <td className="muted small">{fmtDate(u.created_at)}</td>
                  <td>{u.is_active ? <span className="pill ok">active</span> : <span className="pill">off</span>}</td>
                  <td><Spark data={spark(seed, 20, 50, 30)} color="var(--accent)" w={90} h={22} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Нет пользователей.</div>}
      </div>
    </div>
  );
}

function fmtDate(s) {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString(); } catch { return s; }
}
