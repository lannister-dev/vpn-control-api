import { state, refs, $, TABLE_LIMIT } from '../state.js';
import { esc, chip, uuidCell, shortId, fmtDate, relTime, fmtTrafficLimit, transportLabel, parseDateTimeLocal, renderTransportBundle } from '../utils.js';
import { req, runAction, copyToClipboard } from '../api.js';
import { notify, confirmAction, renderPagination } from '../ui.js';

/* ── Callback setters (injected from app.js) ───────── */
let _refreshAll = () => {};
let _render = () => {};
let _setTab = () => {};
export function setCallbacks(refreshAll, render, setTab) { _refreshAll = refreshAll; _render = render; if (setTab) _setTab = setTab; }

/* ── Filtered subscriptions ────────────────────────── */
export function filteredSubscriptions() { return state.subscriptions.slice(0, TABLE_LIMIT); }

/* ── Render subscriptions table (called inside render()) ─ */
export function renderSubscriptions() {
  const subs = filteredSubscriptions();
  refs.subsBody.innerHTML = subs.length
    ? subs.map((s) => `<tr class="sub-row" data-sub-id="${esc(s.id)}">
        <td>${uuidCell(s.id)}</td>
        <td>${uuidCell(s.user_id)}</td>
        <td>${s.plan_name ? chip("info", s.plan_name) : '<span class="muted">-</span>'}</td>
        <td>${s.is_active ? chip("ok", "active") : chip("bad", "inactive")}</td>
        <td>${s.hwid_enabled ? chip("info", "on") : chip("warn", "off")}</td>
        <td class="mono">${esc(s.max_devices == null ? "-" : s.max_devices)}</td>
        <td>${s.used_traffic_bytes != null && s.used_traffic_bytes > 0 ? fmtTrafficLimit(s.used_traffic_bytes) : "-"}</td>
        <td><span title="${esc(fmtDate(s.expires_at))}">${relTime(s.expires_at)}</span></td>
        <td>${fmtDate(s.created_at || s.updated_at)}</td>
        <td><div class="actions"><button class="btn-mini sub-open-btn" data-sub-id="${esc(s.id)}">Open</button><button class="btn-mini sub-devices-btn" data-sub-id="${esc(s.id)}">Devices</button></div></td>
      </tr>`).join("")
    : `<tr><td colspan="10"><div class="empty-state"><div class="empty-state-icon">S</div><div class="empty-state-title">Нет подписок</div><div class="empty-state-desc">Используйте поиск по User ID или создайте новую подписку</div></div></td></tr>`;

  /* Update subscription plan filter dropdown */
  renderSubPlanFilter();
}

/* ── Subscription plan filter dropdown ──────────────── */
export function renderSubPlanFilter() {
  const sel = refs.subFilterPlan;
  if (!sel) return;
  const cur = sel.value;
  sel.innerHTML = `<option value="">Все тарифы</option>` + state.plans.filter((p) => p.is_active).map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("");
  if (cur) sel.value = cur;
}

/* ── Subscription user context banner ───────────────── */
export function renderSubUserContext() {
  const ctx = state.subscriptionContext;
  if (!ctx) { refs.subUserContext.innerHTML = ""; return; }
  refs.subUserContext.innerHTML = `<div class="user-context">
    <div class="user-context-info">
      <span style="font-weight:700;font-size:14px">Подписки пользователя</span>
      ${uuidCell(ctx.userId)}
      ${ctx.username ? `<span class="muted">${esc(ctx.username)}</span>` : ""}
      ${ctx.telegramId ? `<span class="stat-inline">TG: <strong>${esc(ctx.telegramId)}</strong></span>` : ""}
    </div>
    <button class="btn-mini sub-clear-context">Показать все</button>
  </div>`;
}

