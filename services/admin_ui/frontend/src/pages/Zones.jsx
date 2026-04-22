import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Modal } from "../components/Modal.jsx";
import { Field, Row } from "../components/Field.jsx";
import { Icon } from "../components/Icon.jsx";

export function ZonesPage() {
  const { data, loading, error, refetch } = useQuery(() => api.get("/zones"), { interval: 30000 });
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);

  const items = (data?.items || []).slice().sort(
    (a, b) => (a.sort_order - b.sort_order) || a.code.localeCompare(b.code),
  );

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Зоны</h1>
          <div className="page-subtitle">Регионы для отображения entry-нод в Happ (код + эмодзи + название)</div>
        </div>
        <div className="page-head-actions">
          <button className="btn-primary" onClick={() => setCreating(true)}>
            <Icon name="plus" size={13} /> Создать зону
          </button>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr><th>Код</th><th>Эмодзи</th><th>Название</th><th>Sort</th><th>Статус</th><th></th></tr>
          </thead>
          <tbody>
            {items.map((z) => (
              <tr key={z.id}>
                <td className="mono">{z.code}</td>
                <td style={{ fontSize: 20 }}>{z.emoji || "—"}</td>
                <td>{z.name}</td>
                <td className="mono">{z.sort_order}</td>
                <td>{z.is_active ? <span className="chip chip-ok">active</span> : <span className="chip chip-muted">inactive</span>}</td>
                <td><button className="row-btn" onClick={() => setEditing(z)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {(loading && !items.length) && <div className="muted" style={{ padding: 14 }}>Загрузка…</div>}
      </div>

      {creating && <ZoneForm onClose={() => { setCreating(false); refetch(); }} />}
      {editing && <ZoneForm zone={editing} onClose={() => { setEditing(null); refetch(); }} />}
    </div>
  );
}

function ZoneForm({ zone, onClose }) {
  const isEdit = !!zone;
  const [code, setCode] = useState(zone?.code || "");
  const [name, setName] = useState(zone?.name || "");
  const [emoji, setEmoji] = useState(zone?.emoji || "");
  const [sortOrder, setSortOrder] = useState(zone?.sort_order ?? 0);
  const [isActive, setIsActive] = useState(zone ? zone.is_active : true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const save = async () => {
    setBusy(true); setErr("");
    try {
      const payload = { name: name.trim(), emoji: emoji.trim(), sort_order: Number(sortOrder) || 0 };
      if (isEdit) {
        payload.is_active = isActive;
        await api.patch(`/zones/${encodeURIComponent(zone.code)}`, payload);
      } else {
        if (!code) throw new Error("Код обязателен");
        await api.post("/zones", { ...payload, code: code.trim().toLowerCase() });
      }
      onClose();
    } catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  const deactivate = async () => {
    if (!confirm(`Деактивировать зону ${zone.code}?`)) return;
    setBusy(true); setErr("");
    try { await api.del(`/zones/${encodeURIComponent(zone.code)}`); onClose(); }
    catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <Modal
      title={isEdit ? `Зона: ${zone.code}` : "Новая зона"}
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
      <Field label="Код" hint={isEdit ? "неизменяем" : "2–16 символов, lowercase"}>
        <input type="text" value={code} onChange={(e) => setCode(e.target.value)} disabled={isEdit} placeholder="europe" />
      </Field>
      <Field label="Эмодзи">
        <input type="text" value={emoji} onChange={(e) => setEmoji(e.target.value)} placeholder="🇪🇺" />
      </Field>
      <Field label="Название">
        <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Порядок сортировки">
        <input type="number" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} />
      </Field>
      {isEdit && (
        <label className="form-check">
          <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} /> Активна
        </label>
      )}
    </Modal>
  );
}
