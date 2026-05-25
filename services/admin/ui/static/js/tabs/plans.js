import { state, refs, $ } from '../state.js';
import { esc, chip, fmtTrafficLimit, uuidCell, resetLabels, resetColors } from '../utils.js';
import { req, runAction } from '../api.js';
import { notify, confirmAction, showSkeleton, hideSkeleton, openModal } from '../ui.js';

export async function loadPlans() {
  const planBodyEl = $("plans-body");
  if (planBodyEl) showSkeleton("plans-body", 4);
  try {
    const data = await req("/api/v1/plans");
    state.plans = data.items || [];
    renderPlans(); renderPlanSelect();
  } catch (e) {
    if (planBodyEl) hideSkeleton("plans-body");
    throw e;
  }
}

export function renderPlanSelect() {
  const sel = $("sub-plan-select"); if (!sel) return;
  const cur = sel.value;
  sel.innerHTML = `<option value="">-- Без тарифа --</option>` +
    state.plans.filter((p) => p.is_active).map((p) => `<option value="${esc(p.id)}">${esc(p.name)} (${fmtTrafficLimit(p.traffic_limit_bytes)})</option>`).join("");
  if (cur) sel.value = cur;
}

export function renderPlans() {
  refs.plansHead.innerHTML = `<tr><th>Название</th><th>Описание</th><th>Цена</th><th>Трафик</th><th>Сброс</th><th>Макс. устройств</th><th>Вкл. устр.</th><th>Цена доп. устр.</th><th>Длительность</th><th>Статус</th><th>Действия</th></tr>`;
  refs.plansBody.innerHTML = state.plans.length
    ? state.plans.map((p) => {
      const trafficDisplay = p.traffic_limit_bytes && p.traffic_limit_bytes > 0
        ? `<span class="mono" style="font-weight:600">${fmtTrafficLimit(p.traffic_limit_bytes)}</span>`
        : chip("ok", "Unlimited");
      const resetCls = resetColors[p.reset_strategy] || "muted";
      const priceDisplay = p.price_rub > 0 ? `<span class="mono" style="font-weight:600">${Number(p.price_rub).toFixed(2)} \u20BD</span>` : `<span class="muted">\u2014</span>`;
      return `<tr>
        <td><strong>${esc(p.name)}</strong></td>
        <td><span class="muted plan-desc-cell">${esc(p.description || "-")}</span></td>
        <td>${priceDisplay}</td>
        <td>${trafficDisplay}</td>
        <td>${chip(resetCls, resetLabels[p.reset_strategy] || p.reset_strategy)}</td>
        <td><span class="stat-inline"><strong>${esc(p.max_devices)}</strong> dev</span></td>
        <td><span class="mono">${esc(p.included_devices || 1)}</span></td>
        <td>${p.device_price_rub > 0 ? `<span class="mono">${Number(p.device_price_rub).toFixed(2)} \u20BD</span>` : `<span class="muted">\u2014</span>`}</td>
        <td><span class="mono">${esc(p.duration_days)}</span> \u0434\u043D.</td>
        <td>${p.whitelist_enabled ? chip("info", "WL") : ""} ${p.entry_relay_enabled ? chip("info", "Entry") : ""} ${p.is_active ? chip("ok", "active") : chip("bad", "inactive")}</td>
        <td><div class="actions"><button class="btn-mini plan-edit-btn" data-plan-id="${esc(p.id)}">Edit</button></div></td>
      </tr>`;
    }).join("")
    : `<tr><td colspan="11"><div class="empty-state"><div class="empty-state-icon">\uD83D\uDCB0</div><div class="empty-state-title">Тарифных планов пока нет</div><div class="empty-state-hint">Создайте первый тарифный план, чтобы выдавать подписки пользователям.</div><div class="empty-state-action"><button class="btn btn-primary plans-empty-create btn-auto">+ Создать тариф</button></div></div></td></tr>`;
}

