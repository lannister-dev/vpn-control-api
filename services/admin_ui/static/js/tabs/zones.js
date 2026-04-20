import { state, refs } from '../state.js';
import { esc, chip } from '../utils.js';
import { req, runAction } from '../api.js';
import { notify, confirmAction, openModal } from '../ui.js';

export async function loadZones() {
  const data = await req("/api/v1/zones");
  state.zones = data.items || [];
  renderZones();
}

export function renderZones() {
  if (!refs.zonesBody) return;
  const rows = state.zones.slice().sort((a, b) => {
    if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
    return a.code.localeCompare(b.code);
  });
  refs.zonesBody.innerHTML = rows.length
    ? rows.map((z) => `<tr>
        <td><span class="mono" style="font-weight:600">${esc(z.code)}</span></td>
        <td style="font-size:20px">${esc(z.emoji || "—")}</td>
        <td>${esc(z.name)}</td>
        <td class="mono">${esc(z.sort_order)}</td>
        <td>${z.is_active ? chip("ok", "active") : chip("warn", "inactive")}</td>
        <td><div class="actions">
          <button class="btn-mini zone-edit-btn" data-zone-code="${esc(z.code)}">Edit</button>
        </div></td>
      </tr>`).join("")
    : `<tr><td colspan="6"><div class="empty-state"><div class="empty-state-icon">🌍</div><div class="empty-state-title">Зон нет</div><div class="empty-state-hint">Создайте зону, чтобы привязывать к ней entry-ноды для отображения в Happ.</div><div class="empty-state-action"><button class="btn btn-primary zones-empty-create btn-auto">+ Создать зону</button></div></div></td></tr>`;
  if (refs.zonesMeta) refs.zonesMeta.textContent = `Всего: ${rows.length}`;
}

function _zoneFormBody(zone) {
  const z = zone || {};
  const locked = !!zone;
  return `
    <div class="form-section"><div class="form-section-title">Идентификатор</div>
      <div class="form-group"><label class="form-label">Код${locked ? " (неизменяем)" : ""}</label>
        <input class="input mono" id="zf-code" value="${esc(z.code || "")}" ${locked ? "disabled" : "required minlength=\"2\" maxlength=\"16\" pattern=\"[a-z][a-z0-9_]*\""} />
      </div>
    </div>
    <div class="form-section"><div class="form-section-title">Отображение</div>
      <div class="form-group"><label class="form-label">Эмодзи</label>
        <input class="input" id="zf-emoji" value="${esc(z.emoji || "")}" maxlength="16" placeholder="🌍" />
      </div>
      <div class="form-group"><label class="form-label">Название${locked ? "" : " (обязательно)"}</label>
        <input class="input" id="zf-name" value="${esc(z.name || "")}" ${locked ? "" : "required"} maxlength="64" />
      </div>
      <div class="form-group"><label class="form-label">Порядок сортировки</label>
        <input class="input mono" id="zf-sort" type="number" min="0" step="10" value="${esc(z.sort_order != null ? z.sort_order : 0)}" />
      </div>
      ${locked ? `<div class="form-group"><label class="checkbox-inline muted"><input type="checkbox" id="zf-active" ${z.is_active ? "checked" : ""} /> Активна</label></div>` : ""}
    </div>`;
}

function _readZoneForm(root, { includeCode }) {
  const payload = {
    emoji: root.querySelector("#zf-emoji").value.trim(),
    name: root.querySelector("#zf-name").value.trim(),
    sort_order: parseInt(root.querySelector("#zf-sort").value) || 0,
  };
  if (includeCode) {
    payload.code = root.querySelector("#zf-code").value.trim().toLowerCase();
  }
  const active = root.querySelector("#zf-active");
  if (active) payload.is_active = active.checked;
  return payload;
}

function openZoneCreateModal() {
  const footerHtml = `<button class="btn btn-ghost" data-act="cancel">Отмена</button><button class="btn btn-primary" data-act="save">Создать</button>`;
  openModal({
    title: "Создать зону",
    bodyHtml: _zoneFormBody(null),
    footerHtml,
    onMount: ({ root, close }) => {
      root.querySelector('[data-act="cancel"]').addEventListener("click", close);
      root.querySelector('[data-act="save"]').addEventListener("click", () => {
        const payload = _readZoneForm(root, { includeCode: true });
        if (!payload.code) { notify("Код обязателен", true); return; }
        if (!payload.name) { notify("Название обязательно", true); return; }
        close();
        runAction("Create zone", () => req("/api/v1/zones", { method: "POST", body: payload }))
          .then(() => loadZones()).catch(() => {});
      });
    },
  });
}

function openZoneEditModal(code) {
  const zone = state.zones.find((z) => z.code === code); if (!zone) return;
  const bodyHtml = _zoneFormBody(zone) + `
    <div class="danger-zone"><div class="danger-zone-title">Опасная зона</div>
      <button class="btn btn-danger btn-auto" data-act="deactivate">Деактивировать</button>
    </div>`;
  const footerHtml = `<button class="btn btn-ghost" data-act="cancel">Отмена</button><button class="btn btn-primary" data-act="save">Сохранить</button>`;
  openModal({
    title: `Редактировать: ${zone.code}`,
    bodyHtml,
    footerHtml,
    onMount: ({ root, close }) => {
      root.querySelector('[data-act="cancel"]').addEventListener("click", close);
      root.querySelector('[data-act="save"]').addEventListener("click", () => {
        const payload = _readZoneForm(root, { includeCode: false });
        close();
        runAction("Update zone", () => req(`/api/v1/zones/${encodeURIComponent(code)}`, { method: "PATCH", body: payload }))
          .then(() => loadZones()).catch(() => {});
      });
      root.querySelector('[data-act="deactivate"]').addEventListener("click", async () => {
        close();
        const ok = await confirmAction("Деактивация зоны", `Деактивировать зону "${zone.name}"?`); if (!ok) return;
        runAction("Deactivate zone", () => req(`/api/v1/zones/${encodeURIComponent(code)}`, { method: "DELETE" }))
          .then(() => loadZones()).catch(() => {});
      });
    },
  });
}

export function bindZoneEvents() {
  if (refs.zonesReload) {
    refs.zonesReload.addEventListener("click", () => loadZones().catch((e) => notify("Ошибка: " + e.message, true)));
  }
  if (refs.zonesCreateBtn) {
    refs.zonesCreateBtn.addEventListener("click", () => openZoneCreateModal());
  }
  if (refs.zonesBody) {
    refs.zonesBody.addEventListener("click", (ev) => {
      const empty = ev.target.closest(".zones-empty-create");
      if (empty) { openZoneCreateModal(); return; }
      const btn = ev.target.closest(".zone-edit-btn");
      if (btn) openZoneEditModal(btn.dataset.zoneCode);
    });
  }
}
