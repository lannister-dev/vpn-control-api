import { state, refs, $ } from '../state.js';
import { esc, chip, uuidCell, shortId, fmtDate, sortTh, sortedBy, toggleSort } from '../utils.js';
import { req, runAction } from '../api.js';
import { notify, confirmAction, renderPagination, showSkeleton, hideSkeleton, smoothUpdate, markRefreshing, openModal } from '../ui.js';

/* ── Callback setters (injected from app.js) ───────── */
let _refreshAll = () => {};
let _render = () => {};
let _setTab = () => {};
export function setCallbacks(refreshAll, render, setTab) { _refreshAll = refreshAll; _render = render; if (setTab) _setTab = setTab; }

/* ── Load users ─────────────────────────────────────── */
export async function loadUsers() {
  const params = new URLSearchParams();
  const search = refs.usersSearch.value.trim(); if (search) params.set("search", search);
  const statusVal = refs.usersStatus.value; if (statusVal) params.set("is_active", statusVal);
  params.set("limit", String(state.usersLimit)); params.set("offset", String(state.usersOffset));
  showSkeleton("users-body", 5);
  markRefreshing("users-body");
  try {
    const data = await req(`/api/v1/users?${params}`);
    state.users = data.items || []; state.usersTotal = data.total || 0;
    renderUsers();
  } catch (e) {
    hideSkeleton("users-body");
    throw e;
  }
}

/* ── Comparators ────────────────────────────────────── */
const usersComparators = {
  telegram_id: (a, b) => a.telegram_id - b.telegram_id,
  username: (a, b) => (a.username || "").localeCompare(b.username || ""),
  tag: (a, b) => (a.tag || "").localeCompare(b.tag || ""),
  balance: (a, b) => Number(a.balance) - Number(b.balance),
  status: (a, b) => (a.is_active === b.is_active ? 0 : a.is_active ? -1 : 1),
  created_at: (a, b) => new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime(),
};

/* ── Render users table ─────────────────────────────── */
export function renderUsers() {
  refs.usersHead.innerHTML = `<tr>${sortTh("users", "id", "ID")}${sortTh("users", "telegram_id", "Telegram ID")}${sortTh("users", "username", "Username")}${sortTh("users", "tag", "Tag")}${sortTh("users", "balance", "Баланс")}<th>Subs</th><th>Keys</th>${sortTh("users", "status", "Статус")}${sortTh("users", "created_at", "Создан")}<th>Действия</th></tr>`;
  const sorted = sortedBy([...state.users], "users", usersComparators);
  const html = sorted.length
    ? sorted.map((u) => `<tr data-focusable tabindex="0">
        <td>${uuidCell(u.id)}</td>
        <td class="mono">${esc(u.telegram_id)}</td>
        <td>${esc(u.username || "-")}</td>
        <td>${u.tag ? chip("info", u.tag) : '<span class="muted">-</span>'}</td>
        <td class="mono">${esc(u.balance)}</td>
        <td class="mono muted">-</td>
        <td class="mono muted">-</td>
        <td>${u.is_active ? chip("ok", "active") : chip("bad", "inactive")}</td>
        <td style="white-space:nowrap">${fmtDate(u.created_at)}</td>
        <td><div class="actions"><button class="btn-mini usr-edit-btn" data-user-id="${esc(u.id)}">Edit</button><button class="btn-mini usr-subs-btn" data-user-id="${esc(u.id)}" data-username="${esc(u.username || "")}" data-tg="${esc(u.telegram_id)}">Subs</button></div></td>
      </tr>`).join("")
    : `<tr><td colspan="10"><div class="empty-state"><div class="empty-state-icon">\uD83D\uDC65</div><div class="empty-state-title">Нет пользователей</div><div class="empty-state-hint">Нажмите Загрузить или создайте нового пользователя</div></div></td></tr>`;
  smoothUpdate("users-body", html);
  renderPagination(refs.usersPagination, state.usersTotal, state.usersLimit, state.usersOffset, (page) => {
    state.usersOffset = page * state.usersLimit;
    loadUsers().catch((e) => notify("Ошибка: " + e.message, true));
  });
}

