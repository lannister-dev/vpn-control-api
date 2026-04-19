import { state, refs, $ } from '../state.js';
import { esc, chip, fmtDate, uuidCell } from '../utils.js';
import { req } from '../api.js';
import { notify, confirmAction, showSkeleton, hideSkeleton, smoothUpdate, markRefreshing, openModal } from '../ui.js';

/* Local refs */
const auBody = $("au-body"), auMeta = $("au-meta"), auSearch = $("au-search"), auRole = $("au-role"), auStatus = $("au-status"), auReload = $("au-reload");
const auCreateBtn = $("au-create-btn");

export async function loadAdminUsers() {
  const params = new URLSearchParams();
  const s = auSearch.value.trim(); if (s) params.set("search", s);
  const r = auRole.value; if (r) params.set("role", r);
  const a = auStatus.value; if (a) params.set("is_active", a);
  params.set("limit", "100");
  showSkeleton("au-body", 5);
  markRefreshing("au-body");
  try {
    const data = await req(`/api/v1/auth/admin/users?${params}`);
    state.adminUsers = data.items || []; state.adminUsersTotal = data.total || 0;
    renderAdminUsers();
  } catch (e) {
    hideSkeleton("au-body");
    throw e;
  }
}

export function renderAdminUsers() {
  if (!state.adminUsers.length) {
    smoothUpdate("au-body", `<tr><td colspan="7"><div class="empty-state"><div class="empty-state-icon">\u2699</div><div class="empty-state-title">Админов пока нет</div><div class="empty-state-hint">Создайте первого админа панели.</div><div class="empty-state-action"><button class="btn btn-primary au-empty-create btn-auto">+ Создать</button></div></div></td></tr>`);
    auMeta.textContent = "";
    return;
  }
  const html = state.adminUsers.map((u) => {
    const roleCls = u.role === "admin" ? "bad" : (u.role === "operator" ? "warn" : "info");
    const statusCls = u.is_active ? "ok" : "warn";
    return `<tr><td>${esc(u.username)}</td><td>${chip(roleCls, u.role)}</td><td>${chip(statusCls, u.is_active ? "active" : "inactive")}</td><td class="mono">${u.telegram_id ? esc(u.telegram_id) : "-"}</td><td>-</td><td class="nowrap">${fmtDate(u.created_at)}</td><td><button class="btn-mini au-edit-btn" data-uid="${esc(u.id)}" data-uname="${esc(u.username)}" data-urole="${esc(u.role)}" data-uactive="${u.is_active}">Edit</button></td></tr>`;
  }).join("");
  smoothUpdate("au-body", html);
  auMeta.textContent = `\u041F\u043E\u043A\u0430\u0437\u0430\u043D\u043E ${state.adminUsers.length} \u0438\u0437 ${state.adminUsersTotal}`;
}

function openCreateModal() {
  const bodyHtml = `
    <form id="au-form" class="stack">
      <div class="form-group"><label class="form-label">Username</label><input class="input mono" name="username" required minlength="1" maxlength="64" /></div>
      <div class="form-group"><label class="form-label">Пароль <span class="muted">(мин. 8 символов)</span></label><input class="input mono" name="password" type="password" minlength="8" maxlength="256" /></div>
      <div class="form-group"><label class="form-label">Telegram ID <span class="muted">(опционально)</span></label><input class="input mono" name="telegram_id" type="number" /></div>
      <div class="form-group"><label class="form-label">Роль</label><select class="select" name="role"><option value="viewer">viewer</option><option value="operator">operator</option><option value="admin">admin</option></select></div>
    </form>`;
  const footerHtml = `<button class="btn btn-ghost" data-act="cancel">Отмена</button><button class="btn btn-primary" data-act="save">Создать</button>`;
  openModal({
    title: "Новый admin user",
    bodyHtml,
    footerHtml,
    onMount: ({ root, close }) => {
      root.querySelector('[data-act="cancel"]').addEventListener("click", close);
      root.querySelector('[data-act="save"]').addEventListener("click", async () => {
        const form = root.querySelector("#au-form");
        const fd = new FormData(form);
        const body = { username: fd.get("username"), role: fd.get("role") };
        const pw = fd.get("password"); if (pw) body.password = pw;
        const tgId = fd.get("telegram_id"); if (tgId) body.telegram_id = Number(tgId);
        try {
          await req("/api/v1/auth/admin/users", { method: "POST", body });
          notify("Пользователь создан", false);
          close();
          await loadAdminUsers();
        } catch (err) {
          notify("Ошибка: " + err.message, true);
        }
      });
    },
  });
}

