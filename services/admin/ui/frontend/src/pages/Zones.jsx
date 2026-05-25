import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Modal } from "../components/Modal.jsx";
import { Field } from "../components/Field.jsx";
import { Icon } from "../components/Icon.jsx";
import { toast } from "../components/Toast.jsx";
import { Empty, SkeletonRows } from "../components/Empty.jsx";

export function ZonesPage() {
  const { data, loading, error, refetch } = useQuery(() => api.get("/zones"), { interval: 30000 });
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);

  const items = (data?.items || []).slice().sort(
    (a, b) => (a.sort_order - b.sort_order) || a.code.localeCompare(b.code),
  );

  // ── Drag-and-drop ordering ─────────────────────────────────
  const [reordering, setReordering] = useState(false);
  const [draft, setDraft] = useState(null);       // local override during DnD
  const [dragIdx, setDragIdx] = useState(null);
  const [overIdx, setOverIdx] = useState(null);
  const [saving, setSaving] = useState(false);

  const view = reordering && draft ? draft : items;

  useEffect(() => {
    if (reordering && !draft) setDraft(items);
  }, [reordering, items, draft]);

  const onDragStart = (idx) => (e) => {
    setDragIdx(idx);
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", String(idx));
  };
  const onDragOver = (idx) => (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (overIdx !== idx) setOverIdx(idx);
  };
  const onDrop = (idx) => (e) => {
    e.preventDefault();
    if (dragIdx === null || dragIdx === idx) {
      setDragIdx(null); setOverIdx(null);
      return;
    }
    const next = (draft || items).slice();
    const [moved] = next.splice(dragIdx, 1);
    next.splice(idx, 0, moved);
    setDraft(next);
    setDragIdx(null); setOverIdx(null);
  };
  const onDragEnd = () => { setDragIdx(null); setOverIdx(null); };

  const cancelReorder = () => { setReordering(false); setDraft(null); };
  const saveReorder = async () => {
    if (!draft) { setReordering(false); return; }
    setSaving(true);
    try {
      await api.post("/zones/reorder", { codes: draft.map((z) => z.code) });
      toast.ok("Порядок зон сохранён");
      setReordering(false); setDraft(null);
      refetch();
    } catch (e) {
      toast.bad(e?.message || "Не удалось сохранить порядок");
    }
    finally { setSaving(false); }
  };

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Зоны</h1>
          <div className="page-subtitle">Регионы для отображения entry-нод в Happ (код + эмодзи + название)</div>
        </div>
        <div className="page-head-actions">
          {reordering ? (
            <>
              <button className="btn btn-ghost" onClick={cancelReorder} disabled={saving}>
                Отмена
              </button>
              <button className="btn btn-primary" onClick={saveReorder} disabled={saving}>
                <Icon name="check" size={13} /> Сохранить порядок
              </button>
            </>
          ) : (
            <>
              <button className="btn" onClick={() => setReordering(true)} disabled={items.length < 2}>
                <Icon name="menu" size={13} /> Изменить порядок
              </button>
              <button className="btn btn-primary" onClick={() => setCreating(true)}>
                <Icon name="plus" size={13} /> Создать зону
              </button>
            </>
          )}
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              {reordering && <th style={{ width: 28 }}></th>}
              <th>Код</th>
              <th>Эмодзи</th>
              <th>Название</th>
              <th style={{ textAlign: "right" }}>Sort</th>
              <th>Статус</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(loading && !items.length) && <SkeletonRows count={3} cols={reordering ? 7 : 6} />}
            {view.map((z, idx) => {
              const isDragging = reordering && dragIdx === idx;
              const isOver = reordering && overIdx === idx && dragIdx !== idx;
              return (
                <tr
                  key={z.id}
                  draggable={reordering}
                  onDragStart={reordering ? onDragStart(idx) : undefined}
                  onDragOver={reordering ? onDragOver(idx) : undefined}
                  onDrop={reordering ? onDrop(idx) : undefined}
                  onDragEnd={reordering ? onDragEnd : undefined}
                  style={{
                    cursor: reordering ? "grab" : undefined,
                    opacity: isDragging ? 0.4 : 1,
                    boxShadow: isOver ? "inset 0 2px 0 var(--accent)" : undefined,
                    background: isOver ? "var(--accent-soft)" : undefined,
                  }}
                >
                  {reordering && (
                    <td style={{ color: "var(--text-muted)", cursor: "grab", textAlign: "center" }}>
                      <Icon name="menu" size={14} />
                    </td>
                  )}
                  <td className="mono">{z.code}</td>
                  <td style={{ fontSize: 20 }}>{z.emoji || "—"}</td>
                  <td style={{ fontWeight: 500 }}>{z.name}</td>
                  <td className="tbl-num mono">{reordering ? (idx + 1) * 10 : z.sort_order}</td>
                  <td>{z.is_active ? <span className="pill ok">active</span> : <span className="pill">inactive</span>}</td>
                  <td className="row-actions">
                    {!reordering && <button className="row-btn" onClick={() => setEditing(z)}>Edit</button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(!loading && !items.length) && <Empty icon="globe" title="Зон нет" hint="Создайте первую зону, чтобы привязывать к ней entry-ноды." />}
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
      const payload = {
        name: name.trim(),
        emoji: emoji.trim(),
        sort_order: Number(sortOrder) || 0,
      };
      if (isEdit) {
        payload.is_active = isActive;
        await api.patch(`/zones/${encodeURIComponent(zone.code)}`, payload);
      } else {
        if (!code) throw new Error("Код обязателен");
        await api.post("/zones", { ...payload, code: code.trim().toLowerCase() });
      }
      toast.ok(isEdit ? "Зона обновлена" : "Зона создана");
      onClose();
    } catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  const deactivate = async () => {
    if (!confirm(`Деактивировать зону ${zone.code}?`)) return;
    setBusy(true); setErr("");
    try { await api.del(`/zones/${encodeURIComponent(zone.code)}`); toast.ok("Зона деактивирована"); onClose(); }
    catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <Modal
      title={isEdit ? `Зона: ${zone.code}` : "Новая зона"}
      onClose={onClose}
      footer={
        <>
          {isEdit && <button className="btn btn-danger" onClick={deactivate} disabled={busy} style={{ marginRight: "auto" }}>Деактивировать</button>}
          <button className="btn btn-ghost" onClick={onClose}>Отмена</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>{isEdit ? "Сохранить" : "Создать"}</button>
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