/* ── User edit modal ────────────────────────────────── */
export function openUserEditModal(userId) {
  runAction("Load user", () => req(`/api/v1/users/${encodeURIComponent(userId)}`))
    .then((user) => {
      const bodyHtml = `
        <div class="form-section"><div class="form-section-title">Информация</div>
          <div class="stat-inline-row">
            <div class="stat-inline">ID: ${uuidCell(user.id)}</div>
            <div class="stat-inline">TG: <strong>${esc(user.telegram_id)}</strong></div>
            <div class="stat-inline">Создан: <strong>${fmtDate(user.created_at)}</strong></div>
          </div>
          <div class="mini-kpi-row">
            <div class="mini-kpi"><div class="mini-kpi-label">Подписки</div><div class="mini-kpi-value">${esc(user.subscription_count != null ? user.subscription_count : "-")}</div></div>
            <div class="mini-kpi"><div class="mini-kpi-label">Ключи</div><div class="mini-kpi-value">${esc(user.key_count != null ? user.key_count : "-")}</div></div>
          </div>
        </div>
        <div class="form-section"><div class="form-section-title">Редактирование</div>
          <div class="form-group"><label class="form-label">Username</label><input class="input" id="usr-edit-username" value="${esc(user.username || "")}" /></div>
          <div class="form-group"><label class="form-label">Tag</label><input class="input" id="usr-edit-tag" value="${esc(user.tag || "")}" /></div>
          <div class="form-group"><label class="form-label">Описание</label><textarea class="input textarea-resize" id="usr-edit-desc" rows="2">${esc(user.description || "")}</textarea></div>
          <div class="row-2">
            <div class="form-group"><label class="form-label">Баланс</label><input class="input mono" id="usr-edit-balance" type="number" step="0.01" value="${esc(user.balance)}" /></div>
            <div class="form-group"><label class="form-label">Статус</label><label class="checkbox-inline muted"><input type="checkbox" id="usr-edit-active" ${user.is_active ? "checked" : ""} /> Активен</label></div>
          </div>
        </div>
        <div class="form-section"><div class="form-section-title">Быстрые действия</div>
          <div class="actions">
            <button class="btn-mini btn-info" data-act="view-subs">Подписки пользователя</button>
            <button class="btn-mini btn-primary" data-act="create-sub">Создать подписку</button>
          </div>
        </div>
        <div class="danger-zone"><div class="danger-zone-title">Опасная зона</div>
          <button class="btn btn-danger btn-auto" data-act="deactivate">Деактивировать пользователя</button>
        </div>`;
      const footerHtml = `<button class="btn btn-ghost" data-act="cancel">Отмена</button><button class="btn btn-primary" data-act="save">Сохранить</button>`;
      openModal({
        title: "Редактировать пользователя",
        bodyHtml,
        footerHtml,
        wide: true,
        onMount: ({ root, close }) => {
          root.querySelector('[data-act="cancel"]').addEventListener("click", close);
          root.querySelector('[data-act="save"]').addEventListener("click", () => {
            const payload = {};
            payload.username = root.querySelector("#usr-edit-username").value.trim() || null;
            payload.tag = root.querySelector("#usr-edit-tag").value.trim() || null;
            payload.description = root.querySelector("#usr-edit-desc").value.trim() || null;
            const balance = root.querySelector("#usr-edit-balance").value.trim(); if (balance !== "") payload.balance = balance;
            payload.is_active = root.querySelector("#usr-edit-active").checked;
            close();
            runAction("Update user", () => req(`/api/v1/users/${encodeURIComponent(userId)}`, { method: "PATCH", body: payload })).then(() => loadUsers()).catch(() => {});
          });
          root.querySelector('[data-act="deactivate"]').addEventListener("click", async () => {
            close();
            const ok = await confirmAction("Деактивация пользователя", `Деактивировать пользователя ${shortId(userId)}...?`); if (!ok) return;
            runAction("Deactivate user", () => req(`/api/v1/users/${encodeURIComponent(userId)}`, { method: "DELETE" })).then(() => loadUsers()).catch(() => {});
          });
          root.querySelector('[data-act="view-subs"]').addEventListener("click", () => {
            close();
            navigateToUserSubscriptions(userId, user.username, user.telegram_id);
          });
          root.querySelector('[data-act="create-sub"]').addEventListener("click", () => {
            close();
            _setTab("subscriptions");
            state.subCreateOpen = true;
            refs.subCreateContent.style.maxHeight = "600px";
            refs.subCreateArrow.style.transform = "rotate(180deg)";
            const userIdInput = refs.formSubCreate.querySelector('input[name="user_id"]');
            if (userIdInput) userIdInput.value = userId;
          });
        },
      });
    }).catch(() => {});
}