/* ── Subscription detail panel ──────────────────────── */
export function renderSubscriptionDetail(sub) {
  if (!sub) { refs.subDetailContainer.innerHTML = ""; state.selectedSubscription = null; return; }
  state.selectedSubscription = sub;
  const trafficUsed = sub.used_traffic_bytes || 0;
  const trafficInfo = trafficUsed > 0 ? fmtTrafficLimit(trafficUsed) : "0 B";
  refs.subDetailContainer.innerHTML = `<div class="detail-panel">
    <div class="detail-header">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <span style="font-weight:700;font-size:15px">Подписка</span>
        ${uuidCell(sub.id)}
        ${sub.is_active ? chip("ok", "active") : chip("bad", "inactive")}
        ${sub.plan_name ? chip("info", sub.plan_name) : ""}
      </div>
      <button class="btn-mini sub-detail-close">Закрыть</button>
    </div>
    <div class="detail-stats">
      <div class="detail-stat"><div class="detail-stat-label">Трафик</div><div class="detail-stat-value">${trafficInfo}</div></div>
      <div class="detail-stat"><div class="detail-stat-label">Устройства</div><div class="detail-stat-value">${esc(sub.max_devices == null ? "\u221E" : sub.max_devices)}</div></div>
      <div class="detail-stat"><div class="detail-stat-label">Истекает</div><div class="detail-stat-value" style="font-size:13px">${relTime(sub.expires_at)}</div></div>
      <div class="detail-stat"><div class="detail-stat-label">HWID</div><div class="detail-stat-value">${sub.hwid_enabled ? "On" : "Off"}</div></div>
    </div>
    <div class="detail-actions">
      <button class="btn-mini btn-warn sub-detail-rotate" data-sub-id="${esc(sub.id)}">Rotate Token</button>
      <button class="btn-mini btn-primary sub-detail-activate" data-sub-id="${esc(sub.id)}">Activate</button>
      <button class="btn-mini btn-danger sub-detail-deactivate" data-sub-id="${esc(sub.id)}">Deactivate</button>
      <button class="btn-mini sub-detail-devices" data-sub-id="${esc(sub.id)}">Show Devices</button>
      <button class="btn-mini sub-detail-edit" data-sub-id="${esc(sub.id)}">Edit</button>
    </div>
    <div id="sub-detail-edit-form" style="display:none;margin-top:10px">
      <div style="display:flex;align-items:flex-end;gap:8px">
        <div class="form-group" style="margin:0"><label class="form-label">Max devices</label><input class="input mono" id="sub-edit-max-devices" type="number" min="1" max="100" value="${sub.max_devices || ""}" style="width:80px" /></div>
        <button class="btn-mini btn-primary sub-edit-save" data-sub-id="${esc(sub.id)}">Сохранить</button>
        <button class="btn-mini sub-edit-cancel">Отмена</button>
      </div>
    </div>
    <div id="sub-detail-url"></div>
    <div id="sub-detail-token-info" class="muted" style="font-size:11px;margin-top:4px">${sub.last_token_rotated_at ? "Last token rotation: " + fmtDate(sub.last_token_rotated_at) : ""}</div>
  </div>`;
}

/* ── Subscription devices as cards ──────────────────── */
export function renderSubscriptionDevices(devices, subscriptionId) {
  if (!devices || !devices.length) {
    refs.subDevicesContainer.innerHTML = `<div class="detail-panel" style="margin-top:8px"><div class="empty-state"><div class="empty-state-icon">D</div><div class="empty-state-title">Нет устройств</div><div class="empty-state-desc">Устройства появятся после первого подключения по HWID</div></div></div>`;
    return;
  }
  const cards = devices.map((d) => {
    const hwidShort = d.hwid_hash ? shortId(d.hwid_hash, 12) : "-";
    const bundleBadges = Array.isArray(d.transport_keys) ? d.transport_keys.map((k) => chip(k.is_primary ? "info" : "ok", transportLabel(k.transport))).join(" ") : '<span class="muted">-</span>';
    return `<div class="device-card">
      <div class="device-card-head">
        <div>${uuidCell(d.id)} ${d.is_active ? chip("ok", "active") : chip("warn", "inactive")}</div>
        <button class="btn-mini btn-danger device-revoke-btn" data-sub-id="${esc(subscriptionId)}" data-device-id="${esc(d.id)}">Revoke</button>
      </div>
      <div class="device-meta">
        <div class="device-meta-row"><span class="muted">HWID</span><span class="mono" style="font-size:11px" title="${esc(d.hwid_hash || "")}">${esc(hwidShort)}</span></div>
        <div class="device-meta-row"><span class="muted">Bundle</span><span>${bundleBadges}</span></div>
        <div class="device-meta-row"><span class="muted">Last seen</span><span>${relTime(d.last_seen_at)}</span></div>
        <div class="device-meta-row"><span class="muted">User-Agent</span><span style="font-size:11px;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(d.user_agent || "")}">${esc(d.user_agent || "-")}</span></div>
      </div>
    </div>`;
  }).join("");
  refs.subDevicesContainer.innerHTML = `<div class="detail-panel" style="margin-top:8px">
    <div style="font-weight:600;font-size:13px;margin-bottom:10px">Устройства (${devices.length})</div>
    <div class="device-grid">${cards}</div>
  </div>`;
}

