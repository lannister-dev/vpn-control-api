import { useState } from "react";
import { api } from "../api/client.js";
import { Drawer } from "./Drawer.jsx";
import { Modal } from "./Modal.jsx";
import { Field } from "./Field.jsx";
import { toast } from "./Toast.jsx";

export function SubscriptionDrawer({ subscription, onClose, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [maxDevOpen, setMaxDevOpen] = useState(false);

  const sub = subscription;

  const rotate = async () => {
    if (!confirm("Ротировать токен подписки?")) return;
    setBusy(true); setErr("");
    try {
      const r = await api.post(`/subscriptions/${sub.id}/rotate-token`);
      if (r?.token) navigator.clipboard?.writeText(r.token);
      toast.ok("Токен обновлён, скопирован в буфер");
      onChanged && onChanged();
    } catch (e) { setErr(e.message || String(e)); toast.bad(e.message || String(e)); }
    finally { setBusy(false); }
  };
  const deactivate = async () => {
    if (!confirm("Деактивировать подписку?")) return;
    setBusy(true); setErr("");
    try { await api.post(`/subscriptions/${sub.id}/deactivate`); onChanged && onChanged(); onClose(); }
    catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };
  const activate = async () => {
    setBusy(true); setErr("");
    try { await api.post(`/subscriptions/${sub.id}/activate`); onChanged && onChanged(); }
    catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <Drawer
      title={String(sub.id).slice(0, 8) + "…"}
      subtitle={sub.plan_name || sub.plan_id || "без тарифа"}
      onClose={onClose}
    >
      {err && <div className="form-error">{err}</div>}
      <table className="kv-table">
        <tbody>
          <tr><th>ID</th><td className="mono small">{sub.id}</td></tr>
          <tr><th>User</th><td className="mono small">{sub.user_id}</td></tr>
          <tr><th>Plan</th><td>{sub.plan_name || sub.plan_id || "—"}</td></tr>
          <tr><th>Preferred region</th><td className="mono">{sub.preferred_region || "—"}</td></tr>
          <tr><th>HWID enabled</th><td>{String(sub.hwid_enabled)}</td></tr>
          <tr><th>Max devices</th><td className="mono">{sub.max_devices ?? "—"}</td></tr>
          <tr><th>Paid slots</th><td className="mono">{sub.paid_device_slots ?? 0}</td></tr>
          <tr><th>Expires</th><td>{sub.expires_at ? new Date(sub.expires_at).toLocaleString() : "—"}</td></tr>
          <tr><th>Статус</th><td>{sub.is_active ? <span className="pill ok">active</span> : <span className="pill">inactive</span>}</td></tr>
        </tbody>
      </table>
      <div className="muted small" style={{ marginTop: 10 }}>
        Устройствами этой подписки управляйте во вкладке «Устройства» карточки пользователя.
      </div>
      <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="btn btn-ghost" onClick={() => setMaxDevOpen(true)} disabled={busy}>Изменить max devices</button>
        <button className="btn btn-ghost" onClick={rotate} disabled={busy}>Ротировать токен</button>
        {sub.is_active
          ? <button className="btn btn-danger" onClick={deactivate} disabled={busy}>Деактивировать</button>
          : <button className="btn btn-primary" onClick={activate} disabled={busy}>Активировать</button>}
      </div>

      {maxDevOpen && <MaxDevicesForm sub={sub} onClose={() => { setMaxDevOpen(false); onChanged && onChanged(); }} />}
    </Drawer>
  );
}

function MaxDevicesForm({ sub, onClose }) {
  const [v, setV] = useState(sub.max_devices ?? 5);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const save = async () => {
    setBusy(true); setErr("");
    try { await api.patch(`/subscriptions/${sub.id}/max-devices`, { max_devices: Number(v) }); onClose(); }
    catch (e) { setErr(e.message || String(e)); }
    finally { setBusy(false); }
  };
  return (
    <Modal
      title="Изменить max devices"
      onClose={onClose}
      footer={<><button className="btn btn-ghost" onClick={onClose}>Отмена</button><button className="btn btn-primary" onClick={save} disabled={busy}>Сохранить</button></>}
    >
      {err && <div className="form-error">{err}</div>}
      <Field label="Max devices" hint="1–100"><input type="number" min={1} max={100} value={v} onChange={(e) => setV(e.target.value)} /></Field>
    </Modal>
  );
}
