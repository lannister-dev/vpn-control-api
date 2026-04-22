import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Drawer } from "./Drawer.jsx";
import { Icon } from "./Icon.jsx";
import { SubscriptionDrawer } from "./SubscriptionDrawer.jsx";

function fmtBytes(b) {
  if (!b) return "0";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, n = Number(b);
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return n.toFixed(n >= 100 || i === 0 ? 0 : 1) + " " + u[i];
}

function fmtDate(s) {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("ru-RU"); } catch { return s; }
}

function fmtDateTime(s) {
  if (!s) return "—";
  try { return new Date(s).toLocaleString("ru-RU"); } catch { return s; }
}

export function UserDrawer({ user, onClose }) {
  const [tab, setTab] = useState("overview");
  const [openSub, setOpenSub] = useState(null);

  const detail = useQuery(() => api.get(`/users/${user.id}`), { interval: 0, deps: [user.id] });
  const subs = useQuery(() => api.get(`/subscriptions/by-user/${user.id}`), { interval: 30000, deps: [user.id] });
  const plans = useQuery(() => api.get("/plans"), { interval: 60000 });
  const plansById = useMemo(() => Object.fromEntries((plans.data?.items || []).map((p) => [p.id, p])), [plans.data]);

  const subsList = Array.isArray(subs.data) ? subs.data : (subs.data?.items || []);
  const d = detail.data || user;

  const tabs = [
    { id: "overview", label: "Обзор" },
    { id: "subs", label: `Подписки · ${d.subscription_count ?? subsList.length}` },
    { id: "devices", label: `Устройства` },
  ];

  const head = (
    <>
      <div className="user-avatar" style={{ width: 36, height: 36, marginTop: 2 }}>
        {(d.username || `tg${d.telegram_id}`).slice(0, 2).toUpperCase()}
      </div>
      <div className="slideover-title-main">
        <div className="slideover-title" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span>{d.username ? `@${d.username}` : `tg:${d.telegram_id}`}</span>
          {d.is_active ? <span className="pill ok">active</span> : <span className="pill">disabled</span>}
        </div>
        <div className="slideover-sub">
          <span className="mono">{String(d.id).slice(0, 12)}</span> · tg <span className="mono">{d.telegram_id}</span> · {fmtDate(d.created_at)}
        </div>
      </div>
    </>
  );

  return (
    <>
      <Drawer head={head} onClose={onClose} tabs={tabs} activeTab={tab} onTab={setTab}>
        {tab === "overview" && <UserOverview user={d} subs={subsList} />}
        {tab === "subs" && <UserSubsTab subs={subsList} plansById={plansById} loading={subs.loading} onOpen={setOpenSub} />}
        {tab === "devices" && <UserDevicesTab subs={subsList} />}
      </Drawer>
      {openSub && <SubscriptionDrawer subscription={openSub} onClose={() => setOpenSub(null)} onChanged={subs.refetch} />}
    </>
  );
}