/* ── Shared form body builder ──────────────────────── */
function _planFormBody(plan) {
  const p = plan || {};
  const tBytes = p.traffic_limit_bytes || 0;
  const isGb = tBytes >= 1024 * 1024 * 1024;
  const tVal = plan
    ? (isGb ? (tBytes / (1024 * 1024 * 1024)).toFixed(1) : (tBytes / (1024 * 1024)).toFixed(0))
    : "0";
  const reset = p.reset_strategy || "MONTH";
  const active = plan ? p.is_active : true;
  return `
    <div class="form-section"><div class="form-section-title">Основное</div>
      <div class="form-group"><label class="form-label">Название${plan ? "" : " (обязательно)"}</label><input class="input" id="pf-name" value="${esc(p.name || "")}" ${plan ? "" : "required"} /></div>
      <div class="form-group"><label class="form-label">Описание</label><input class="input" id="pf-desc" value="${esc(p.description || "")}" placeholder="${plan ? "" : "Опционально"}" /></div>
    </div>
    <div class="form-section"><div class="form-section-title">Трафик</div>
      <div class="form-group"><label class="form-label">Лимит трафика (0 = безлимит)</label>
        <div class="input-with-unit">
          <input class="input mono" id="pf-traffic" type="number" min="0" step="0.1" value="${tVal}" />
          <select class="select unit-select" id="pf-traffic-unit"><option value="gb" ${isGb ? "selected" : ""}>GB</option><option value="mb" ${!isGb ? "selected" : ""}>MB</option></select>
        </div>
      </div>
      <div class="form-group"><label class="form-label">Стратегия сброса</label>
        <select class="select" id="pf-reset">
          <option value="NO_RESET" ${reset === "NO_RESET" ? "selected" : ""}>Без сброса</option>
          <option value="DAY" ${reset === "DAY" ? "selected" : ""}>Ежедневно</option>
          <option value="WEEK" ${reset === "WEEK" ? "selected" : ""}>Еженедельно</option>
          <option value="MONTH" ${reset === "MONTH" ? "selected" : ""}>Ежемесячно</option>
        </select>
      </div>
    </div>
    <div class="form-section"><div class="form-section-title">Ограничения</div>
      <div class="row-2">
        <div class="form-group"><label class="form-label">Макс. устройств</label><input class="input mono" id="pf-devices" type="number" min="1" max="100" value="${esc(p.max_devices != null ? p.max_devices : 5)}" /></div>
        <div class="form-group"><label class="form-label">Длительность (дни)</label><input class="input mono" id="pf-duration" type="number" min="1" max="3650" value="${esc(p.duration_days != null ? p.duration_days : 30)}" /></div>
      </div>
      <div class="form-group"><label class="checkbox-inline muted"><input type="checkbox" id="pf-active" ${active ? "checked" : ""} /> Активен</label></div>
    </div>
    <div class="form-section"><div class="form-section-title">Устройства</div>
      <div class="row-2">
        <div class="form-group"><label class="form-label">Включено устройств</label><input class="input mono" id="pf-included-devices" type="number" min="1" max="100" value="${esc(p.included_devices || 1)}" /></div>
        <div class="form-group"><label class="form-label">Цена доп. устройства (руб.)</label><input class="input mono" id="pf-device-price" type="number" min="0" step="0.01" value="${esc(p.device_price_rub || 0)}" /></div>
      </div>
      <div class="form-group"><label class="form-label">Цена доп. устройства (Stars)</label><input class="input mono" id="pf-device-price-stars" type="number" min="1" value="${esc(p.device_price_stars || "")}" placeholder="Опционально" /></div>
    </div>
    <div class="form-section"><div class="form-section-title">Цена</div>
      <div class="form-group"><label class="form-label">Цена (руб.)</label><input class="input mono" id="pf-price" type="number" min="0" step="0.01" value="${esc(p.price_rub || 0)}" /></div>
    </div>
    <div class="form-section"><div class="form-section-title">Entry / Whitelist</div>
      <div class="form-group"><label class="checkbox-inline"><input type="checkbox" id="pf-er" ${p.entry_relay_enabled ? "checked" : ""} /> Умная маршрутизация (entry pool)</label></div>
      <div class="form-group"><label class="checkbox-inline"><input type="checkbox" id="pf-wl" ${p.whitelist_enabled ? "checked" : ""} /> Whitelist-маршруты (обход глушилок)</label></div>
    </div>`;
}

