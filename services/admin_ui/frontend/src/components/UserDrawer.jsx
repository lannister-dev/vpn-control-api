import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Drawer } from "./Drawer.jsx";
import { Icon } from "./Icon.jsx";
import { toast } from "./Toast.jsx";
import { SubscriptionDrawer } from "./SubscriptionDrawer.jsx";
import { SubscriptionCreateModal } from "./SubscriptionCreateModal.jsx";
import { UserAvatar } from "./users/UserAvatar.jsx";
import { BalancePill } from "./users/BalancePill.jsx";
import { StatusPill, deriveSubStatus } from "./users/StatusPill.jsx";
import { DaysCountdown, daysLeft } from "./users/DaysCountdown.jsx";
import { SubscriptionCard } from "./users/SubscriptionCard.jsx";
import { SubscriptionSummaryRow } from "./users/SubscriptionSummaryRow.jsx";
import { DeviceCard } from "./users/DeviceCard.jsx";
import "./users/users.css";

function fmtDateTime(s) {
  if (!s) return "—";
  try { return new Date(s).toLocaleString("ru-RU"); } catch { return s; }
}

export function UserDrawer({ user, onClose }) {
  const [tab, setTab] = useState("overview");
  const [openSub, setOpenSub] = useState(null);
  const [creatingSub, setCreatingSub] = useState(false);

  const detail = useQuery(() => api.get(`/users/${user.id}`), { interval: 0, deps: [user.id] });
  const subs = useQuery(() => api.get(`/subscriptions/by-user/${user.id}`), { interval: 30000, deps: [user.id] });
  const plans = useQuery(() => api.get("/plans"), { interval: 60000 });
  const plansById = useMemo(() => Object.fromEntries((plans.data?.items || []).map((p) => [p.id, p])), [plans.data]);

  const subsList = Array.isArray(subs.data) ? subs.data : (subs.data?.items || []);
  const d = detail.data || user;
  const userLabel = d.username ? `@${d.username}` : `tg:${d.telegram_id}`;

  const expiringSub = useMemo(() => {
    return subsList.find((s) => deriveSubStatus(s) === "expiring");
  }, [subsList]);

  const tabs = [
    { id: "overview", label: "Обзор" },
    { id: "subs", label: `Подписки · ${subsList.length}` },
    { id: "devices", label: "Устройства" },
  ];

  const head = (
    <UserHero d={d} subsCount={subsList.length} />
  );

  return (
    <>
      <Drawer head={head} onClose={onClose} tabs={tabs} activeTab={tab} onTab={setTab}>
        {tab === "overview" && (
          <Overview
            user={d}
            subs={subsList}
            plansById={plansById}
            expiringSub={expiringSub}
            onCreateSub={() => setCreatingSub(true)}
            onOpenSub={setOpenSub}
          />
        )}
        {tab === "subs" && (
          <SubsTab
            subs={subsList}
            plansById={plansById}
            loading={subs.loading}
            onOpen={setOpenSub}
            onCreate={() => setCreatingSub(true)}
          />
        )}
        {tab === "devices" && (
          <DevicesTab
            subs={subsList}
            plansById={plansById}
            onOpenSub={setOpenSub}
          />
        )}
      </Drawer>
      {openSub && <SubscriptionDrawer subscription={openSub} onClose={() => setOpenSub(null)} onChanged={subs.refetch} />}
      {creatingSub && (
        <SubscriptionCreateModal
          userId={d.id}
          userLabel={userLabel}
          plans={plans.data}
          onClose={() => setCreatingSub(false)}
          onCreated={() => { setCreatingSub(false); subs.refetch(); detail.refetch(); }}
        />
      )}
    </>
  );
}

function UserHero({ d, subsCount }) {
  const name = d.username || `tg${d.telegram_id}`;
  const copy = (text) => {
    navigator.clipboard?.writeText(text);
    toast.ok("Скопировано");
  };
  return (
    <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
      <UserAvatar name={name} size="lg" muted={!d.is_active} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="slideover-title" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span>{d.username ? `@${d.username}` : `tg:${d.telegram_id}`}</span>
          <BalancePill amount={d.balance} />
          {d.tag && <span className="pill">{d.tag}</span>}
          {!d.is_active && <span className="pill">отключён</span>}
        </div>
        <div className="slideover-sub">
          <span
            className="mono"
            style={{ cursor: "pointer" }}
            onClick={() => copy(d.id)}
            title="Скопировать UUID"
          >{String(d.id).slice(0, 12)}…</span>
          <span> · tg <span className="mono">{d.telegram_id}</span></span>
        </div>
      </div>
    </div>
  );
}