/* ── Subscription create result ─────────────────────── */
export function renderSubscriptionCreateResult(created) {
  if (!created) { refs.subCreateResult.innerHTML = `<div class="empty">После создания здесь появится токен и URL.</div>`; return; }
  refs.subCreateResult.innerHTML = `
    <div>${chip("ok", "Подписка создана")}</div>
    <div class="result-grid">
      <div class="result-row"><span class="muted">subscription_id</span><span class="mono">${uuidCell(created.id)}</span></div>
      <div class="result-row"><span class="muted">token</span><span class="mono">${esc(created.token)} <button class="btn-mini copy-value" data-copy="${esc(created.token)}">Копировать</button></span></div>
      <div class="result-row"><span class="muted">url</span><span class="mono">${esc(created.subscription_url)} <button class="btn-mini copy-value" data-copy="${esc(created.subscription_url)}">Копировать</button></span></div>
      <div class="result-row"><span class="muted">status</span><span>${created.is_active ? chip("ok", "active") : chip("bad", "inactive")}</span></div>
      <div class="result-row"><span class="muted">expires</span><span class="mono">${fmtDate(created.expires_at)}</span></div>
    </div>`;
}

/* ── Bind all subscription event listeners ──────────── */
export function bindSubscriptionEvents(setTab, render) {
  /* Collapse trigger for create form */
  refs.subCreateTrigger.addEventListener("click", () => {
    state.subCreateOpen = !state.subCreateOpen;
    refs.subCreateContent.style.maxHeight = state.subCreateOpen ? "600px" : "0";
    refs.subCreateArrow.style.transform = state.subCreateOpen ? "rotate(180deg)" : "rotate(0deg)";
  });

  /* Subscription create */
  refs.formSubCreate.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = new FormData(refs.formSubCreate);
    const payload = { user_id: String(d.get("user_id") || "").trim() };
    const planId = String(d.get("plan_id") || "").trim(); if (planId) payload.plan_id = planId;
    const preferredRegion = String(d.get("preferred_region") || "").trim(); if (preferredRegion) payload.preferred_region = preferredRegion;
    const maxDevices = String(d.get("max_devices") || "").trim(); if (maxDevices) payload.max_devices = Number(maxDevices);
    const expiresAt = parseDateTimeLocal(d.get("expires_at")); if (expiresAt) payload.expires_at = expiresAt;
    runAction("Create subscription", () => req("/api/v1/subscriptions", { method: "POST", body: payload }))
      .then((created) => {
        renderSubscriptionCreateResult(created);
        const createdSub = { id: created.id, user_id: payload.user_id, preferred_region: payload.preferred_region || null, is_active: created.is_active, expires_at: created.expires_at, hwid_enabled: true, max_devices: payload.max_devices || null, updated_at: new Date().toISOString() };
        state.subscriptions = [createdSub, ...state.subscriptions].slice(0, TABLE_LIMIT);
        _render();
      }).catch(() => {});
  });

  /* Subscription search */
  refs.subSearchBtn.addEventListener("click", () => {
    const userId = refs.subFilterUser.value.trim();
    const activeOnly = refs.subFilterActive.checked;
    if (!userId) { notify("Укажите User ID для поиска", true); return; }
    state.subscriptionContext = { userId, username: null, telegramId: null };
    renderSubUserContext();
    runAction("List subscriptions by user", () => req(`/api/v1/subscriptions/by-user/${encodeURIComponent(userId)}?active_only=${activeOnly ? "true" : "false"}`))
      .then((rows) => { state.subscriptions = Array.isArray(rows) ? rows : []; _render(); }).catch(() => {});
  });

  refs.subClearBtn.addEventListener("click", () => {
    refs.subFilterUser.value = ""; refs.subFilterActive.checked = false;
    state.subscriptionContext = null; state.selectedSubscription = null;
    refs.subUserContext.innerHTML = ""; refs.subDetailContainer.innerHTML = ""; refs.subDevicesContainer.innerHTML = "";
    state.subscriptions = []; _render();
  });

  /* Pre-fill user_id in create form from context */
  refs.subUserContext.addEventListener("click", (ev) => {
    if (ev.target.closest(".sub-clear-context")) {
      state.subscriptionContext = null; renderSubUserContext();
      refs.subFilterUser.value = "";
    }
  });

  /* Subscription table click delegation */
  refs.subsBody.addEventListener("click", async (ev) => {
    const openBtn = ev.target.closest(".sub-open-btn");
    if (openBtn) {
      const subId = openBtn.dataset.subId;
      try {
        const sub = await runAction("Load subscription", () => req(`/api/v1/subscriptions/${encodeURIComponent(subId)}`));
        renderSubscriptionDetail(sub);
        refs.subDevicesContainer.innerHTML = "";
      } catch (_) {}
      return;
    }
    const devicesBtn = ev.target.closest(".sub-devices-btn");
    if (devicesBtn) {
      const subId = devicesBtn.dataset.subId;
      try {
        const devices = await runAction("List devices", () => req(`/api/v1/subscriptions/${encodeURIComponent(subId)}/devices?active_only=false`));
        state.subscriptionDevices = Array.isArray(devices) ? devices : [];
        renderSubscriptionDevices(state.subscriptionDevices, subId);
      } catch (_) {}
      return;
    }
  });

  /* Subscription detail panel delegation */
  refs.subDetailContainer.addEventListener("click", async (ev) => {
    const el = ev.target;
    if (el.closest(".sub-detail-close")) { refs.subDetailContainer.innerHTML = ""; refs.subDevicesContainer.innerHTML = ""; state.selectedSubscription = null; return; }
    const rotateBtn = el.closest(".sub-detail-rotate");
    if (rotateBtn) {
      const subId = rotateBtn.dataset.subId;
      try {
        const out = await runAction("Rotate token", () => req(`/api/v1/subscriptions/${encodeURIComponent(subId)}/rotate-token`, { method: "POST", body: {} }));
        const urlEl = $("sub-detail-url");
        if (urlEl && out) {
          let urlHtml = "";
          if (out.token) urlHtml += `<div class="url-display"><span style="flex:1">${esc(out.token)}</span><button class="btn-mini copy-value" data-copy="${esc(out.token)}">Copy</button></div>`;
          if (out.subscription_url) urlHtml += `<div class="url-display" style="margin-top:6px"><span style="flex:1">${esc(out.subscription_url)}</span><button class="btn-mini copy-value" data-copy="${esc(out.subscription_url)}">Copy</button></div>`;
          urlEl.innerHTML = urlHtml;
        }
      } catch (_) {}
      return;
    }
    const activateBtn = el.closest(".sub-detail-activate");
    if (activateBtn) {
      const subId = activateBtn.dataset.subId;
      try {
        await runAction("Activate", () => req(`/api/v1/subscriptions/${encodeURIComponent(subId)}/activate`, { method: "POST", body: {} }));
        const sub = await req(`/api/v1/subscriptions/${encodeURIComponent(subId)}`);
        renderSubscriptionDetail(sub);
        const idx = state.subscriptions.findIndex((s) => s.id === sub.id);
        if (idx >= 0) state.subscriptions[idx] = sub; else state.subscriptions.unshift(sub);
        _render();
      } catch (_) {}
      return;
    }
    const deactivateBtn = el.closest(".sub-detail-deactivate");
    if (deactivateBtn) {
      const subId = deactivateBtn.dataset.subId;
      const ok = await confirmAction("Деактивация подписки", `Деактивировать подписку ${shortId(subId)}...?`);
      if (!ok) return;
      try {
        await runAction("Deactivate", () => req(`/api/v1/subscriptions/${encodeURIComponent(subId)}/deactivate`, { method: "POST", body: {} }));
        const sub = await req(`/api/v1/subscriptions/${encodeURIComponent(subId)}`);
        renderSubscriptionDetail(sub);
        const idx = state.subscriptions.findIndex((s) => s.id === sub.id);
        if (idx >= 0) state.subscriptions[idx] = sub; else state.subscriptions.unshift(sub);
        _render();
      } catch (_) {}
      return;
    }
    const devBtn = el.closest(".sub-detail-devices");
    if (devBtn) {
      const subId = devBtn.dataset.subId;
      try {
        const devices = await runAction("List devices", () => req(`/api/v1/subscriptions/${encodeURIComponent(subId)}/devices?active_only=false`));
        state.subscriptionDevices = Array.isArray(devices) ? devices : [];
        renderSubscriptionDevices(state.subscriptionDevices, subId);
      } catch (_) {}
      return;
    }
    const editBtn = el.closest(".sub-detail-edit");
    if (editBtn) {
      const form = $("sub-detail-edit-form");
      if (form) form.style.display = form.style.display === "none" ? "block" : "none";
      return;
    }
    const cancelBtn = el.closest(".sub-edit-cancel");
    if (cancelBtn) {
      const form = $("sub-detail-edit-form");
      if (form) form.style.display = "none";
      return;
    }
    const saveBtn = el.closest(".sub-edit-save");
    if (saveBtn) {
      const subId = saveBtn.dataset.subId;
      const maxDev = $("sub-edit-max-devices").value.trim();
      if (!maxDev) return;
      const payload = { max_devices: Number(maxDev) };
      try {
        const sub = await runAction("Set max devices", () => req(`/api/v1/subscriptions/${encodeURIComponent(subId)}/max-devices`, { method: "PATCH", body: payload }));
        renderSubscriptionDetail(sub);
        const idx = state.subscriptions.findIndex((s) => s.id === sub.id);
        if (idx >= 0) state.subscriptions[idx] = sub; else state.subscriptions.unshift(sub);
        _render();
      } catch (_) {}
      return;
    }
    const copyBtn = el.closest(".copy-value");
    if (copyBtn && copyBtn.dataset.copy) { copyToClipboard(copyBtn.dataset.copy); return; }
  });

  /* Device revoke delegation */
  refs.subDevicesContainer.addEventListener("click", async (ev) => {
    const revokeBtn = ev.target.closest(".device-revoke-btn");
    if (!revokeBtn) return;
    const subId = revokeBtn.dataset.subId; const deviceId = revokeBtn.dataset.deviceId;
    const ok = await confirmAction("Отключить устройство", `Отозвать устройство ${shortId(deviceId)}...?`);
    if (!ok) return;
    try {
      await runAction("Revoke device", () => req(`/api/v1/subscriptions/${encodeURIComponent(subId)}/devices/${encodeURIComponent(deviceId)}/revoke`, { method: "POST", body: {} }));
      const devices = await req(`/api/v1/subscriptions/${encodeURIComponent(subId)}/devices?active_only=false`);
      state.subscriptionDevices = Array.isArray(devices) ? devices : [];
      renderSubscriptionDevices(state.subscriptionDevices, subId);
    } catch (_) {}
  });

  /* Copy delegation in create result */
  refs.subCreateResult.addEventListener("click", (ev) => {
    const cbtn = ev.target.closest(".copy-value");
    if (cbtn && cbtn.dataset.copy) copyToClipboard(cbtn.dataset.copy);
  });
}
