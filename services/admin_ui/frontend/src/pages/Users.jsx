import { useState, useMemo } from "react";
import { api } from "../api/client.js";
import { useQuery } from "../hooks/useQuery.js";
import { Icon } from "../components/Icon.jsx";
import { Modal } from "../components/Modal.jsx";
import { Field } from "../components/Field.jsx";
import { toast } from "../components/Toast.jsx";
import { UserDrawer } from "../components/UserDrawer.jsx";
import { UserAvatar } from "../components/users/UserAvatar.jsx";
import { BalancePill } from "../components/users/BalancePill.jsx";
import { FilterPresets } from "../components/users/FilterChip.jsx";
import "../components/users/users.css";

const PRESETS = [
  { id: "all", label: "Все" },
  { id: "no_sub", label: "Без подписки", icon: "user" },
  { id: "expiring", label: "Истекают (7д)", icon: "clock" },
];

function presetParams(preset) {
  switch (preset) {
    case "no_sub": return { has_subscription: false };
    case "expiring": return { expiring_within_days: 7 };
    default: return {};
  }
}

export function UsersPage() {
  const [search, setSearch] = useState("");
  const [preset, setPreset] = useState("all");
  const [activeFilter, setActiveFilter] = useState("");
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);

  const params = useMemo(() => presetParams(preset), [preset]);

  const qs = new URLSearchParams({ limit: "100" });
  if (search) qs.set("search", search);
  if (activeFilter) qs.set("is_active", activeFilter);
  Object.entries(params).forEach(([k, v]) => qs.set(k, String(v)));

  const { data, loading, error, refetch } = useQuery(
    () => api.get(`/users?${qs.toString()}`),
    { interval: 30000, deps: [search, activeFilter, preset] }
  );

  const expiringQuery = useQuery(
    () => api.get(`/users?expiring_within_days=7&limit=1`),
    { interval: 60000 }
  );
  const noSubQuery = useQuery(
    () => api.get(`/users?has_subscription=false&limit=1`),
    { interval: 60000 }
  );

  const items = data?.items || [];
  const total = data?.total ?? 0;

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Пользователи</h1>
          <div className="page-subtitle">{total.toLocaleString("ru-RU")} всего</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-ghost" onClick={refetch}>
            <Icon name="refresh" size={13} /> Обновить
          </button>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            <Icon name="plus" size={13} /> Создать
          </button>
        </div>
      </div>

      <div className="u-kpi-bar">
        <KpiCard icon="user" label="Всего" value={total.toLocaleString("ru-RU")} />
        <KpiCard icon="user" label="Без подписки" value={noSubQuery.data?.total ?? "—"} />
        <KpiCard
          icon="clock"
          label="Истекают за 7 дней"
          value={expiringQuery.data?.total ?? "—"}
          tone={(expiringQuery.data?.total ?? 0) > 0 ? "warn" : ""}
        />
      </div>

      <div className="u-filter-bar">
        <div className="input-search-wrap" style={{ flex: 1, minWidth: 240, maxWidth: 360 }}>
          <Icon name="search" size={13} className="input-search-icon" />
          <input
            className="input"
            placeholder="Поиск: tg-id, @username, uuid…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <FilterPresets items={PRESETS} value={preset} onPick={setPreset} />
        <div style={{ marginLeft: "auto" }}>
          <select
            className="select"
            value={activeFilter}
            onChange={(e) => setActiveFilter(e.target.value)}
          >
            <option value="">Любой статус</option>
            <option value="true">Активные</option>
            <option value="false">Отключённые</option>
          </select>
        </div>
      </div>

      {error && <div className="card card-bad">Ошибка: {error.message}</div>}

      {loading && !items.length ? (
        <UsersSkeleton />
      ) : !items.length ? (
        <UsersEmpty
          hasFilters={Boolean(search || activeFilter || preset !== "all")}
          onReset={() => { setSearch(""); setActiveFilter(""); setPreset("all"); }}
        />
      ) : (
        <>
          <div className="card">
            <table className="tbl u-tbl">
              <thead>
                <tr>
                  <th>Пользователь</th>
                  <th style={{ textAlign: "right" }}>Баланс</th>
                  <th>Создан</th>
                  <th>Условия</th>
                  <th>Статус</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((u) => (
                  <UserRow key={u.id} u={u} onOpen={() => setSelected(u)} />
                ))}
              </tbody>
            </table>
          </div>

          <div className="u-mobile-list">
            {items.map((u) => (
              <UserMobileCard key={u.id} u={u} onOpen={() => setSelected(u)} />
            ))}
          </div>
        </>
      )}

      {selected && <UserDrawer user={selected} onClose={() => setSelected(null)} />}
      {creating && (
        <UserCreateModal
          onClose={() => setCreating(false)}
          onCreated={(u) => { setCreating(false); refetch(); setSelected(u); }}
        />
      )}
    </div>
  );
}

function KpiCard({ icon, label, value, tone }) {
  return (
    <div className={"u-kpi" + (tone ? ` ${tone}` : "")}>
      <div className="u-kpi-label"><Icon name={icon} size={11} /> {label}</div>
      <div className="u-kpi-val">{value}</div>
    </div>
  );
}

function fmtDate(s) {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("ru-RU"); } catch { return s; }
}

