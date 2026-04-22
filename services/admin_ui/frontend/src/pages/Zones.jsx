import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";

export function ZonesPage() {
  const { data, loading, error, refetch } = useQuery(() => api.get("/zones"), { interval: 30000 });
  const items = (data?.items || []).slice().sort((a, b) => (a.sort_order - b.sort_order) || a.code.localeCompare(b.code));

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Зоны</h1>
          <div className="page-subtitle">Регионы для отображения entry-нод в Happ (код + эмодзи + название)</div>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr><th>Код</th><th>Эмодзи</th><th>Название</th><th>Sort</th><th>Статус</th></tr>
          </thead>
          <tbody>
            {items.map((z) => (
              <tr key={z.id}>
                <td className="mono">{z.code}</td>
                <td style={{ fontSize: 20 }}>{z.emoji || "—"}</td>
                <td>{z.name}</td>
                <td className="mono">{z.sort_order}</td>
                <td>{z.is_active ? <span className="chip chip-ok">active</span> : <span className="chip chip-muted">inactive</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
        {(!loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Нет зон.</div>}
      </div>
    </div>
  );
}
