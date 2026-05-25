import { state, refs } from '../state.js';
import {
  esc, fmtDate, chip, uuidCell, shortId, nodeGeo, nodeNameById,
  routeStatusLabel, routeReasonLabel, latestProbeForRoute,
  sortTh, sortedBy,
} from '../utils.js';
import { req, runAction } from '../api.js';
import { notify, confirmAction, openModal } from '../ui.js';

/* ── Late-binding callbacks (set by app.js) ────────── */
let _refreshAll = () => {};
let _render = () => {};
export function setCallbacks(refreshAll, render) { _refreshAll = refreshAll; _render = render; }

/* ── filteredRoutes ────────────────────────────────── */
export function filteredRoutes() {
  const status = refs.routesStatus.value;
  const q = refs.routesSearch.value.trim().toLowerCase();
  return state.routes.filter((r) => {
    if (status && r.health_status !== status) return false;
    if (q) {
      const nodeName = nodeNameById(r.node_id) || "";
      const entryNodeName = nodeNameById(r.entry_node_id) || "";
      const hay = [r.id, r.name, r.node_id, r.entry_node_id, r.transport_profile_id, nodeName, entryNodeName].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

/* ── _routeFormBody (private) ──────────────────────── */
function _routeFormBody({ name, nodeId, entryNodeId, tpId, baseWeight, healthStatus, isCreate }) {
  const nodes = ((state.status && state.status.nodes) || []);
  const backendNodes = nodes.filter((n) => String(n.role || "").toLowerCase() === "backend");
  const entryNodes = nodes.filter((n) => ["whitelist_entry", "entry"].includes(String(n.role || "").toLowerCase()));
  const tps = state.transportProfiles || [];
  const backendOpts = backendNodes.map((n) => { const g = nodeGeo(n.region); return `<option value="${esc(n.id)}"${n.id === nodeId ? " selected" : ""}>${esc(g.flag)} ${esc(n.name)} (${shortId(n.id)})</option>`; }).join("");
  const entryOpts = [`<option value=""${!entryNodeId ? " selected" : ""}>Без entry (прямое)</option>`].concat(entryNodes.map((n) => { const g = nodeGeo(n.region); return `<option value="${esc(n.id)}"${n.id === entryNodeId ? " selected" : ""}>${esc(g.flag)} ${esc(n.name)} (${shortId(n.id)})</option>`; })).join("");
  const tpOpts = tps.map((t) => `<option value="${esc(t.id)}"${t.id === tpId ? " selected" : ""}>${esc(t.name)} (${esc(t.network)}/${esc(t.security)})</option>`).join("");
  const statusOpts = ["healthy", "blocked", "warming_up"].map((s) => `<option value="${esc(s)}"${s === (healthStatus || "healthy") ? " selected" : ""}>${esc(s)}</option>`).join("");
  return `<div class="stack">
    <div class="form-group"><label class="form-label">Имя маршрута</label><input id="rf-name" class="input" value="${esc(name || "")}" maxlength="100" /></div>
    <div class="form-group"><label class="form-label">Backend нода</label><select id="rf-node" class="select">${backendOpts}</select></div>
    <div class="form-group"><label class="form-label">Entry нода</label><select id="rf-entry" class="select">${entryOpts}</select></div>
    ${isCreate ? `<div class="form-group"><label class="form-label">Transport profile</label><select id="rf-tp" class="select">${tpOpts}</select></div>` : ""}
    <div class="form-group"><label class="form-label">Base weight</label><input id="rf-weight" class="input mono" type="number" min="0" max="100" value="${baseWeight != null ? baseWeight : 50}" /></div>
    ${isCreate ? `<div class="form-group"><label class="form-label">Статус</label><select id="rf-status" class="select">${statusOpts}</select></div>` : ""}
  </div>`;
}

/* ── renderRoutes ──────────────────────────────────── */
export function renderRoutes() {
  const routeComparators = {
    name: (a, b) => (a.name || "").localeCompare(b.name || ""),
    backend: (a, b) => (nodeNameById(a.node_id) || "").localeCompare(nodeNameById(b.node_id) || ""),
    status: (a, b) => (a.health_status || "").localeCompare(b.health_status || ""),
    weight: (a, b) => ((a.effective_weight || 0) - (b.effective_weight || 0)),
  };
  refs.routesHead.innerHTML = `<tr>${sortTh("routes", "name", "Маршрут")}${sortTh("routes", "backend", "Backend / Entry")}${sortTh("routes", "status", "Статус")}${sortTh("routes", "weight", "Вес")}<th>Прогрев</th><th>Действия</th></tr>`;
  const routes = sortedBy(filteredRoutes(), "routes", routeComparators);
  const allRoutes = state.routes;
  const filterActive = !!(refs.routesStatus.value || refs.routesSearch.value);
  refs.routesBody.innerHTML = routes.length
    ? routes.map((r) => {
      const nName = nodeNameById(r.node_id);
      const entryName = nodeNameById(r.entry_node_id);
      const routeHint = r.routing_eligible ? `<div style="margin-top:3px">${chip("ok", "eligible")}</div>` : (r.routing_reason ? `<div style="margin-top:3px">${chip("warn", routeReasonLabel(r.routing_reason))}</div>` : "");
      const rProbe = latestProbeForRoute(r.id);
      const routeProbeHint = rProbe ? `<div class="muted" style="font-size:10px;margin-top:3px">${rProbe.is_reachable ? "probe ok" : "probe fail"}${rProbe.latency_ms != null ? " \u00B7 " + rProbe.latency_ms + "ms" : ""}${!rProbe.is_reachable && rProbe.error_phase ? " \u00B7 " + rProbe.error_phase : ""}</div>` : "";
      const entryHtml = r.entry_node_id ? `<div class="muted" style="font-size:11px">entry: ${entryName ? esc(entryName) + " " : ""}${uuidCell(r.entry_node_id)}</div>` : `<div class="muted" style="font-size:11px">entry: -</div>`;
      return `<tr><td><strong>${esc(r.name)}</strong><div>${uuidCell(r.id)}</div></td><td>${nName ? `<strong>${esc(nName)}</strong> ` : ""}${uuidCell(r.node_id)}${entryHtml}</td><td>${r.health_status === "healthy" ? chip("ok", routeStatusLabel(r.health_status)) : (r.health_status === "blocked" ? chip("bad", routeStatusLabel(r.health_status)) : chip("warn", routeStatusLabel(r.health_status)))}${routeHint}${routeProbeHint}</td><td class="mono">${esc(r.effective_weight)} / ${esc(r.base_weight)}</td><td class="mono">${esc(r.warmup_stage == null ? "-" : r.warmup_stage)}</td><td><div class="actions"><button class="btn-mini route-action" data-id="${esc(r.id)}" data-action="set_healthy">Healthy</button><button class="btn-mini route-action" data-id="${esc(r.id)}" data-action="set_degraded">Degrade</button><button class="btn-mini route-action" data-id="${esc(r.id)}" data-action="block">Block</button><button class="btn-mini btn-info route-entry" data-id="${esc(r.id)}">Entry</button><button class="btn-mini route-edit" data-id="${esc(r.id)}">Edit</button></div></td></tr>`;
    }).join("")
    : (!filterActive && allRoutes.length === 0
      ? `<tr><td colspan="6"><div class="empty-state">
          <div class="empty-state-icon">🛣</div>
          <div class="empty-state-title">Маршрутов пока нет</div>
          <div class="empty-state-hint">Создайте первый маршрут — он свяжет backend-ноду и transport profile в единицу доставки трафика.</div>
          <div class="empty-state-action"><button class="btn btn-primary routes-empty-create" style="width:auto">+ Создать маршрут</button></div>
        </div></td></tr>`
      : `<tr><td colspan="6" class="empty">Нет маршрутов по фильтрам.</td></tr>`);
}

/* ── openEntryNodeModal ────────────────────────────── */
export function openEntryNodeModal(routeId) {
  const route = state.routes.find((r) => r.id === routeId);
  if (!route) { notify("Маршрут не найден", true); return; }
  const entryNodes = ((state.status && state.status.nodes) || []).filter((n) => ["whitelist_entry", "entry"].includes(String(n.role || "").toLowerCase()));
  const optionsHtml = [`<div class="entry-option${!route.entry_node_id ? " selected" : ""}" data-entry-id="none">Без entry (прямое подключение)</div>`].concat(
    entryNodes.map((en) => {
      const sel = route.entry_node_id === en.id ? " selected" : "";
      const g = nodeGeo(en.region);
      return `<div class="entry-option${sel}" data-entry-id="${esc(en.id)}"><strong>${esc(en.name)}</strong> <span class="geo"><span class="flag">${esc(g.flag)}</span>${esc(g.country)}</span><div class="muted" style="font-size:11px">${uuidCell(en.id)}</div></div>`;
    })
  ).join("");
  openModal({
    title: `Entry node для "${route.name}"`,
    bodyHtml: `<div id="entry-options" class="entry-option-list">${optionsHtml}</div>`,
    footerHtml: `<button class="btn btn-ghost" id="entry-modal-cancel">Отмена</button>`,
    onMount: ({ root, close }) => {
      root.querySelector("#entry-modal-cancel").addEventListener("click", close);
      root.querySelector("#entry-options").addEventListener("click", (ev) => {
        const opt = ev.target.closest(".entry-option");
        if (!opt) return;
        const entryId = opt.dataset.entryId;
        const body = { entry_node_id: entryId === "none" ? null : entryId };
        close();
        runAction(`Set entry node on route ${shortId(routeId)}`, () => req(`/api/v1/routes/${encodeURIComponent(routeId)}`, { method: "PATCH", body })).then(() => _refreshAll()).catch(() => {});
      });
    },
  });
}

/* ── openRouteCreateModal ──────────────────────────── */
export function openRouteCreateModal() {
  if (!state.transportProfiles.length) { req("/api/v1/routes/transport-profiles?limit=200").then((tp) => { state.transportProfiles = tp; openRouteCreateModal(); }); return; }
  openModal({
    title: "Создать маршрут",
    bodyHtml: _routeFormBody({ name: "", nodeId: null, entryNodeId: null, tpId: null, baseWeight: 50, healthStatus: "healthy", isCreate: true }),
    footerHtml: `<button class="btn btn-ghost" id="rf-cancel">Отмена</button><button class="btn btn-primary" id="rf-submit">Создать</button>`,
    onMount: ({ root, close }) => {
      root.querySelector("#rf-cancel").addEventListener("click", close);
      root.querySelector("#rf-submit").addEventListener("click", () => {
        const name = root.querySelector("#rf-name").value.trim();
        const nodeId = root.querySelector("#rf-node").value;
        const entryVal = root.querySelector("#rf-entry").value;
        const tpId = root.querySelector("#rf-tp").value;
        const weight = parseInt(root.querySelector("#rf-weight").value, 10);
        const status = root.querySelector("#rf-status").value;
        if (!name) { notify("Введите имя маршрута", true); return; }
        if (!nodeId) { notify("Выберите backend ноду", true); return; }
        if (!tpId) { notify("Выберите transport profile", true); return; }
        const body = { name, node_id: nodeId, transport_profile_id: tpId, base_weight: isNaN(weight) ? 50 : weight, health_status: status };
        if (entryVal) body.entry_node_id = entryVal;
        close();
        runAction("Create route", () => req("/api/v1/routes", { method: "POST", body })).then(() => _refreshAll()).catch(() => {});
      });
    },
  });
}

/* ── openRouteEditModal ────────────────────────────── */
export function openRouteEditModal(routeId) {
  const route = state.routes.find((r) => r.id === routeId);
  if (!route) { notify("Маршрут не найден", true); return; }
  openModal({
    title: `Редактировать "${route.name}"`,
    bodyHtml: _routeFormBody({ name: route.name, nodeId: route.node_id, entryNodeId: route.entry_node_id, tpId: route.transport_profile_id, baseWeight: route.base_weight, healthStatus: route.health_status, isCreate: false }),
    footerHtml: `<button class="btn btn-ghost" id="rf-cancel">Отмена</button><button class="btn btn-primary" id="rf-submit">Сохранить</button>`,
    onMount: ({ root, close }) => {
      root.querySelector("#rf-cancel").addEventListener("click", close);
      root.querySelector("#rf-submit").addEventListener("click", () => {
        const name = root.querySelector("#rf-name").value.trim();
        const nodeId = root.querySelector("#rf-node").value;
        const entryVal = root.querySelector("#rf-entry").value;
        const weight = parseInt(root.querySelector("#rf-weight").value, 10);
        const body = {};
        if (name && name !== route.name) body.name = name;
        if (nodeId && nodeId !== route.node_id) body.node_id = nodeId;
        const newEntry = entryVal || null;
        if (newEntry !== (route.entry_node_id || null)) body.entry_node_id = newEntry;
        if (!isNaN(weight) && weight !== route.base_weight) body.base_weight = weight;
        if (!Object.keys(body).length) { close(); return; }
        close();
        runAction(`Update route ${shortId(routeId)}`, () => req(`/api/v1/routes/${encodeURIComponent(routeId)}`, { method: "PATCH", body })).then(() => _refreshAll()).catch(() => {});
      });
    },
  });
}

/* ── bindRouteEvents ───────────────────────────────── */
export function bindRouteEvents() {
  /* Create route button */
  const createBtn = document.getElementById("routes-create-btn");
  if (createBtn) createBtn.addEventListener("click", () => openRouteCreateModal());

  /* Routes table click delegation */
  refs.routesBody.addEventListener("click", async (ev) => {
    const t = ev.target; if (!(t instanceof HTMLElement)) return;
    const emptyCreate = t.closest(".routes-empty-create");
    if (emptyCreate) { openRouteCreateModal(); return; }
    const editBtn = t.closest(".route-edit");
    if (editBtn && editBtn.dataset.id) { openRouteEditModal(editBtn.dataset.id); return; }
    const entryBtn = t.closest(".route-entry");
    if (entryBtn && entryBtn.dataset.id) { openEntryNodeModal(entryBtn.dataset.id); return; }
    const b = t.closest(".route-action"); if (!b || !b.dataset.id || !b.dataset.action) return;
    const action = b.dataset.action;
    if (action === "block") { const ok = await confirmAction("Блокировка маршрута", `Заблокировать маршрут ${shortId(b.dataset.id)}...?`); if (!ok) return; }
    runAction(`Route ${action} ${b.dataset.id}`, () => req("/api/v1/admin/set-route-health", { method: "POST", body: { route_id: b.dataset.id, action: action, cooldown_hours: 6 } })).then(() => _refreshAll()).catch(() => {});
  });

  /* Reload */
  refs.routesReload.addEventListener("click", () => _refreshAll(true).catch((e) => notify(`Ошибка: ${e.message}`, true)));
}
