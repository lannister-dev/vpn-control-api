import { state, refs, $ } from '../state.js';
import { esc, chip, fmtDate, uuidCell } from '../utils.js';
import { req } from '../api.js';
import { notify, confirmAction, showModal, hideModal, showSkeleton, hideSkeleton, smoothUpdate, markRefreshing } from '../ui.js';

/* Local refs */
const auBody = $("au-body"), auMeta = $("au-meta"), auSearch = $("au-search"), auRole = $("au-role"), auStatus = $("au-status"), auReload = $("au-reload");
const auCreateBtn = $("au-create-btn"), auCreateModal = $("au-create-modal"), auCreateForm = $("au-create-form"), auCreateCancel = $("au-create-cancel");
const auEditModal = $("au-edit-modal"), auEditForm = $("au-edit-form"), auEditCancel = $("au-edit-cancel"), auEditName = $("au-edit-name");
const auEditUid = $("au-edit-uid"), auEditRole = $("au-edit-role"), auEditActive = $("au-edit-active");
const auPwForm = $("au-pw-form"), auRevokeSessions = $("au-revoke-sessions"), auDeleteUser = $("au-delete-user"), auEditSessionsCount = $("au-edit-sessions-count");

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
  if (!state.adminUsers.length) { smoothUpdate("au-body", `<tr><td colspan="7" class="empty">\u041D\u0435\u0442 \u043F\u043E\u043B\u044C\u0437\u043E\u0432\u0430\u0442\u0435\u043B\u0435\u0439.</td></tr>`); auMeta.textContent = ""; return; }
  const html = state.adminUsers.map((u) => {
    const roleCls = u.role === "admin" ? "bad" : (u.role === "operator" ? "warn" : "info");
    const statusCls = u.is_active ? "ok" : "warn";
    return `<tr><td>${esc(u.username)}</td><td>${chip(roleCls, u.role)}</td><td>${chip(statusCls, u.is_active ? "active" : "inactive")}</td><td class="mono">${u.telegram_id ? esc(u.telegram_id) : "-"}</td><td>-</td><td style="white-space:nowrap;">${fmtDate(u.created_at)}</td><td><button class="btn-mini au-edit-btn" data-uid="${esc(u.id)}" data-uname="${esc(u.username)}" data-urole="${esc(u.role)}" data-uactive="${u.is_active}">Edit</button></td></tr>`;
  }).join("");
  smoothUpdate("au-body", html);
  auMeta.textContent = `\u041F\u043E\u043A\u0430\u0437\u0430\u043D\u043E ${state.adminUsers.length} \u0438\u0437 ${state.adminUsersTotal}`;
}

export async function openEditModal(uid, uname, urole, uactive) {
  auEditUid.value = uid; auEditName.textContent = uname; auEditRole.value = urole; auEditActive.value = String(uactive);
  auEditSessionsCount.textContent = "..."; showModal(auEditModal);
  try { const data = await req(`/api/v1/auth/admin/users/${uid}/sessions`); auEditSessionsCount.textContent = String(data.total || 0); }
  catch (_) { auEditSessionsCount.textContent = "?"; }
}

