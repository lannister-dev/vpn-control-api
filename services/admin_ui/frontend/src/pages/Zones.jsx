import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Modal } from "../components/Modal.jsx";
import { Field } from "../components/Field.jsx";
import { Icon } from "../components/Icon.jsx";
import { toast } from "../components/Toast.jsx";
import { Empty, SkeletonRows } from "../components/Empty.jsx";

export function ZonesPage() {
  const { data, loading, error, refetch } = useQuery(() => api.get("/zones"), { interval: 30000 });
  const status = useQuery(() => api.get("/admin/status").catch(() => null), { interval: 60000 });
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);

  const allNodes = status.data?.nodes || [];
  const whitelistEntries = useMemo(
    () => allNodes.filter((n) => n.role === "whitelist_entry"),
    [allNodes],
  );
  const nodeById = useMemo(
    () => Object.fromEntries(allNodes.map((n) => [n.id, n])),
    [allNodes],
  );

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
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            <Icon name="plus" size={13} /> Создать зону
          </button>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      <div className="card">
        <table className="tbl">
          <thead>
            <tr>
              <th>Код</th>
              <th>Эмодзи</th>
              <th>Название</th>
              <th style={{ textAlign: "right" }}>Sort</th>
              <th>Статус</th>
              <th>Fallback entry</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(loading && !items.length) && <SkeletonRows count={3} cols={7} />}
            {items.map((z) => {
              const fb = z.fallback_entry_node_id ? nodeById[z.fallback_entry_node_id] : null;
              return (
                <tr key={z.id}>
                  <td className="mono">{z.code}</td>
                  <td style={{ fontSize: 20 }}>{z.emoji || "—"}</td>
                  <td style={{ fontWeight: 500 }}>{z.name}</td>
                  <td className="tbl-num mono">{z.sort_order}</td>
                  <td>{z.is_active ? <span className="pill ok">active</span> : <span className="pill">inactive</span>}</td>
                  <td>
                    {fb
                      ? <span className="pill accent">{fb.name}</span>
                      : z.fallback_entry_node_id
                        ? <span className="mono small muted">{String(z.fallback_entry_node_id).slice(0, 8)}…</span>
                        : <span className="muted">—</span>}
                  </td>
                  <td className="row-actions"><button className="row-btn" onClick={() => setEditing(z)}>Edit</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(!loading && !items.length) && <Empty icon="globe" title="Зон нет" hint="Создайте первую зону, чтобы привязывать к ней entry-ноды." />}
      </div>

      {creating && <ZoneForm whitelistEntries={whitelistEntries} onClose={() => { setCreating(false); refetch(); }} />}
      {editing && <ZoneForm zone={editing} whitelistEntries={whitelistEntries} onClose={() => { setEditing(null); refetch(); }} />}
    </div>
  );
}

function ZoneForm({ zone, whitelistEntries = [], onClose }) {
  const isEdit = !!zone;
  const [code, setCode] = useState(zone?.code || "");
  const [name, setName] = useState(zone?.name || "");
  const [emoji, setEmoji] = useState(zone?.emoji || "");
  const [sortOrder, setSortOrder] = useState(zone?.sort_order ?? 0);
  const [isActive, setIsActive] = useState(zone ? zone.is_active : true);
  const [fallbackEntryId, setFallbackEntryId] = useState(zone?.fallback_entry_node_id || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const save = async () => {
    setBusy(true); setErr("");
    try {
      const payload = {
        name: name.trim(),
        emoji: emoji.trim(),
        sort_order: Number(sortOrder) || 0,
        fallback_entry_node_id: fallbackEntryId || null,
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
      <Field
        label="Fallback entry-нода"
        hint="когда основной entry не пингуется — клиент перейдёт сюда (whitelist)"
      >
        <select value={fallbackEntryId || ""} onChange={(e) => setFallbackEntryId(e.target.value)}>
          <option value="">— нет (без fallback) —</option>
          {whitelistEntries.map((n) => (
            <option key={n.id} value={n.id}>
              {n.name} ({n.region || "?"})
            </option>
          ))}
        </select>
      </Field>
      {isEdit && (
        <label className="form-check">
          <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} /> Активна
        </label>
      )}
    </Modal>
  );
}
