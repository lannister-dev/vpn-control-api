import { useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Drawer } from "./Drawer.jsx";
import { Modal } from "./Modal.jsx";
import { Field } from "./Field.jsx";
import { toast } from "./Toast.jsx";

export function SubscriptionDrawer({ subscription, onClose, onChanged }) {
  const [tab, setTab] = useState("overview");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [maxDevOpen, setMaxDevOpen] = useState(false);

  const sub = subscription;

  const devices = useQuery(
    () => api.get(`/subscriptions/${sub.id}/devices`),
    { interval: 20000, deps: [sub.id] },
  );

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
  const revokeDevice = async (deviceId) => {
    if (!confirm("Отозвать это устройство?")) return;
    try { await api.post(`/subscriptions/${sub.id}/devices/${deviceId}/revoke`); toast.ok("Устройство отозвано"); devices.refetch(); }
    catch (e) { toast.bad(e.message); }
  };

  const tabs = [
    { id: "overview", label: "Обзор" },
    { id: "devices", label: `Устройства${devices.data ? ` (${(devices.data?.items || devices.data || []).length})` : ""}` },
  ];

  return (
    <Drawer
      title={String(sub.id).slice(0, 8) + "…"}
      subtitle={sub.plan_name || sub.plan_id || "без тарифа"}
      onClose={onClose}
      tabs={tabs}
      activeTab={tab}
      onTab={setTab}
    >
      {err && <div className="form-error">{err}</div>}
      {tab === "overview" && (
        <>
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
          <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn-ghost" onClick={() => setMaxDevOpen(true)} disabled={busy}>Изменить max devices</button>
            <button className="btn-ghost" onClick={rotate} disabled={busy}>Ротировать токен</button>
            {sub.is_active
              ? <button className="btn-danger" onClick={deactivate} disabled={busy}>Деактивировать</button>
              : <button className="btn-primary" onClick={activate} disabled={busy}>Активировать</button>}
          </div>
        </>
      )}

      {tab === "devices" && <DevicesList data={devices.data} loading={devices.loading} onRevoke={revokeDevice} />}

      {maxDevOpen && <MaxDevicesForm sub={sub} onClose={() => { setMaxDevOpen(false); onChanged && onChanged(); }} />}
    </Drawer>
  );
}

function DevicesList({ data, loading, onRevoke }) {
  const items = Array.isArray(data) ? data : (data?.items || []);
  if (loading && !items.length) return <div className="muted">Загрузка…</div>;
  if (!items.length) return <div className="muted">Устройств нет.</div>;
  return (
    <table className="tbl">
      <thead><tr><th>Device ID</th><th>HWID</th><th>User-Agent</th><th>Last seen</th><th>Статус</th><th></th></tr></thead>
      <tbody>
        {items.map((d) => (
          <tr key={d.id}>
            <td className="mono small">{String(d.id).slice(0, 12)}…</td>
            <td className="mono small">{String(d.hwid_hash || "").slice(0, 12)}…</td>
            <td className="small">{d.user_agent || "—"}</td>
            <td className="small muted">{d.last_seen_at ? new Date(d.last_seen_at).toLocaleString() : "—"}</td>
            <td>{d.is_active ? <span className="pill ok">active</span> : <span className="pill">revoked</span>}</td>
            <td>{d.is_active && <button className="row-btn" onClick={() => onRevoke(d.id)}>Revoke</button>}</td>
          </tr>
        ))}
      </tbody>
    </table>
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
      footer={<><button className="btn-ghost" onClick={onClose}>Отмена</button><button className="btn-primary" onClick={save} disabled={busy}>Сохранить</button></>}
    >
      {err && <div className="form-error">{err}</div>}
      <Field label="Max devices" hint="1–100"><input type="number" min={1} max={100} value={v} onChange={(e) => setV(e.target.value)} /></Field>
    </Modal>
  );
}
