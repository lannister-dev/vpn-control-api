import { state, refs, $ } from '../state.js';
import { esc, chip, uuidCell, shortId, fmtDate, sortTh, sortedBy, toggleSort } from '../utils.js';
import { req, runAction } from '../api.js';
import { notify, confirmAction, renderPagination, showSkeleton, hideSkeleton, smoothUpdate, markRefreshing } from '../ui.js';

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
      refs.confirmModal.innerHTML = `
        <div class="modal-overlay"><div class="modal-box wide">
          <div class="modal-title">Редактировать пользователя</div>
          <div class="modal-body">
            <div class="form-section"><div class="form-section-title">Информация</div>
              <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px">
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
              <div class="form-group"><label class="form-label">Описание</label><textarea class="input" id="usr-edit-desc" rows="2" style="resize:vertical">${esc(user.description || "")}</textarea></div>
              <div class="row-2">
                <div class="form-group"><label class="form-label">Баланс</label><input class="input mono" id="usr-edit-balance" type="number" step="0.01" value="${esc(user.balance)}" /></div>
                <div class="form-group"><label class="form-label">Статус</label><label class="muted" style="display:flex;align-items:center;gap:6px;margin-top:6px"><input type="checkbox" id="usr-edit-active" ${user.is_active ? "checked" : ""} /> Активен</label></div>
              </div>
            </div>
            <div class="form-section"><div class="form-section-title">Быстрые действия</div>
              <div class="actions">
                <button class="btn-mini btn-info" data-confirm="view-subs">Подписки пользователя</button>
                <button class="btn-mini btn-primary" data-confirm="create-sub">Создать подписку</button>
              </div>
            </div>
            <div class="danger-zone"><div class="danger-zone-title">Опасная зона</div>
              <button class="btn btn-danger" data-confirm="deactivate" style="width:auto;padding:8px 16px">Деактивировать пользователя</button>
            </div>
          </div>
          <div class="modal-actions">
            <button class="btn btn-ghost" data-confirm="cancel">Отмена</button>
            <button class="btn btn-primary" data-confirm="ok">Сохранить</button>
          </div>
        </div></div>`;
      const cleanup = () => { refs.confirmModal.innerHTML = ""; };
      refs.confirmModal.querySelector('[data-confirm="cancel"]').addEventListener("click", cleanup);
      refs.confirmModal.querySelector(".modal-overlay").addEventListener("click", (ev) => { if (ev.target === ev.currentTarget) cleanup(); });
      refs.confirmModal.querySelector('[data-confirm="ok"]').addEventListener("click", () => {
        const payload = {};
        payload.username = document.getElementById("usr-edit-username").value.trim() || null;
        payload.tag = document.getElementById("usr-edit-tag").value.trim() || null;
        payload.description = document.getElementById("usr-edit-desc").value.trim() || null;
        const balance = document.getElementById("usr-edit-balance").value.trim(); if (balance !== "") payload.balance = balance;
        payload.is_active = document.getElementById("usr-edit-active").checked;
        cleanup();
        runAction("Update user", () => req(`/api/v1/users/${encodeURIComponent(userId)}`, { method: "PATCH", body: payload })).then(() => loadUsers()).catch(() => {});
      });
      refs.confirmModal.querySelector('[data-confirm="deactivate"]').addEventListener("click", async () => {
        cleanup();
        const ok = await confirmAction("Деактивация пользователя", `Деактивировать пользователя ${shortId(userId)}...?`); if (!ok) return;
        runAction("Deactivate user", () => req(`/api/v1/users/${encodeURIComponent(userId)}`, { method: "DELETE" })).then(() => loadUsers()).catch(() => {});
      });
      refs.confirmModal.querySelector('[data-confirm="view-subs"]').addEventListener("click", () => {
        cleanup();
        navigateToUserSubscriptions(userId, user.username, user.telegram_id);
      });
      refs.confirmModal.querySelector('[data-confirm="create-sub"]').addEventListener("click", () => {
        cleanup();
        _setTab("subscriptions");
        state.subCreateOpen = true;
        refs.subCreateContent.style.maxHeight = "600px";
        refs.subCreateArrow.style.transform = "rotate(180deg)";
        const userIdInput = refs.formSubCreate.querySelector('input[name="user_id"]');
        if (userIdInput) userIdInput.value = userId;
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
    refs.confirmModal.innerHTML = `
      <div class="modal-overlay"><div class="modal-box wide">
        <div class="modal-title">Создать пользователя</div>
        <div class="modal-body">
          <div class="form-section"><div class="form-section-title">Идентификация</div>
            <div class="form-group"><label class="form-label">Telegram ID (обязательно)</label><input class="input mono" id="usr-create-tg" type="number" required /></div>
            <div class="form-group"><label class="form-label">Username</label><input class="input" id="usr-create-username" placeholder="Опционально" /></div>
          </div>
          <div class="form-section"><div class="form-section-title">Мета-данные</div>
            <div class="form-group"><label class="form-label">Tag</label><input class="input" id="usr-create-tag" placeholder="Опционально (напр. vip, test)" /></div>
            <div class="form-group"><label class="form-label">Описание</label><textarea class="input" id="usr-create-desc" rows="2" placeholder="Опционально" style="resize:vertical"></textarea></div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" data-confirm="cancel">Отмена</button>
          <button class="btn btn-primary" data-confirm="ok">Создать</button>
        </div>
      </div></div>`;
    const cleanup = () => { refs.confirmModal.innerHTML = ""; };
    refs.confirmModal.querySelector('[data-confirm="cancel"]').addEventListener("click", cleanup);
    refs.confirmModal.querySelector(".modal-overlay").addEventListener("click", (ev) => { if (ev.target === ev.currentTarget) cleanup(); });
    refs.confirmModal.querySelector('[data-confirm="ok"]').addEventListener("click", () => {
      const tgId = document.getElementById("usr-create-tg").value.trim();
      if (!tgId) { notify("telegram_id обязателен", true); return; }
      const payload = { telegram_id: Number(tgId) };
      const username = document.getElementById("usr-create-username").value.trim(); if (username) payload.username = username;
      const tag = document.getElementById("usr-create-tag").value.trim(); if (tag) payload.tag = tag;
      const desc = document.getElementById("usr-create-desc").value.trim(); if (desc) payload.description = desc;
      cleanup();
      runAction("Create user", () => req("/api/v1/users", { method: "POST", body: payload })).then(() => loadUsers()).catch(() => {});
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