function UserRow({ u, onOpen }) {
  return (
    <tr style={{ cursor: "pointer" }} onClick={onOpen}>
      <td>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <UserAvatar name={u.username || `tg${u.telegram_id}`} muted={!u.is_active} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 500, display: "flex", alignItems: "center", gap: 6 }}>
              {u.username ? `@${u.username}` : <span className="muted">tg:{u.telegram_id}</span>}
              {!u.is_active && <Icon name="shield-off" size={11} style={{ color: "var(--bad)" }} />}
            </div>
            <div className="mono muted" style={{ fontSize: 11 }}>
              tg:{u.telegram_id}
            </div>
          </div>
        </div>
      </td>
      <td style={{ textAlign: "right" }}>
        <BalancePill amount={u.balance} />
      </td>
      <td className="small muted">{fmtDate(u.created_at)}</td>
      <td>
        {u.terms_accepted
          ? <span className="pill ok small">принято</span>
          : <span className="pill small">нет</span>}
      </td>
      <td>
        {u.is_active
          ? <span className="pill ok small">активен</span>
          : <span className="pill small">отключён</span>}
      </td>
      <td style={{ width: 32, textAlign: "right", paddingRight: 12 }}>
        <Icon name="chevron-right" size={14} className="muted" />
      </td>
    </tr>
  );
}

function UserMobileCard({ u, onOpen }) {
  return (
    <div className="u-mobile-card" onClick={onOpen}>
      <div className="u-mobile-card-head">
        <UserAvatar name={u.username || `tg${u.telegram_id}`} muted={!u.is_active} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 500 }}>
            {u.username ? `@${u.username}` : `tg${u.telegram_id}`}
          </div>
          <div className="mono muted" style={{ fontSize: 11 }}>tg:{u.telegram_id}</div>
        </div>
        <BalancePill amount={u.balance} />
      </div>
      <div className="u-mobile-card-row">
        <div>
          <div className="u-mobile-card-lbl">Создан</div>
          <span className="small muted">{fmtDate(u.created_at)}</span>
        </div>
        <div>
          <div className="u-mobile-card-lbl">Статус</div>
          {u.is_active
            ? <span className="pill ok small">активен</span>
            : <span className="pill small">отключён</span>}
        </div>
      </div>
    </div>
  );
}

function UsersSkeleton() {
  return (
    <div className="card">
      <table className="tbl u-tbl">
        <thead>
          <tr>
            <th>Пользователь</th>
            <th style={{ textAlign: "right" }}>Баланс</th>
            <th>Создан</th>
            <th>Условия</th>
            <th>Статус</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {[0,1,2,3,4,5,6].map((i) => (
            <tr key={i}>
              <td>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <div className="u-skel" style={{ width: 32, height: 32, borderRadius: "50%" }}></div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                    <div className="u-skel" style={{ width: 140, height: 11 }}></div>
                    <div className="u-skel" style={{ width: 96, height: 9 }}></div>
                  </div>
                </div>
              </td>
              <td style={{ textAlign: "right" }}><div className="u-skel" style={{ width: 80, height: 18, borderRadius: 6, display: "inline-block" }}></div></td>
              <td><div className="u-skel" style={{ width: 70, height: 12 }}></div></td>
              <td><div className="u-skel" style={{ width: 60, height: 18, borderRadius: 6 }}></div></td>
              <td><div className="u-skel" style={{ width: 60, height: 18, borderRadius: 6 }}></div></td>
              <td></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function UsersEmpty({ hasFilters, onReset }) {
  return (
    <div className="card">
      <div className="u-empty">
        <div className="u-empty-art"><Icon name="user" size={36} /></div>
        <div className="u-empty-title">
          {hasFilters ? "Нет пользователей под фильтры" : "Пока нет пользователей"}
        </div>
        <div className="u-empty-text">
          {hasFilters
            ? "Попробуйте смягчить условия. Поиск работает по @username, telegram_id и UUID."
            : "Создайте первого пользователя по telegram_id, либо они появятся автоматически после регистрации в боте."}
        </div>
        {hasFilters && (
          <div className="u-empty-actions">
            <button className="btn btn-ghost" onClick={onReset}>
              <Icon name="x" size={13} /> Сбросить фильтры
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function UserCreateModal({ onClose, onCreated }) {
  const [f, setF] = useState({ telegram_id: "", username: "", description: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));

  const submit = async (e) => {
    e?.preventDefault?.();
    if (busy) return;
    setErr("");
    const tgRaw = String(f.telegram_id).trim();
    if (!tgRaw) { setErr("Telegram ID обязателен"); return; }
    const tg = Number(tgRaw);
    if (!Number.isInteger(tg) || tg <= 0) { setErr("Telegram ID должен быть положительным целым числом"); return; }
    const payload = { telegram_id: tg };
    const username = f.username.trim().replace(/^@/, "");
    if (username) payload.username = username;
    const description = f.description.trim();
    if (description) payload.description = description;
    setBusy(true);
    try {
      const created = await api.post("/users", payload);
      toast.ok("Пользователь создан");
      onCreated(created);
    } catch (e) {
      const msg = e.status === 409
        ? "Пользователь с таким Telegram ID уже существует"
        : (e.message || String(e));
      setErr(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Новый пользователь"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>Отмена</button>
          <button className="btn btn-primary" onClick={submit} disabled={busy}>
            {busy ? "Создание…" : "Создать"}
          </button>
        </>
      }
    >
      <form onSubmit={submit}>
        {err && <div className="form-error">{err}</div>}
        <Field label="Telegram ID" hint="обязательно">
          <input
            type="number"
            inputMode="numeric"
            min="1"
            step="1"
            autoFocus
            value={f.telegram_id}
            onChange={set("telegram_id")}
            placeholder="например, 123456789"
          />
        </Field>
        <Field label="Username" hint="без @, опционально">
          <input type="text" value={f.username} onChange={set("username")} placeholder="username" />
        </Field>
        <Field label="Описание" hint="опционально">
          <textarea rows={3} value={f.description} onChange={set("description")} />
        </Field>
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}
