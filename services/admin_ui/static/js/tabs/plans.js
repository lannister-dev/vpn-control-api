import { state, refs, $ } from '../state.js';
import { esc, chip, fmtTrafficLimit, uuidCell, resetLabels, resetColors } from '../utils.js';
import { req, runAction } from '../api.js';
import { notify, confirmAction, showSkeleton, hideSkeleton } from '../ui.js';

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
        <td><span class="muted" style="font-size:11px;max-width:200px;display:inline-block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(p.description || "-")}</span></td>
        <td>${priceDisplay}</td>
        <td>${trafficDisplay}</td>
        <td>${chip(resetCls, resetLabels[p.reset_strategy] || p.reset_strategy)}</td>
        <td><span class="stat-inline"><strong>${esc(p.max_devices)}</strong> dev</span></td>
        <td><span class="mono">${esc(p.included_devices || 1)}</span></td>
        <td>${p.device_price_rub > 0 ? `<span class="mono">${Number(p.device_price_rub).toFixed(2)} \u20BD</span>` : `<span class="muted">\u2014</span>`}</td>
        <td><span class="mono">${esc(p.duration_days)}</span> \u0434\u043D.</td>
        <td>${p.whitelist_enabled ? chip("info", "WL") : ""} ${p.is_active ? chip("ok", "active") : chip("bad", "inactive")}</td>
        <td><div class="actions"><button class="btn-mini plan-edit-btn" data-plan-id="${esc(p.id)}">Edit</button></div></td>
      </tr>`;
    }).join("")
    : `<tr><td colspan="11"><div class="empty-state"><div class="empty-state-icon">$</div><div class="empty-state-title">\u041D\u0435\u0442 \u0442\u0430\u0440\u0438\u0444\u043D\u044B\u0445 \u043F\u043B\u0430\u043D\u043E\u0432</div><div class="empty-state-desc">\u0421\u043E\u0437\u0434\u0430\u0439\u0442\u0435 \u043F\u0435\u0440\u0432\u044B\u0439 \u0442\u0430\u0440\u0438\u0444\u043D\u044B\u0439 \u043F\u043B\u0430\u043D</div></div></td></tr>`;
}

export function openPlanEditModal(planId) {
  const plan = state.plans.find((p) => p.id === planId); if (!plan) return;
  const tBytes = plan.traffic_limit_bytes || 0;
  const isGb = tBytes >= 1024 * 1024 * 1024;
  const tVal = isGb ? (tBytes / (1024 * 1024 * 1024)).toFixed(1) : (tBytes / (1024 * 1024)).toFixed(0);
  refs.confirmModal.innerHTML = `
    <div class="modal-overlay"><div class="modal-box wide">
      <div class="modal-title">\u0420\u0435\u0434\u0430\u043A\u0442\u0438\u0440\u043E\u0432\u0430\u0442\u044C: ${esc(plan.name)}</div>
      <div class="modal-body">
        <div class="form-section"><div class="form-section-title">\u041E\u0441\u043D\u043E\u0432\u043D\u043E\u0435</div>
          <div class="form-group"><label class="form-label">\u041D\u0430\u0437\u0432\u0430\u043D\u0438\u0435</label><input class="input" id="plan-e-name" value="${esc(plan.name)}" /></div>
          <div class="form-group"><label class="form-label">\u041E\u043F\u0438\u0441\u0430\u043D\u0438\u0435</label><input class="input" id="plan-e-desc" value="${esc(plan.description || "")}" /></div>
        </div>
        <div class="form-section"><div class="form-section-title">\u0422\u0440\u0430\u0444\u0438\u043A</div>
          <div class="form-group"><label class="form-label">\u041B\u0438\u043C\u0438\u0442 \u0442\u0440\u0430\u0444\u0438\u043A\u0430 (0 = \u0431\u0435\u0437\u043B\u0438\u043C\u0438\u0442)</label>
            <div style="display:flex;gap:8px;align-items:center">
              <input class="input mono" id="plan-e-traffic" type="number" min="0" step="0.1" value="${tVal}" style="flex:1" />
              <select class="select" id="plan-e-traffic-unit" style="width:80px"><option value="gb" ${isGb ? "selected" : ""}>GB</option><option value="mb" ${!isGb ? "selected" : ""}>MB</option></select>
            </div>
          </div>
          <div class="form-group"><label class="form-label">\u0421\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u044F \u0441\u0431\u0440\u043E\u0441\u0430</label>
            <select class="select" id="plan-e-reset">
              <option value="NO_RESET" ${plan.reset_strategy === "NO_RESET" ? "selected" : ""}>\u0411\u0435\u0437 \u0441\u0431\u0440\u043E\u0441\u0430</option>
              <option value="DAY" ${plan.reset_strategy === "DAY" ? "selected" : ""}>\u0415\u0436\u0435\u0434\u043D\u0435\u0432\u043D\u043E</option>
              <option value="WEEK" ${plan.reset_strategy === "WEEK" ? "selected" : ""}>\u0415\u0436\u0435\u043D\u0435\u0434\u0435\u043B\u044C\u043D\u043E</option>
              <option value="MONTH" ${plan.reset_strategy === "MONTH" ? "selected" : ""}>\u0415\u0436\u0435\u043C\u0435\u0441\u044F\u0447\u043D\u043E</option>
            </select>
          </div>
        </div>
        <div class="form-section"><div class="form-section-title">\u041E\u0433\u0440\u0430\u043D\u0438\u0447\u0435\u043D\u0438\u044F</div>
          <div class="row-2">
            <div class="form-group"><label class="form-label">\u041C\u0430\u043A\u0441. \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432</label><input class="input mono" id="plan-e-devices" type="number" min="1" max="100" value="${plan.max_devices}" /></div>
            <div class="form-group"><label class="form-label">\u0414\u043B\u0438\u0442\u0435\u043B\u044C\u043D\u043E\u0441\u0442\u044C (\u0434\u043D\u0438)</label><input class="input mono" id="plan-e-duration" type="number" min="1" max="3650" value="${plan.duration_days}" /></div>
          </div>
          <div class="form-group"><label class="muted" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="plan-e-active" ${plan.is_active ? "checked" : ""} /> \u0410\u043A\u0442\u0438\u0432\u0435\u043D</label></div>
        </div>
        <div class="form-section"><div class="form-section-title">\u0423\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430</div>
          <div class="row-2">
            <div class="form-group"><label class="form-label">\u0412\u043A\u043B\u044E\u0447\u0435\u043D\u043E \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432</label><input class="input mono" id="plan-e-included-devices" type="number" min="1" max="100" value="${plan.included_devices || 1}" /></div>
            <div class="form-group"><label class="form-label">\u0426\u0435\u043D\u0430 \u0434\u043E\u043F. \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430 (\u0440\u0443\u0431.)</label><input class="input mono" id="plan-e-device-price" type="number" min="0" step="0.01" value="${plan.device_price_rub || 0}" /></div>
          </div>
          <div class="form-group"><label class="form-label">\u0426\u0435\u043D\u0430 \u0434\u043E\u043F. \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430 (Stars)</label><input class="input mono" id="plan-e-device-price-stars" type="number" min="1" value="${plan.device_price_stars || ""}" placeholder="\u041E\u043F\u0446\u0438\u043E\u043D\u0430\u043B\u044C\u043D\u043E" /></div>
        </div>
        <div class="form-section"><div class="form-section-title">\u0426\u0435\u043D\u0430</div>
          <div class="form-group"><label class="form-label">\u0426\u0435\u043D\u0430 (\u0440\u0443\u0431.)</label><input class="input mono" id="plan-e-price" type="number" min="0" step="0.01" value="${plan.price_rub || 0}" /></div>
        </div>
        <div class="form-section"><div class="form-section-title">Whitelist</div>
          <div class="form-group"><label class="form-label" style="display:flex;align-items:center;gap:8px"><input type="checkbox" id="plan-e-wl" ${plan.whitelist_enabled ? "checked" : ""} /> Whitelist-\u043C\u0430\u0440\u0448\u0440\u0443\u0442\u044B (entry \u043D\u043E\u0434\u044B)</label></div>
        </div>
        <div class="danger-zone"><div class="danger-zone-title">\u041E\u043F\u0430\u0441\u043D\u0430\u044F \u0437\u043E\u043D\u0430</div>
          <button class="btn btn-danger" data-confirm="deactivate" style="width:auto;padding:8px 16px">\u0414\u0435\u0430\u043A\u0442\u0438\u0432\u0438\u0440\u043E\u0432\u0430\u0442\u044C \u043F\u043B\u0430\u043D</button>
        </div>
      </div>
      <div class="modal-actions">
        <button class="btn btn-ghost" data-confirm="cancel">\u041E\u0442\u043C\u0435\u043D\u0430</button>
        <button class="btn btn-primary" data-confirm="ok">\u0421\u043E\u0445\u0440\u0430\u043D\u0438\u0442\u044C</button>
      </div>
    </div></div>`;
  const cleanup = () => { refs.confirmModal.innerHTML = ""; };
  refs.confirmModal.querySelector('[data-confirm="cancel"]').addEventListener("click", cleanup);
  refs.confirmModal.querySelector(".modal-overlay").addEventListener("click", (ev) => { if (ev.target === ev.currentTarget) cleanup(); });
  refs.confirmModal.querySelector('[data-confirm="ok"]').addEventListener("click", () => {
    const trafficVal = parseFloat(document.getElementById("plan-e-traffic").value) || 0;
    const unit = document.getElementById("plan-e-traffic-unit").value;
    const traffic_limit_bytes = unit === "gb" ? Math.round(trafficVal * 1024 * 1024 * 1024) : Math.round(trafficVal * 1024 * 1024);
    const payload = { name: document.getElementById("plan-e-name").value.trim() || null, description: document.getElementById("plan-e-desc").value.trim() || null, traffic_limit_bytes, reset_strategy: document.getElementById("plan-e-reset").value, max_devices: parseInt(document.getElementById("plan-e-devices").value) || 5, duration_days: parseInt(document.getElementById("plan-e-duration").value) || 30, included_devices: parseInt(document.getElementById("plan-e-included-devices").value) || 1, device_price_rub: parseFloat(document.getElementById("plan-e-device-price").value) || 0, is_active: document.getElementById("plan-e-active").checked, whitelist_enabled: document.getElementById("plan-e-wl").checked, price_rub: parseFloat(document.getElementById("plan-e-price").value) || 0 };
    const edps = document.getElementById("plan-e-device-price-stars").value.trim(); if (edps) payload.device_price_stars = parseInt(edps);
    cleanup();
    runAction("Update plan", () => req(`/api/v1/plans/${encodeURIComponent(planId)}`, { method: "PATCH", body: payload })).then(() => loadPlans()).catch(() => {});
  });
  refs.confirmModal.querySelector('[data-confirm="deactivate"]').addEventListener("click", async () => {
    cleanup();
    const ok = await confirmAction("\u0414\u0435\u0430\u043A\u0442\u0438\u0432\u0430\u0446\u0438\u044F \u043F\u043B\u0430\u043D\u0430", `\u0414\u0435\u0430\u043A\u0442\u0438\u0432\u0438\u0440\u043E\u0432\u0430\u0442\u044C \u043F\u043B\u0430\u043D "${plan.name}"?`); if (!ok) return;
    runAction("Deactivate plan", () => req(`/api/v1/plans/${encodeURIComponent(planId)}`, { method: "DELETE" })).then(() => loadPlans()).catch(() => {});
  });
}

export function bindPlanEvents() {
  refs.plansReload.addEventListener("click", () => loadPlans().catch((e) => notify("\u041E\u0448\u0438\u0431\u043A\u0430: " + e.message, true)));

  /* Plans create modal (with section grouping) */
  refs.plansCreateBtn.addEventListener("click", () => {
    refs.confirmModal.innerHTML = `
      <div class="modal-overlay"><div class="modal-box wide">
        <div class="modal-title">\u0421\u043E\u0437\u0434\u0430\u0442\u044C \u0442\u0430\u0440\u0438\u0444\u043D\u044B\u0439 \u043F\u043B\u0430\u043D</div>
        <div class="modal-body">
          <div class="form-section"><div class="form-section-title">\u041E\u0441\u043D\u043E\u0432\u043D\u043E\u0435</div>
            <div class="form-group"><label class="form-label">\u041D\u0430\u0437\u0432\u0430\u043D\u0438\u0435 (\u043E\u0431\u044F\u0437\u0430\u0442\u0435\u043B\u044C\u043D\u043E)</label><input class="input" id="plan-name" required /></div>
            <div class="form-group"><label class="form-label">\u041E\u043F\u0438\u0441\u0430\u043D\u0438\u0435</label><input class="input" id="plan-desc" placeholder="\u041E\u043F\u0446\u0438\u043E\u043D\u0430\u043B\u044C\u043D\u043E" /></div>
          </div>
          <div class="form-section"><div class="form-section-title">\u0422\u0440\u0430\u0444\u0438\u043A</div>
            <div class="form-group"><label class="form-label">\u041B\u0438\u043C\u0438\u0442 \u0442\u0440\u0430\u0444\u0438\u043A\u0430 (0 = \u0431\u0435\u0437\u043B\u0438\u043C\u0438\u0442)</label>
              <div style="display:flex;gap:8px;align-items:center">
                <input class="input mono" id="plan-traffic" type="number" min="0" step="0.1" value="0" style="flex:1" />
                <select class="select" id="plan-traffic-unit" style="width:80px"><option value="gb">GB</option><option value="mb">MB</option></select>
              </div>
            </div>
            <div class="form-group"><label class="form-label">\u0421\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u044F \u0441\u0431\u0440\u043E\u0441\u0430</label>
              <select class="select" id="plan-reset"><option value="NO_RESET">\u0411\u0435\u0437 \u0441\u0431\u0440\u043E\u0441\u0430</option><option value="DAY">\u0415\u0436\u0435\u0434\u043D\u0435\u0432\u043D\u043E</option><option value="WEEK">\u0415\u0436\u0435\u043D\u0435\u0434\u0435\u043B\u044C\u043D\u043E</option><option value="MONTH" selected>\u0415\u0436\u0435\u043C\u0435\u0441\u044F\u0447\u043D\u043E</option></select>
            </div>
          </div>
          <div class="form-section"><div class="form-section-title">\u041E\u0433\u0440\u0430\u043D\u0438\u0447\u0435\u043D\u0438\u044F</div>
            <div class="row-2">
              <div class="form-group"><label class="form-label">\u041C\u0430\u043A\u0441. \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432</label><input class="input mono" id="plan-devices" type="number" min="1" max="100" value="5" /></div>
              <div class="form-group"><label class="form-label">\u0414\u043B\u0438\u0442\u0435\u043B\u044C\u043D\u043E\u0441\u0442\u044C (\u0434\u043D\u0438)</label><input class="input mono" id="plan-duration" type="number" min="1" max="3650" value="30" /></div>
            </div>
          </div>
          <div class="form-section"><div class="form-section-title">\u0423\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430</div>
            <div class="row-2">
              <div class="form-group"><label class="form-label">\u0412\u043A\u043B\u044E\u0447\u0435\u043D\u043E \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432</label><input class="input mono" id="plan-included-devices" type="number" min="1" max="100" value="1" /></div>
              <div class="form-group"><label class="form-label">\u0426\u0435\u043D\u0430 \u0434\u043E\u043F. \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430 (\u0440\u0443\u0431.)</label><input class="input mono" id="plan-device-price" type="number" min="0" step="0.01" value="0" /></div>
            </div>
            <div class="form-group"><label class="form-label">\u0426\u0435\u043D\u0430 \u0434\u043E\u043F. \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430 (Stars)</label><input class="input mono" id="plan-device-price-stars" type="number" min="1" placeholder="\u041E\u043F\u0446\u0438\u043E\u043D\u0430\u043B\u044C\u043D\u043E" /></div>
          </div>
          <div class="form-section"><div class="form-section-title">\u0426\u0435\u043D\u0430</div>
            <div class="form-group"><label class="form-label">\u0426\u0435\u043D\u0430 (\u0440\u0443\u0431.)</label><input class="input mono" id="plan-price" type="number" min="0" step="0.01" value="0" /></div>
          </div>
          <div class="form-section"><div class="form-section-title">Whitelist</div>
            <div class="form-group"><label class="form-label" style="display:flex;align-items:center;gap:8px"><input type="checkbox" id="plan-wl" /> Whitelist-\u043C\u0430\u0440\u0448\u0440\u0443\u0442\u044B (entry \u043D\u043E\u0434\u044B)</label></div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" data-confirm="cancel">\u041E\u0442\u043C\u0435\u043D\u0430</button>
          <button class="btn btn-primary" data-confirm="ok">\u0421\u043E\u0437\u0434\u0430\u0442\u044C</button>
        </div>
      </div></div>`;
    const cleanup = () => { refs.confirmModal.innerHTML = ""; };
    refs.confirmModal.querySelector('[data-confirm="cancel"]').addEventListener("click", cleanup);
    refs.confirmModal.querySelector(".modal-overlay").addEventListener("click", (ev) => { if (ev.target === ev.currentTarget) cleanup(); });
    refs.confirmModal.querySelector('[data-confirm="ok"]').addEventListener("click", () => {
      const name = document.getElementById("plan-name").value.trim();
      if (!name) { notify("\u041D\u0430\u0437\u0432\u0430\u043D\u0438\u0435 \u043E\u0431\u044F\u0437\u0430\u0442\u0435\u043B\u044C\u043D\u043E", true); return; }
      const trafficVal = parseFloat(document.getElementById("plan-traffic").value) || 0;
      const unit = document.getElementById("plan-traffic-unit").value;
      const traffic_limit_bytes = unit === "gb" ? Math.round(trafficVal * 1024 * 1024 * 1024) : Math.round(trafficVal * 1024 * 1024);
      const payload = { name, description: document.getElementById("plan-desc").value.trim() || null, traffic_limit_bytes, reset_strategy: document.getElementById("plan-reset").value, max_devices: parseInt(document.getElementById("plan-devices").value) || 5, duration_days: parseInt(document.getElementById("plan-duration").value) || 30, included_devices: parseInt(document.getElementById("plan-included-devices").value) || 1, device_price_rub: parseFloat(document.getElementById("plan-device-price").value) || 0, whitelist_enabled: document.getElementById("plan-wl").checked, price_rub: parseFloat(document.getElementById("plan-price").value) || 0 };
      const dps = document.getElementById("plan-device-price-stars").value.trim(); if (dps) payload.device_price_stars = parseInt(dps);
      cleanup();
      runAction("Create plan", () => req("/api/v1/plans", { method: "POST", body: payload })).then(() => loadPlans()).catch(() => {});
    });
  });

  refs.plansBody.addEventListener("click", (ev) => { const btn = ev.target.closest(".plan-edit-btn"); if (btn) openPlanEditModal(btn.dataset.planId); });
}
