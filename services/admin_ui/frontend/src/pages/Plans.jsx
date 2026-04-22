import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Modal } from "../components/Modal.jsx";
import { Field, Row } from "../components/Field.jsx";
import { Icon } from "../components/Icon.jsx";

export function PlansPage() {
  const { data, loading, error, refetch } = useQuery(() => api.get("/plans"), { interval: 30000 });
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);
  const items = data?.items || [];

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Тарифы</h1>
          <div className="page-subtitle">Планы подписок, флаги умной маршрутизации и whitelist</div>
        </div>
        <div className="page-head-actions">
          <button className="btn-primary" onClick={() => setCreating(true)}>
            <Icon name="plus" size={13} /> Создать тариф
          </button>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Название</th><th>Трафик</th><th>Сброс</th><th>Устройства</th><th>Длительность</th><th>Флаги</th><th>Статус</th><th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.id}>
                <td><strong>{p.name}</strong><div className="small muted">{p.description || ""}</div></td>
                <td className="mono">{formatBytes(p.traffic_limit_bytes)}</td>
                <td className="small">{p.reset_strategy}</td>
                <td className="mono">{p.included_devices}/{p.max_devices}</td>
                <td className="mono">{p.duration_days} дн.</td>
                <td>
                  {p.entry_relay_enabled && <span className="chip chip-ok" style={{ marginRight: 4 }}>Entry</span>}
                  {p.whitelist_enabled && <span className="chip chip-ok">WL</span>}
                </td>
                <td>{p.is_active ? <span className="chip chip-ok">active</span> : <span className="chip chip-muted">inactive</span>}</td>
                <td><button className="row-btn" onClick={() => setEditing(p)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {(loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
      </div>

      {creating && <PlanForm onClose={() => { setCreating(false); refetch(); }} />}
      {editing && <PlanForm plan={editing} onClose={() => { setEditing(null); refetch(); }} />}
    </div>
  );
}

function PlanForm({ plan, onClose }) {
  const isEdit = !!plan;
  const initial = {
    name: plan?.name || "",
    description: plan?.description || "",
    traffic_gb: plan ? Math.round((plan.traffic_limit_bytes || 0) / (1024 ** 3)) : 0,
    reset_strategy: plan?.reset_strategy || "MONTH",
    max_devices: plan?.max_devices ?? 5,
    included_devices: plan?.included_devices ?? 1,
    duration_days: plan?.duration_days ?? 30,
    price_rub: plan?.price_rub ?? 0,
    device_price_rub: plan?.device_price_rub ?? 0,
    is_active: plan ? plan.is_active : true,
    entry_relay_enabled: plan?.entry_relay_enabled || false,
    whitelist_enabled: plan?.whitelist_enabled || false,
  };
  const [f, setF] = useState(initial);
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const save = async () => {
    setBusy(true); setErr("");
    try {
      const payload = {
        name: f.name.trim(),
        description: f.description.trim() || null,
        traffic_limit_bytes: Math.round(Number(f.traffic_gb) * 1024 ** 3),
        reset_strategy: f.reset_strategy,
        max_devices: Number(f.max_devices) || 1,
        included_devices: Number(f.included_devices) || 1,
        duration_days: Number(f.duration_days) || 30,
        price_rub: Number(f.price_rub) || 0,
        device_price_rub: Number(f.device_price_rub) || 0,
        is_active: !!f.is_active,
        entry_relay_enabled: !!f.entry_relay_enabled,
        whitelist_enabled: !!f.whitelist_enabled,
      };
      if (isEdit) await api.patch(`/plans/${plan.id}`, payload);
      else {
        if (!payload.name) throw new Error("Название обязательно");
        await api.post("/plans", payload);
      }
      onClose();
    } catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  const deactivate = async () => {
    if (!confirm(`Деактивировать тариф ${plan.name}?`)) return;
    setBusy(true);
    try { await api.del(`/plans/${plan.id}`); onClose(); }
    catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <Modal
      title={isEdit ? `Тариф: ${plan.name}` : "Новый тариф"}
      onClose={onClose}
      footer={
        <>
          {isEdit && <button className="btn-danger" onClick={deactivate} disabled={busy} style={{ marginRight: "auto" }}>Деактивировать</button>}
          <button className="btn-ghost" onClick={onClose}>Отмена</button>
          <button className="btn-primary" onClick={save} disabled={busy}>{isEdit ? "Сохранить" : "Создать"}</button>
        </>
      }
    >
      {err && <div className="form-error">{err}</div>}
      <Field label="Название"><input type="text" value={f.name} onChange={set("name")} /></Field>
      <Field label="Описание"><input type="text" value={f.description} onChange={set("description")} /></Field>
      <div className="form-row">
        <Field label="Трафик, GB" hint="0 = безлимит"><input type="number" min={0} value={f.traffic_gb} onChange={set("traffic_gb")} /></Field>
        <Field label="Сброс">
          <select value={f.reset_strategy} onChange={set("reset_strategy")}>
            <option value="NO_RESET">Без сброса</option>
            <option value="DAY">Ежедневно</option>
            <option value="WEEK">Еженедельно</option>
            <option value="MONTH">Ежемесячно</option>
          </select>
        </Field>
      </div>
      <div className="form-row">
        <Field label="Устройств max"><input type="number" min={1} value={f.max_devices} onChange={set("max_devices")} /></Field>
        <Field label="Вкл. устройств"><input type="number" min={1} value={f.included_devices} onChange={set("included_devices")} /></Field>
      </div>
      <div className="form-row">
        <Field label="Длительность, дней"><input type="number" min={1} value={f.duration_days} onChange={set("duration_days")} /></Field>
        <Field label="Цена, ₽"><input type="number" min={0} value={f.price_rub} onChange={set("price_rub")} /></Field>
      </div>
      <Field label="Цена доп. устройства, ₽"><input type="number" min={0} value={f.device_price_rub} onChange={set("device_price_rub")} /></Field>
      <label className="form-check"><input type="checkbox" checked={f.entry_relay_enabled} onChange={set("entry_relay_enabled")} /> Умная маршрутизация (entry pool)</label>
      <label className="form-check" style={{ marginTop: 6 }}><input type="checkbox" checked={f.whitelist_enabled} onChange={set("whitelist_enabled")} /> Whitelist-маршруты (обход глушилок)</label>
      <label className="form-check" style={{ marginTop: 6 }}><input type="checkbox" checked={f.is_active} onChange={set("is_active")} /> Активен</label>
    </Modal>
  );
}

function formatBytes(n) {
  if (!n) return "Unlimited";
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`;
  return `${(n / 1024 / 1024).toFixed(0)} MB`;
}