function Overview({ user, subs, plansById, expiringSub, onCreateSub, onOpenSub }) {
  return (
    <div>
      {expiringSub && (
        <div className="u-action-card">
          <div>
            <div className="u-action-card-title">
              Подписка <span className="mono">{String(expiringSub.id).slice(0, 8)}</span> истекает
            </div>
            <div className="u-action-card-sub">
              <DaysCountdown days={daysLeft(expiringSub.expires_at)} /> · Баланс <BalancePill amount={user.balance} />
            </div>
          </div>
          <button className="btn btn-sm" onClick={() => onOpenSub(expiringSub)}>
            <Icon name="rotate-cw" size={12} /> Продлить
          </button>
        </div>
      )}

      <div className="u-section">
        <div className="u-section-head">
          <span>Подписки · {subs.length}</span>
          <button className="btn btn-ghost btn-sm" onClick={onCreateSub}>
            <Icon name="plus" size={12} /> Добавить
          </button>
        </div>
        {!subs.length && <div className="muted small">Нет подписок</div>}
        {subs.slice(0, 5).map((s) => (
          <SubscriptionSummaryRow
            key={s.id}
            sub={s}
            plan={plansById[s.plan_id]}
            onOpen={onOpenSub}
          />
        ))}
        {subs.length > 5 && (
          <div className="muted small" style={{ marginTop: 6 }}>
            +{subs.length - 5} ещё · во вкладке «Подписки»
          </div>
        )}
      </div>

      <div className="u-section">
        <div className="u-section-head"><span>Параметры</span></div>
        <dl className="kv">
          <dt>UUID</dt><dd className="mono small">{user.id}</dd>
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
    </div>
  );
}

function SubsTab({ subs, plansById, loading, onOpen, onCreate }) {
  return (
    <div className="u-section">
      <div className="u-section-head">
        <span>Все подписки</span>
        <button className="btn btn-ghost btn-sm" onClick={onCreate}>
          <Icon name="plus" size={12} /> Добавить
        </button>
      </div>
      {loading && !subs.length && <div className="muted">Загрузка…</div>}
      {!loading && !subs.length && <div className="muted small">У пользователя нет подписок.</div>}
      {subs.map((s) => (
        <SubscriptionCard
          key={s.id}
          sub={s}
          plan={plansById[s.plan_id]}
          onOpen={onOpen}
        />
      ))}
    </div>
  );
}

function DevicesTab({ subs, plansById, onOpenSub }) {
  const subIds = subs.map((s) => s.id).join(",");
  const allDevices = useQuery(async () => {
    if (!subs.length) return [];
    const lists = await Promise.all(subs.map((s) =>
      api.get(`/subscriptions/${s.id}/devices`)
        .then((d) => (Array.isArray(d) ? d : []).map((dev) => ({ ...dev, subscription_id: dev.subscription_id || s.id })))
        .catch(() => [])
    ));
    return lists.flat();
  }, { interval: 30000, deps: [subIds] });

  const onRevoke = async (device) => {
    if (!confirm(`Отозвать устройство ${String(device.hwid_hash || device.id).slice(0,8)}…?`)) return;
    try {
      await api.post(`/subscriptions/${device.subscription_id}/devices/${device.id}/revoke`);
      toast.ok("Устройство отозвано");
      allDevices.refetch();
    } catch (e) {
      toast.bad(e.message || String(e));
    }
  };
  const onCopy = (device) => {
    navigator.clipboard?.writeText(device.hwid_hash || device.id);
    toast.ok("HWID скопирован");
  };

  if (allDevices.loading && !allDevices.data) {
    return <div className="muted u-section">Загрузка…</div>;
  }
  const devices = allDevices.data || [];
  if (!devices.length) {
    return <div className="muted small u-section">Устройств нет.</div>;
  }

  const subsById = Object.fromEntries(subs.map((s) => [s.id, s]));
  const groups = subs
    .map((s) => ({
      sub: s,
      items: devices.filter((d) => d.subscription_id === s.id),
    }))
    .filter((g) => g.items.length > 0);
  const orphaned = devices.filter((d) => !subsById[d.subscription_id]);
  if (orphaned.length) groups.push({ sub: null, items: orphaned });

  return (
    <div className="u-section">
      <div className="u-section-head"><span>Все устройства · {devices.length}</span></div>
      {groups.map(({ sub, items }) => (
        <DeviceGroup
          key={sub?.id || "orphan"}
          sub={sub}
          plan={sub ? plansById[sub.plan_id] : null}
          devices={items}
          onOpenSub={onOpenSub}
          onCopy={onCopy}
          onRevoke={onRevoke}
        />
      ))}
    </div>
  );
}

function DeviceGroup({ sub, plan, devices, onOpenSub, onCopy, onRevoke }) {
  const planName = plan?.name || (sub?.plan_id ? `plan ${String(sub.plan_id).slice(0, 6)}…` : "—");
  const subId = sub ? String(sub.id).slice(0, 8) : "—";
  return (
    <div className="u-devgroup">
      <div className="u-devgroup-head">
        <div className="u-devgroup-head-main">
          <span className="u-devgroup-plan">{sub ? planName : "Без подписки"}</span>
          {sub && <span className="u-devgroup-id mono">{subId}</span>}
          <span className="u-devgroup-count muted">· {devices.length}</span>
        </div>
        {sub && onOpenSub && (
          <button className="btn btn-ghost btn-sm" onClick={() => onOpenSub(sub)} title="Открыть подписку">
            <Icon name="external-link" size={12} /> Открыть подписку
          </button>
        )}
      </div>
      {devices.map((d) => (
        <DeviceCard key={d.id} device={d} onCopy={onCopy} onRevoke={onRevoke} />
      ))}
    </div>
  );
}
