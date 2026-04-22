import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";

export function OpsPage() {
  const status = useQuery(() => api.get("/admin/status"), { interval: 15000 });
  const readiness = useQuery(() => api.get("/admin/readiness"), { interval: 15000 });

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Операции</h1>
          <div className="page-subtitle">Быстрые ссылки и служебные действия</div>
        </div>
      </div>

      <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        <div className="kpi-card">
          <div className="kpi-label">Readiness</div>
          <div className="kpi-value" style={{ fontSize: 22 }}>
            {readiness.data?.ready ? <span className="chip chip-ok">ready</span> : <span className="chip chip-bad">not ready</span>}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Статус собран</div>
          <div className="kpi-value small muted" style={{ fontSize: 13 }}>{status.data?.generated_at ? new Date(status.data.generated_at).toLocaleString() : "—"}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Ноды</div>
          <div className="kpi-value">{status.data?.nodes?.length ?? "—"}</div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <div className="muted">
          Полный ops-UI (миграции, probe политики, smart-route health) пока доступен в старой панели по адресу <a href="/" target="_blank" rel="noreferrer">/</a> → таб «Операции».
        </div>
      </div>
    </div>
  );
}