export function bindAdminUserEvents() {
  auCreateBtn.addEventListener("click", () => { auCreateForm.reset(); showModal(auCreateModal); });
  auCreateCancel.addEventListener("click", () => hideModal(auCreateModal));
  auCreateModal.addEventListener("click", (e) => { if (e.target === auCreateModal) hideModal(auCreateModal); });

  auCreateForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(auCreateForm);
    const body = { username: fd.get("username"), role: fd.get("role") };
    const pw = fd.get("password"); if (pw) body.password = pw;
    const tgId = fd.get("telegram_id"); if (tgId) body.telegram_id = Number(tgId);
    try { await req("/api/v1/auth/admin/users", { method: "POST", body }); notify("\u041F\u043E\u043B\u044C\u0437\u043E\u0432\u0430\u0442\u0435\u043B\u044C \u0441\u043E\u0437\u0434\u0430\u043D", false); hideModal(auCreateModal); await loadAdminUsers(); }
    catch (err) { notify("\u041E\u0448\u0438\u0431\u043A\u0430: " + err.message, true); }
  });

  auEditCancel.addEventListener("click", () => hideModal(auEditModal));
  auEditModal.addEventListener("click", (e) => { if (e.target === auEditModal) hideModal(auEditModal); });

  auEditForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const uid = auEditUid.value;
    const body = { role: auEditRole.value, is_active: auEditActive.value === "true" };
    try { await req(`/api/v1/auth/admin/users/${uid}`, { method: "PATCH", body }); notify("\u041F\u043E\u043B\u044C\u0437\u043E\u0432\u0430\u0442\u0435\u043B\u044C \u043E\u0431\u043D\u043E\u0432\u043B\u0435\u043D", false); hideModal(auEditModal); await loadAdminUsers(); }
    catch (err) { notify("\u041E\u0448\u0438\u0431\u043A\u0430: " + err.message, true); }
  });

  auPwForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const uid = auEditUid.value; const fd = new FormData(auPwForm);
    try { await req(`/api/v1/auth/admin/users/${uid}/reset-password`, { method: "POST", body: { new_password: fd.get("new_password") } }); notify("\u041F\u0430\u0440\u043E\u043B\u044C \u0441\u0431\u0440\u043E\u0448\u0435\u043D", false); auPwForm.reset(); }
    catch (err) { notify("\u041E\u0448\u0438\u0431\u043A\u0430: " + err.message, true); }
  });

  auRevokeSessions.addEventListener("click", async () => {
    const uid = auEditUid.value;
    try { const r = await req(`/api/v1/auth/admin/users/${uid}/revoke-sessions`, { method: "POST" }); notify(`\u041E\u0442\u043E\u0437\u0432\u0430\u043D\u043E \u0441\u0435\u0441\u0441\u0438\u0439: ${r.revoked}`, false); auEditSessionsCount.textContent = "0"; }
    catch (err) { notify("\u041E\u0448\u0438\u0431\u043A\u0430: " + err.message, true); }
  });

  auDeleteUser.addEventListener("click", async () => {
    const uid = auEditUid.value; const name = auEditName.textContent;
    const confirmed = await confirmAction(`\u0423\u0434\u0430\u043B\u0438\u0442\u044C \u043F\u043E\u043B\u044C\u0437\u043E\u0432\u0430\u0442\u0435\u043B\u044F?`, `\u042D\u0442\u043E \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435 \u0443\u0434\u0430\u043B\u0438\u0442 \u043F\u043E\u043B\u044C\u0437\u043E\u0432\u0430\u0442\u0435\u043B\u044F "${esc(name)}" \u043D\u0430\u0432\u0441\u0435\u0433\u0434\u0430. \u0415\u0433\u043E \u043D\u0435\u043B\u044C\u0437\u044F \u0431\u0443\u0434\u0435\u0442 \u0432\u043E\u0441\u0441\u0442\u0430\u043D\u043E\u0432\u0438\u0442\u044C.`, "btn-danger");
    if (!confirmed) return;
    try { await req(`/api/v1/auth/admin/users/${uid}`, { method: "DELETE" }); notify("\u041F\u043E\u043B\u044C\u0437\u043E\u0432\u0430\u0442\u0435\u043B\u044C \u0443\u0434\u0430\u043B\u0435\u043D", false); hideModal(auEditModal); await loadAdminUsers(); }
    catch (err) { notify("\u041E\u0448\u0438\u0431\u043A\u0430: " + err.message, true); }
  });

  auReload.addEventListener("click", () => loadAdminUsers().catch((e) => notify("\u041E\u0448\u0438\u0431\u043A\u0430: " + e.message, true)));
  auSearch.addEventListener("input", () => loadAdminUsers().catch(() => {}));
  auRole.addEventListener("change", () => loadAdminUsers().catch(() => {}));
  auStatus.addEventListener("change", () => loadAdminUsers().catch(() => {}));
}