/* ── Navigate to user subscriptions ─────────────────── */
export function navigateToUserSubscriptions(userId, username, telegramId) {
  state.subscriptionContext = { userId, username: username || null, telegramId: telegramId || null };
  _setTab("subscriptions");
  refs.subFilterUser.value = userId;
  // Import renderSubUserContext dynamically to avoid circular deps
  import('./subscriptions.js').then((subMod) => {
    subMod.renderSubUserContext();
  });
  runAction("List subscriptions by user", () => req(`/api/v1/subscriptions/by-user/${encodeURIComponent(userId)}?active_only=false`))
    .then((rows) => { state.subscriptions = Array.isArray(rows) ? rows : []; _render(); }).catch(() => {});
}

/* ── Bind user event listeners ──────────────────────── */
export function bindUserEvents() {
  refs.usersHead.addEventListener("click", (ev) => {
    const th = ev.target.closest(".sortable[data-sort-key]");
    if (th) toggleSort(th.dataset.sortTable, th.dataset.sortKey);
  });
  refs.usersReload.addEventListener("click", () => { state.usersOffset = 0; loadUsers().catch((e) => notify("Ошибка: " + e.message, true)); });
  refs.usersSearch.addEventListener("keydown", (e) => { if (e.key === "Enter") { state.usersOffset = 0; loadUsers().catch((e2) => notify("Ошибка: " + e2.message, true)); } });
  refs.usersStatus.addEventListener("change", () => { state.usersOffset = 0; loadUsers().catch((e) => notify("Ошибка: " + e.message, true)); });

  /* User create modal */
  refs.usersCreateBtn.addEventListener("click", () => {
    const bodyHtml = `
      <div class="form-section"><div class="form-section-title">Идентификация</div>
        <div class="form-group"><label class="form-label">Telegram ID (обязательно)</label><input class="input mono" id="usr-create-tg" type="number" required /></div>
        <div class="form-group"><label class="form-label">Username</label><input class="input" id="usr-create-username" placeholder="Опционально" /></div>
      </div>
      <div class="form-section"><div class="form-section-title">Мета-данные</div>
        <div class="form-group"><label class="form-label">Tag</label><input class="input" id="usr-create-tag" placeholder="Опционально (напр. vip, test)" /></div>
        <div class="form-group"><label class="form-label">Описание</label><textarea class="input textarea-resize" id="usr-create-desc" rows="2" placeholder="Опционально"></textarea></div>
      </div>`;
    const footerHtml = `<button class="btn btn-ghost" data-act="cancel">Отмена</button><button class="btn btn-primary" data-act="save">Создать</button>`;
    openModal({
      title: "Создать пользователя",
      bodyHtml,
      footerHtml,
      wide: true,
      onMount: ({ root, close }) => {
        root.querySelector('[data-act="cancel"]').addEventListener("click", close);
        root.querySelector('[data-act="save"]').addEventListener("click", () => {
          const tgId = root.querySelector("#usr-create-tg").value.trim();
          if (!tgId) { notify("telegram_id обязателен", true); return; }
          const payload = { telegram_id: Number(tgId) };
          const username = root.querySelector("#usr-create-username").value.trim(); if (username) payload.username = username;
          const tag = root.querySelector("#usr-create-tag").value.trim(); if (tag) payload.tag = tag;
          const desc = root.querySelector("#usr-create-desc").value.trim(); if (desc) payload.description = desc;
          close();
          runAction("Create user", () => req("/api/v1/users", { method: "POST", body: payload })).then(() => loadUsers()).catch(() => {});
        });
      },
    });
  });

  /* Users click delegation */
  refs.usersBody.addEventListener("click", (ev) => {
    const editBtn = ev.target.closest(".usr-edit-btn");
    if (editBtn) { openUserEditModal(editBtn.dataset.userId); return; }
    const subsBtn = ev.target.closest(".usr-subs-btn");
    if (subsBtn) { navigateToUserSubscriptions(subsBtn.dataset.userId, subsBtn.dataset.username, subsBtn.dataset.tg); }
  });
}
