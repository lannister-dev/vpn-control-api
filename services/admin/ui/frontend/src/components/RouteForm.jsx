import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Modal } from "./Modal.jsx";
import { Field } from "./Field.jsx";
import { toast } from "./Toast.jsx";

export function RouteForm({
  route,
  nodes,
  onClose,
  defaults,
}) {
  const isEdit = !!route;
  const initialNodeId = route?.node_id || defaults?.node_id || "";
  const initialEntryId = route?.entry_node_id ?? defaults?.entry_node_id ?? "";

  const [name, setName] = useState(route?.name || defaults?.name || "");
  const [nodeId, setNodeId] = useState(initialNodeId);
  const [entryNodeId, setEntryNodeId] = useState(initialEntryId || "");
  const [tpId, setTpId] = useState(route?.transport_profile_id || defaults?.transport_profile_id || "");
  const [baseWeight, setBaseWeight] = useState(route?.base_weight ?? defaults?.base_weight ?? 50);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const profiles = useQuery(() => api.get("/routes/transport-profiles?limit=200"), { interval: 0 });
  const profilesList = profiles.data || [];

  const backends = nodes.filter((n) => n.role === "backend");
  const entries = nodes.filter((n) => n.role === "entry" || n.role === "whitelist_entry");

  const save = async () => {
    setBusy(true); setErr("");
    try {
      if (isEdit) {
        const payload = {};
        if (name && name !== route.name) payload.name = name;
        if (nodeId && nodeId !== route.node_id) payload.node_id = nodeId;
        const newEntry = entryNodeId || null;
        if (newEntry !== (route.entry_node_id || null)) payload.entry_node_id = newEntry;
        const w = Number(baseWeight);
        if (!isNaN(w) && w !== route.base_weight) payload.base_weight = w;
        if (Object.keys(payload).length) await api.patch(`/routes/${route.id}`, payload);
      } else {
        if (!name) throw new Error("Имя обязательно");
        if (!nodeId) throw new Error("Backend обязателен");
        if (!tpId) throw new Error("Transport profile обязателен");
        const payload = { name, node_id: nodeId, transport_profile_id: tpId, base_weight: Number(baseWeight) || 50 };
        if (entryNodeId) payload.entry_node_id = entryNodeId;
        await api.post("/routes", payload);
      }
      toast.ok(isEdit ? "Маршрут обновлён" : "Маршрут создан");
      onClose(true);
    } catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  const deactivate = async () => {
    if (!confirm(`Деактивировать маршрут ${route.name}?`)) return;
    setBusy(true);
    try { await api.post(`/routes/${route.id}/deactivate`); toast.ok("Маршрут деактивирован"); onClose(true); }
    catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <Modal
      title={isEdit ? `Маршрут: ${route.name}` : "Новый маршрут"}
      onClose={() => onClose(false)}
      footer={
        <>
          {isEdit && <button className="btn btn-danger" onClick={deactivate} disabled={busy} style={{ marginRight: "auto" }}>Деактивировать</button>}
          <button className="btn btn-ghost" onClick={() => onClose(false)}>Отмена</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>{isEdit ? "Сохранить" : "Создать"}</button>
        </>
      }
    >
      {err && <div className="form-error">{err}</div>}
      <Field label="Имя"><input type="text" value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <Field label="Backend">
        <select value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
          <option value="">— выберите —</option>
          {backends.map((n) => <option key={n.id} value={n.id}>{n.name} · {n.region}</option>)}
        </select>
      </Field>
      <Field label="Entry" hint="опционально">
        <select value={entryNodeId} onChange={(e) => setEntryNodeId(e.target.value)}>
          <option value="">Без entry (direct)</option>
          {entries.map((n) => <option key={n.id} value={n.id}>{n.name} · {n.region} ({n.role})</option>)}
        </select>
      </Field>
      <Field label="Transport profile">
        <select value={tpId} onChange={(e) => setTpId(e.target.value)} disabled={isEdit}>
          <option value="">— выберите —</option>
          {profilesList.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.security}/{p.network})</option>)}
        </select>
      </Field>
      <Field label="Base weight" hint="0–100">
        <input type="number" min={0} max={100} value={baseWeight} onChange={(e) => setBaseWeight(e.target.value)} />
      </Field>
    </Modal>
  );
}