function UserOverview({ user, subs }) {
  const active = subs.filter((s) => s.is_active).length;
  const totalUsed = subs.reduce((a, s) => a + (s.used_traffic_bytes || 0), 0);
  const lifetime = subs.reduce((a, s) => a + (s.lifetime_used_traffic_bytes || 0), 0);

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 20 }}>
        <div className="card"><div className="card-body" style={{ padding: 14 }}>
          <div className="kpi-label"><Icon name="key" size={12} /> Активных подписок</div>
          <div className="kpi-value" style={{ fontSize: 22 }}>{active}<span className="kpi-unit">/ {subs.length}</span></div>
        </div></div>
        <div className="card"><div className="card-body" style={{ padding: 14 }}>
          <div className="kpi-label"><Icon name="wallet" size={12} /> Баланс</div>
          <div className="kpi-value" style={{ fontSize: 22 }}>{user.balance ?? 0}<span className="kpi-unit">₽</span></div>
        </div></div>
        <div className="card"><div className="card-body" style={{ padding: 14 }}>
          <div className="kpi-label"><Icon name="activity" size={12} /> Трафик за период</div>
          <div className="kpi-value" style={{ fontSize: 22 }}>{fmtBytes(totalUsed)}</div>
        </div></div>
        <div className="card"><div className="card-body" style={{ padding: 14 }}>
          <div className="kpi-label"><Icon name="bar-chart" size={12} /> Всего использовано</div>
          <div className="kpi-value" style={{ fontSize: 22 }}>{fmtBytes(lifetime)}</div>
        </div></div>
      </div>

      <div className="sec-head"><div className="sec-title">Параметры</div></div>
      <dl className="kv">
        <dt>UUID</dt><dd className="mono">{user.id}</dd>
        <dt>Telegram ID</dt><dd className="mono">{user.telegram_id}</dd>
        <dt>Username</dt><dd>{user.username ? `@${user.username}` : <span className="muted">—</span>}</dd>
        <dt>Тег</dt><dd>{user.tag || <span className="muted">—</span>}</dd>
        <dt>Описание</dt><dd className="small">{user.description || <span className="muted">—</span>}</dd>
        <dt>Реф. код</dt><dd className="mono">{user.referral_code || <span className="muted">—</span>}</dd>
        <dt>Согласие с условиями</dt><dd>
          {user.terms_accepted
            ? <span className="pill ok">{fmtDateTime(user.terms_accepted_at)}</span>
            : <span className="pill">не принято</span>}
        </dd>
        <dt>Создан</dt><dd className="small muted">{fmtDateTime(user.created_at)}</dd>
        <dt>Обновлён</dt><dd className="small muted">{fmtDateTime(user.updated_at)}</dd>
      </dl>
    </div>
  );
}

function UserSubsTab({ subs, plansById, loading, onOpen }) {
  if (loading && !subs.length) return <div className="muted" style={{ padding: 14 }}>Загрузка…</div>;
  if (!subs.length) return <div className="muted" style={{ padding: 14 }}>У пользователя нет подписок.</div>;
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>Тариф</th>
          <th>Регион</th>
          <th style={{ textAlign: "right" }}>Устройств</th>
          <th>Истекает</th>
          <th>Статус</th>
        </tr>
      </thead>
      <tbody>
        {subs.map((s) => (
          <tr key={s.id} style={{ cursor: "pointer" }} onClick={() => onOpen(s)}>
            <td style={{ fontWeight: 500 }}>{s.plan_id ? (plansById[s.plan_id]?.name || String(s.plan_id).slice(0, 8) + "…") : <span className="muted">—</span>}</td>
            <td className="mono">{s.preferred_region || "—"}</td>
            <td className="tbl-num mono">{s.max_devices ?? "—"}</td>
            <td className="small muted">{fmtDate(s.expires_at)}</td>
            <td>{s.is_active ? <span className="pill ok">active</span> : <span className="pill">inactive</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function UserDevicesTab({ subs }) {
  const subIds = subs.map((s) => s.id).join(",");
  const allDevices = useQuery(async () => {
    if (!subs.length) return [];
    const lists = await Promise.all(subs.map((s) =>
      api.get(`/subscriptions/${s.id}/devices`).then((d) => (Array.isArray(d) ? d.map((x) => ({ ...x, _sub: s })) : [])).catch(() => [])
    ));
    return lists.flat();
  }, { interval: 30000, deps: [subIds] });

  if (allDevices.loading && !allDevices.data) return <div className="muted" style={{ padding: 14 }}>Загрузка…</div>;
  const devices = allDevices.data || [];
  if (!devices.length) return <div className="muted" style={{ padding: 14 }}>Устройств нет.</div>;

  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>HWID</th>
          <th>Подписка</th>
          <th>User-Agent</th>
          <th>Последний раз</th>
          <th>Статус</th>
        </tr>
      </thead>
      <tbody>
        {devices.map((d) => (
          <tr key={d.id}>
            <td className="mono small">{String(d.hwid_hash || d.id).slice(0, 16)}…</td>
            <td className="mono small muted">{String(d._sub.id).slice(0, 8)}…</td>
            <td className="small muted" style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={d.user_agent || ""}>{d.user_agent || "—"}</td>
            <td className="small muted">{fmtDateTime(d.last_seen_at)}</td>
            <td>{d.is_active ? <span className="pill ok">active</span> : <span className="pill">revoked</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