export async function openEditModal(uid, uname, urole, uactive) {
  const bodyHtml = `
    <form id="au-edit-form" class="stack">
      <input type="hidden" name="user_id" value="${esc(uid)}" />
      <div class="form-group"><label class="form-label">Роль</label>
        <select class="select" name="role">
          <option value="viewer" ${urole === "viewer" ? "selected" : ""}>viewer</option>
          <option value="operator" ${urole === "operator" ? "selected" : ""}>operator</option>
          <option value="admin" ${urole === "admin" ? "selected" : ""}>admin</option>
        </select>
      </div>
      <div class="form-group"><label class="form-label">Статус</label>
        <select class="select" name="is_active">
          <option value="true" ${uactive ? "selected" : ""}>Активен</option>
          <option value="false" ${!uactive ? "selected" : ""}>Деактивирован</option>
        </select>
      </div>
    </form>
    <div class="form-section"><div class="form-section-title">Пароль</div>
      <form id="au-pw-form" class="stack">
        <input class="input mono" name="new_password" type="password" placeholder="Новый пароль (мин. 8 символов)" minlength="8" required />
        <button class="btn btn-warn btn-auto" type="submit">Сбросить пароль</button>
      </form>
    </div>
    <div class="form-section"><div class="form-section-title">Сессии: <span id="au-sessions-count">…</span></div>
      <button class="btn btn-warn btn-auto" data-act="revoke-sessions">Отозвать все сессии</button>
    </div>
    <div class="danger-zone"><div class="danger-zone-title">Опасная зона</div>
      <button class="btn btn-danger btn-auto" data-act="delete-user">Удалить пользователя</button>
    </div>`;
  const footerHtml = `<button class="btn btn-ghost" data-act="cancel">Отмена</button><button class="btn btn-primary" data-act="save">Сохранить</button>`;
  const handle = openModal({
    title: `Редактировать: ${uname}`,
    bodyHtml,
    footerHtml,
    onMount: ({ root, close }) => {
      root.querySelector('[data-act="cancel"]').addEventListener("click", close);
      root.querySelector('[data-act="save"]').addEventListener("click", async () => {
        const form = root.querySelector("#au-edit-form");
        const fd = new FormData(form);
        const body = { role: fd.get("role"), is_active: fd.get("is_active") === "true" };
        try {
          await req(`/api/v1/auth/admin/users/${uid}`, { method: "PATCH", body });
          notify("Пользователь обновлён", false);
          close();
          await loadAdminUsers();
        } catch (err) { notify("Ошибка: " + err.message, true); }
      });
      root.querySelector("#au-pw-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const fd = new FormData(e.currentTarget);
        try {
          await req(`/api/v1/auth/admin/users/${uid}/reset-password`, { method: "POST", body: { new_password: fd.get("new_password") } });
          notify("Пароль сброшен", false);
          e.currentTarget.reset();
        } catch (err) { notify("Ошибка: " + err.message, true); }
      });
      root.querySelector('[data-act="revoke-sessions"]').addEventListener("click", async () => {
        try {
          const r = await req(`/api/v1/auth/admin/users/${uid}/revoke-sessions`, { method: "POST" });
          notify(`Отозвано сессий: ${r.revoked}`, false);
          const el = root.querySelector("#au-sessions-count"); if (el) el.textContent = "0";
        } catch (err) { notify("Ошибка: " + err.message, true); }
      });
      root.querySelector('[data-act="delete-user"]').addEventListener("click", async () => {
        const confirmed = await confirmAction(
          "Удалить пользователя?",
          `Это действие удалит пользователя "${esc(uname)}" навсегда. Его нельзя будет восстановить.`,
          "btn-danger"
        );
        if (!confirmed) return;
        try {
          await req(`/api/v1/auth/admin/users/${uid}`, { method: "DELETE" });
          notify("Пользователь удалён", false);
          close();
          await loadAdminUsers();
        } catch (err) { notify("Ошибка: " + err.message, true); }
      });
    },
  });
  /* Load sessions count async after mount. */
  try {
    const data = await req(`/api/v1/auth/admin/users/${uid}/sessions`);
    const el = handle.root.querySelector("#au-sessions-count");
    if (el) el.textContent = String(data.total || 0);
  } catch (_) {
    const el = handle.root.querySelector("#au-sessions-count");
    if (el) el.textContent = "?";
  }
}

export function bindAdminUserEvents() {
  auCreateBtn.addEventListener("click", () => openCreateModal());
  auBody.addEventListener("click", (ev) => {
    const empty = ev.target.closest(".au-empty-create");
    if (empty) { openCreateModal(); return; }
  });
  auReload.addEventListener("click", () => loadAdminUsers().catch((e) => notify("\u041E\u0448\u0438\u0431\u043A\u0430: " + e.message, true)));
  auSearch.addEventListener("input", () => loadAdminUsers().catch(() => {}));
  auRole.addEventListener("change", () => loadAdminUsers().catch(() => {}));
  auStatus.addEventListener("change", () => loadAdminUsers().catch(() => {}));
}