/* ── Read form values ──────────────────────────────── */
function _readPlanForm(root) {
  const trafficVal = parseFloat(root.querySelector("#pf-traffic").value) || 0;
  const unit = root.querySelector("#pf-traffic-unit").value;
  const traffic_limit_bytes = unit === "gb" ? Math.round(trafficVal * 1024 * 1024 * 1024) : Math.round(trafficVal * 1024 * 1024);
  const payload = {
    name: root.querySelector("#pf-name").value.trim() || null,
    description: root.querySelector("#pf-desc").value.trim() || null,
    traffic_limit_bytes,
    reset_strategy: root.querySelector("#pf-reset").value,
    max_devices: parseInt(root.querySelector("#pf-devices").value) || 5,
    duration_days: parseInt(root.querySelector("#pf-duration").value) || 30,
    included_devices: parseInt(root.querySelector("#pf-included-devices").value) || 1,
    device_price_rub: parseFloat(root.querySelector("#pf-device-price").value) || 0,
    is_active: root.querySelector("#pf-active").checked,
    whitelist_enabled: root.querySelector("#pf-wl").checked,
    entry_relay_enabled: root.querySelector("#pf-er").checked,
    price_rub: parseFloat(root.querySelector("#pf-price").value) || 0,
  };
  const dps = root.querySelector("#pf-device-price-stars").value.trim();
  if (dps) payload.device_price_stars = parseInt(dps);
  return payload;
}

/* ── openPlanEditModal ─────────────────────────────── */
export function openPlanEditModal(planId) {
  const plan = state.plans.find((p) => p.id === planId); if (!plan) return;
  const bodyHtml = _planFormBody(plan) + `
    <div class="danger-zone"><div class="danger-zone-title">Опасная зона</div>
      <button class="btn btn-danger btn-auto" data-act="deactivate">Деактивировать план</button>
    </div>`;
  const footerHtml = `<button class="btn btn-ghost" data-act="cancel">Отмена</button><button class="btn btn-primary" data-act="save">Сохранить</button>`;
  openModal({
    title: `Редактировать: ${plan.name}`,
    bodyHtml,
    footerHtml,
    wide: true,
    onMount: ({ root, close }) => {
      root.querySelector('[data-act="cancel"]').addEventListener("click", close);
      root.querySelector('[data-act="save"]').addEventListener("click", () => {
        const payload = _readPlanForm(root);
        close();
        runAction("Update plan", () => req(`/api/v1/plans/${encodeURIComponent(planId)}`, { method: "PATCH", body: payload })).then(() => loadPlans()).catch(() => {});
      });
      root.querySelector('[data-act="deactivate"]').addEventListener("click", async () => {
        close();
        const ok = await confirmAction("Деактивация плана", `Деактивировать план "${plan.name}"?`); if (!ok) return;
        runAction("Deactivate plan", () => req(`/api/v1/plans/${encodeURIComponent(planId)}`, { method: "DELETE" })).then(() => loadPlans()).catch(() => {});
      });
    },
  });
}

/* ── openPlanCreateModal ───────────────────────────── */
function openPlanCreateModal() {
  const footerHtml = `<button class="btn btn-ghost" data-act="cancel">Отмена</button><button class="btn btn-primary" data-act="save">Создать</button>`;
  openModal({
    title: "Создать тарифный план",
    bodyHtml: _planFormBody(null),
    footerHtml,
    wide: true,
    onMount: ({ root, close }) => {
      root.querySelector('[data-act="cancel"]').addEventListener("click", close);
      root.querySelector('[data-act="save"]').addEventListener("click", () => {
        const payload = _readPlanForm(root);
        if (!payload.name) { notify("Название обязательно", true); return; }
        close();
        runAction("Create plan", () => req("/api/v1/plans", { method: "POST", body: payload })).then(() => loadPlans()).catch(() => {});
      });
    },
  });
}

export function bindPlanEvents() {
  refs.plansReload.addEventListener("click", () => loadPlans().catch((e) => notify("\u041E\u0448\u0438\u0431\u043A\u0430: " + e.message, true)));
  refs.plansCreateBtn.addEventListener("click", () => openPlanCreateModal());
  refs.plansBody.addEventListener("click", (ev) => {
    const empty = ev.target.closest(".plans-empty-create");
    if (empty) { openPlanCreateModal(); return; }
    const btn = ev.target.closest(".plan-edit-btn");
    if (btn) openPlanEditModal(btn.dataset.planId);
  });
}
