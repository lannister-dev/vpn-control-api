import { state, refs, $ } from '../state.js';
import {
  esc, fmtDate, chip, uuidCell, shortId, nodeGeo, nodeNameById,
  routeStatusLabel, latestProbeForNode, capacityBar, relTime,
  nodeRoleLabel, nodeRoleClass, routingReasonLabel,
  sortTh, sortedBy,
} from '../utils.js';
import { req, runAction, copyToClipboard } from '../api.js';
import { notify, confirmAction } from '../ui.js';

/* ── Late-binding callbacks (set by app.js) ────────── */
let _refreshAll = () => {};
let _render = () => {};
export function setCallbacks(refreshAll, render) { _refreshAll = refreshAll; _render = render; }

/* ── filteredNodes ─────────────────────────────────── */
export function filteredNodes() {
  if (!state.status || !state.status.nodes) return [];
  const q = refs.nodesSearch.value.trim().toLowerCase();
  const health = refs.nodesHealth.value;
  const st = refs.nodesState.value;
  return state.status.nodes.filter((n) => {
    if (health === "healthy" && !n.is_healthy) return false;
    if (health === "unhealthy" && n.is_healthy) return false;
    if (st === "draining" && !n.is_draining) return false;
    if (st === "disabled" && n.is_enabled) return false;
    if (st === "active" && (n.is_draining || !n.is_enabled)) return false;
    if (q) { const g = nodeGeo(n.region); const hay = [n.name, n.id, n.role, n.public_domain, n.reality_ip, n.region, g.country, g.code].join(" ").toLowerCase(); if (!hay.includes(q)) return false; }
    return true;
  });
}

/* ── renderNodes ───────────────────────────────────── */
export function renderNodes() {
  const nodeComparators = {
    name: (a, b) => (a.name || "").localeCompare(b.name || ""),
    region: (a, b) => { const ga = nodeGeo(a.region); const gb = nodeGeo(b.region); return ga.country.localeCompare(gb.country); },
    health: (a, b) => (a.is_healthy === b.is_healthy ? 0 : a.is_healthy ? -1 : 1),
    load: (a, b) => ((a.capacity ? a.placements_backend / a.capacity : 0) - (b.capacity ? b.placements_backend / b.capacity : 0)),
    heartbeat: (a, b) => (new Date(a.last_seen_at || 0).getTime() - new Date(b.last_seen_at || 0).getTime()),
  };
  refs.nodesHead.innerHTML = `<tr>${sortTh("nodes", "name", "Сервер")}${sortTh("nodes", "region", "Гео")}${sortTh("nodes", "health", "Здоровье")}<th>Состояние</th>${sortTh("nodes", "load", "Нагрузка")}${sortTh("nodes", "heartbeat", "Heartbeat")}<th>Действия</th></tr>`;
  const nodes = sortedBy(filteredNodes(), "nodes", nodeComparators);
  refs.nodesBody.innerHTML = nodes.length
    ? nodes.map((n) => {
      const g = nodeGeo(n.region);
      const routingHint = n.routing_eligible ? `<div style="margin-top:3px">${chip("ok", "eligible")}</div>` : (n.routing_reason ? `<div style="margin-top:3px">${chip("warn", routingReasonLabel(n.routing_reason))}</div>` : "");
      const isEntryNode = ["whitelist_entry", "entry"].includes(String(n.role || "").toLowerCase());
      const healthCol = isEntryNode ? chip("info", "Relay") : (n.is_healthy ? chip("ok", "Здоров") : chip("bad", "Нездоров"));
      const nodeProbe = latestProbeForNode(n.id);
      const probeLine = nodeProbe ? `<div class="muted" style="font-size:10px;margin-top:3px">${nodeProbe.is_reachable ? "probe ok" : "probe fail"}${nodeProbe.latency_ms != null ? " \u00B7 " + nodeProbe.latency_ms + "ms" : ""}</div>` : "";
      const heartbeatCol = isEntryNode
        ? (nodeProbe ? `${nodeProbe.is_reachable ? chip("ok", "OK") : chip("bad", "FAIL")}${nodeProbe.latency_ms != null ? `<div class="mono muted" style="font-size:10px;margin-top:2px">${nodeProbe.latency_ms}ms</div>` : ""}` : `<span class="muted">no probe</span>`)
        : `<span title="${esc(fmtDate(n.last_seen_at))}">${relTime(n.last_seen_at)}</span>${probeLine}`;
      const loadCol = isEntryNode ? (n.upstream_node_id ? `<span class="muted" style="font-size:11px">\u2192 ${esc(nodeNameById(n.upstream_node_id) || shortId(n.upstream_node_id))}</span>` : `<span class="muted" style="font-size:11px">upstream \u2014</span>`) : capacityBar(n.placements_backend, n.capacity);
      return `<tr><td><strong>${esc(n.name)}</strong> ${chip(nodeRoleClass(n.role), nodeRoleLabel(n.role))}<div>${uuidCell(n.id)}</div>${n.public_domain ? `<div class="mono muted" style="font-size:11px">${esc(n.public_domain)}</div>` : ""}${n.reality_ip ? `<div class="mono muted" style="font-size:11px">reality: ${esc(n.reality_ip)}</div>` : ""}</td><td><div class="geo"><span class="flag">${esc(g.flag)}</span>${esc(g.country)}</div><div class="mono muted">${esc(g.regionText)}</div></td><td>${healthCol}</td><td>${n.is_draining ? chip("warn", "Draining") : (!n.is_enabled ? chip("bad", "Отключен") : chip("ok", "Активен"))}${routingHint}</td><td>${loadCol}</td><td>${heartbeatCol}</td><td><div class="actions"><button class="btn-mini node-action" data-action="drain" data-id="${esc(n.id)}">Drain</button><button class="btn-mini node-action" data-action="enable" data-id="${esc(n.id)}">Enable</button><button class="btn-mini node-config" data-id="${esc(n.id)}">Настройки</button></div></td></tr>`;
    }).join("")
    : `<tr><td colspan="7" class="empty">Нет серверов по текущим фильтрам.</td></tr>`;
}

/* ── openNodeConfigModal ───────────────────────────── */
export function openNodeConfigModal(nodeId) {
  if (!state.status || !state.status.nodes) return;
  const n = state.status.nodes.find((x) => x.id === nodeId);
  if (!n) { notify("Сервер не найден", true); return; }
  state.selectedNode = n;
  const g = nodeGeo(n.region);
  const isEntry = ["whitelist_entry", "entry"].includes(String(n.role || "").toLowerCase());
  const nodeRoutes = state.routes.filter((r) => r.node_id === n.id || r.entry_node_id === n.id);
  const entryRoutes = isEntry ? state.routes.filter((r) => r.entry_node_id === n.id) : [];
  const nodePlacementsCount = state.placements.filter((p) => p.backend_node_id === n.id).length;
  const routesVisible = nodeRoutes.slice(0, 4);
  const routesExtra = nodeRoutes.length - routesVisible.length;
  const routesHtml = nodeRoutes.length
    ? routesVisible.map((r) => {
      const sCls = r.health_status === "healthy" ? "ok" : (r.health_status === "blocked" ? "bad" : "warn");
      const backendName = nodeNameById(r.node_id) || shortId(r.node_id);
      const entryName = r.entry_node_id ? (nodeNameById(r.entry_node_id) || shortId(r.entry_node_id)) : null;
      const pathLabel = entryName ? `${backendName} via ${entryName}` : backendName;
      return `<div style="font-size:12px;margin-bottom:2px">${esc(r.name)} ${chip(sCls, routeStatusLabel(r.health_status))}<span class="muted" style="font-size:11px;margin-left:4px">${esc(pathLabel)}</span></div>`;
    }).join("") + (routesExtra > 0 ? `<div class="muted" style="font-size:11px">+ ещё ${routesExtra}</div>` : "")
    : `<div class="empty">Нет маршрутов</div>`;
  refs.nodeConfigModal.innerHTML = `<div class="modal-overlay"><div class="modal-box wide">
    <div class="modal-title">${esc(n.name)}</div>
    <div class="modal-body">
      <div class="form-section"><div class="form-section-title">Информация</div>
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px">
          <div class="stat-inline">ID: ${uuidCell(n.id)}</div>
          <div class="stat-inline">Geo: <strong>${esc(g.short)}</strong></div>
          <div class="stat-inline">Role: ${chip(nodeRoleClass(n.role), nodeRoleLabel(n.role))}</div>
        </div>
        <div style="margin-bottom:8px">${isEntry ? chip("info", "Relay") : (n.is_healthy ? chip("ok", "Здоров") : chip("bad", "Нездоров"))} ${n.is_draining ? chip("warn", "Draining") : (!n.is_enabled ? chip("bad", "Отключен") : chip("ok", "Активен"))}</div>
        ${isEntry ? "" : `<div style="margin-bottom:8px"><div class="muted" style="font-size:11px;margin-bottom:2px">Нагрузка</div>${capacityBar(n.placements_backend, n.capacity)}</div>`}
        <div class="mini-kpi-row">
          <div class="mini-kpi"><div class="mini-kpi-label">Маршруты</div><div class="mini-kpi-value">${nodeRoutes.length}</div></div>
          ${isEntry ? "" : `<div class="mini-kpi"><div class="mini-kpi-label">Плейсменты</div><div class="mini-kpi-value">${nodePlacementsCount}</div></div>`}
        </div>
        ${isEntry ? `<div style="margin-top:8px"><div class="muted" style="font-size:11px;margin-bottom:4px">Upstream</div>${n.upstream_node_id ? (() => { const ub = ((state.status && state.status.nodes) || []).find((x) => x.id === n.upstream_node_id); const ubName = ub ? ub.name : shortId(n.upstream_node_id); const ubGeo = ub ? nodeGeo(ub.region) : null; return '<div style="font-size:12px"><strong>' + esc(ubName) + '</strong>' + (ubGeo ? ' <span class="muted">' + esc(ubGeo.short) + '</span>' : '') + '</div>'; })() : '<div class="muted" style="font-size:12px">Не назначен</div>'}${entryRoutes.length ? '<div class="muted" style="font-size:11px;margin-top:4px;margin-bottom:2px">Маршруты через entry</div>' + entryRoutes.map((r) => { const bName = nodeNameById(r.node_id) || shortId(r.node_id); return '<div style="font-size:12px;margin-bottom:2px">' + esc(r.name) + ' \u2192 <strong>' + esc(bName) + '</strong></div>'; }).join("") : ""}</div>` : ""}
        <div style="margin-top:8px"><div class="muted" style="font-size:11px;margin-bottom:4px">Последний probe</div>${(() => {
          const np = latestProbeForNode(n.id);
          if (!np) return '<div class="empty" style="font-size:12px">Нет probe-данных</div>';
          const s = np.is_reachable ? chip("ok", "OK") : chip("bad", "FAIL");
          return '<div style="font-size:12px">' + s + (np.latency_ms != null ? ' <span class="mono">' + np.latency_ms + 'ms</span>' : '') + (np.error_phase ? ' ' + chip("warn", np.error_phase) : '') + (np.error ? ' <span class="muted">' + esc(np.error) + '</span>' : '') + '<div class="muted" style="font-size:11px">' + esc(np.source) + ' | ' + fmtDate(np.checked_at) + '</div></div>';
        })()}</div>
        <div style="margin-top:8px"><div class="muted" style="font-size:11px;margin-bottom:4px">Маршруты</div>${routesHtml}</div>
      </div>
      <div class="form-section"><div class="form-section-title">Конфигурация</div>
        <div class="form-group"><label class="form-label">Role</label><select id="edit-role" class="select"><option value="backend"${n.role === "backend" ? " selected" : ""}>backend</option><option value="whitelist_entry"${n.role === "whitelist_entry" ? " selected" : ""}>whitelist_entry</option><option value="entry"${n.role === "entry" ? " selected" : ""}>entry</option></select></div>
        <div class="form-group"><label class="form-label">Region</label><input id="edit-region" class="input" value="${esc(n.region || "")}" /></div>
        ${isEntry ? "" : `<div class="form-group" id="fg-public-domain"><label class="form-label">Public domain</label><input id="edit-public-domain" class="input" value="${esc(n.public_domain || "")}" /></div>`}
        <div class="form-group"><label class="form-label">${isEntry ? "Адрес (IP)" : "Reality IP"}</label><input id="edit-reality-ip" class="input" value="${esc(n.reality_ip || "")}" placeholder="${isEntry ? "IP-адрес entry ноды" : ""}" /></div>
        ${isEntry ? `<div class="form-group"><label class="form-label">Upstream бэкенд</label><select id="edit-upstream" class="select"><option value="">— нет —</option>${((state.status && state.status.nodes) || []).filter((b) => b.role === "backend" && b.is_active !== false).map((b) => { const bg = nodeGeo(b.region); return '<option value="' + b.id + '"' + (n.upstream_node_id === b.id ? ' selected' : '') + '>' + esc(b.name) + ' (' + esc(bg.short) + ')</option>'; }).join("")}</select></div>` : `<div class="form-group"><label class="form-label">Capacity</label><input id="edit-capacity" class="input" type="number" min="1" max="10000" value="${n.capacity || ""}" /></div>`}
      </div>
      <div class="form-section"><div class="form-section-title">Действия</div>
        <div class="actions">
          <button class="btn btn-warn" id="ncm-drain">Drain</button>
          <button class="btn btn-primary" id="ncm-enable">Enable</button>
        </div>
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost" id="ncm-cancel">Закрыть</button>
      <button class="btn btn-primary" id="ncm-save">Сохранить конфигурацию</button>
    </div>
  </div></div>`;
  const closeModal = () => { refs.nodeConfigModal.innerHTML = ""; };
  refs.nodeConfigModal.querySelector("#ncm-cancel").addEventListener("click", closeModal);
  refs.nodeConfigModal.querySelector(".modal-overlay").addEventListener("click", (ev) => { if (ev.target === ev.currentTarget) closeModal(); });
  refs.nodeConfigModal.querySelector("#ncm-save").addEventListener("click", () => {
    const body = {};
    const role = document.getElementById("edit-role").value;
    const region = document.getElementById("edit-region").value;
    const publicDomainEl = document.getElementById("edit-public-domain");
    const publicDomain = publicDomainEl ? publicDomainEl.value : "";
    const realityIp = document.getElementById("edit-reality-ip").value;
    const capacityEl = document.getElementById("edit-capacity");
    const upstreamEl = document.getElementById("edit-upstream");
    const capacity = capacityEl ? capacityEl.value : "";
    const upstream = upstreamEl ? upstreamEl.value : "";
    if (role !== (n.role || "backend")) body.role = role;
    if (region !== (n.region || "")) body.region = region;
    if (publicDomainEl && publicDomain !== (n.public_domain || "")) body.public_domain = publicDomain;
    if (realityIp !== (n.reality_ip || "")) body.reality_ip = realityIp || null;
    if (capacity !== "" && Number(capacity) !== n.capacity) body.capacity = Number(capacity);
    if (upstreamEl && upstream !== (n.upstream_node_id || "")) body.upstream_node_id = upstream || null;
    if (!Object.keys(body).length) { notify("Нет изменений", false); return; }
    closeModal();
    runAction(`Update node config ${n.id}`, () => req(`/api/v1/agent/nodes/${encodeURIComponent(n.id)}`, { method: "PATCH", body })).then(() => _refreshAll()).catch(() => {});
  });
  refs.nodeConfigModal.querySelector("#ncm-drain").addEventListener("click", async () => {
    const ok = await confirmAction("Drain ноды", `Перевести "${esc(n.name)}" в режим drain?`, "btn-warn");
    if (!ok) return;
    closeModal();
    runAction(`Node drain ${n.id}`, () => req(`/api/v1/agent/nodes/${encodeURIComponent(n.id)}/drain`, { method: "POST", body: {} })).then(() => _refreshAll()).catch(() => {});
  });
  refs.nodeConfigModal.querySelector("#ncm-enable").addEventListener("click", async () => {
    const ok = await confirmAction("Enable ноды", `Активировать ноду "${esc(n.name)}"?`, "btn-primary");
    if (!ok) return;
    closeModal();
    runAction(`Node enable ${n.id}`, () => req(`/api/v1/agent/nodes/${encodeURIComponent(n.id)}/enable`, { method: "POST", body: {} })).then(() => _refreshAll()).catch(() => {});
  });
}

/* ── openAddNodeModal ──────────────────────────────── */
export function openAddNodeModal() {
  const closeModal = () => { refs.addNodeModal.innerHTML = ""; };
  refs.addNodeModal.innerHTML = `<div class="modal-overlay"><div class="modal-box wide">
    <div class="modal-title">Добавить VPN-сервер</div>
    <div class="modal-body">
      <div class="form-section">
        <div class="form-section-title">Параметры ноды</div>
        <div class="form-group"><label class="form-label">Имя</label><input id="an-name" class="input" placeholder="например, vpn-yc-entry-03" /></div>
        <div class="form-group"><label class="form-label">Роль</label><select id="an-role" class="select">
          <option value="backend">backend \u2014 Xray backend</option>
          <option value="entry">entry \u2014 TCP relay</option>
          <option value="whitelist_entry">whitelist_entry \u2014 whitelisted IP entry</option>
        </select></div>
        <div class="form-group"><label class="form-label">Регион</label><input id="an-region" class="input" placeholder="например, ru-central1-d" /></div>
        <div class="form-group"><label class="form-label">Capacity</label><input id="an-capacity" class="input" type="number" min="1" max="10000" value="100" /></div>
        <div class="form-group"><label class="form-label">Public domain <span class="muted">(опционально)</span></label><input id="an-public-domain" class="input" placeholder="leave empty for entry/relay roles" /></div>
        <div class="form-group"><label class="form-label">Reality IP <span class="muted">(опционально)</span></label><input id="an-reality-ip" class="input" placeholder="" /></div>
      </div>
      <div id="an-result" class="form-section" style="display:none">
        <div class="form-section-title">Установщик готов</div>
        <div class="muted" style="font-size:12px;margin-bottom:8px">Скопируйте команду и выполните на новой VM под root. Токен одноразовый.</div>
        <pre id="an-install-cmd" class="mono" style="white-space:pre-wrap;word-break:break-all;padding:10px;background:var(--bg-soft);border:1px solid var(--line);border-radius:8px;font-size:12px"></pre>
        <div style="margin-top:6px"><button id="an-copy" class="btn btn-ghost">Скопировать</button></div>
        <div id="an-expires" class="muted" style="font-size:11px;margin-top:6px"></div>
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost" id="an-cancel">Закрыть</button>
      <button class="btn btn-primary" id="an-create">Создать ноду</button>
    </div>
  </div></div>`;
  refs.addNodeModal.querySelector("#an-cancel").addEventListener("click", closeModal);
  refs.addNodeModal.querySelector(".modal-overlay").addEventListener("click", (ev) => { if (ev.target === ev.currentTarget) closeModal(); });
  refs.addNodeModal.querySelector("#an-create").addEventListener("click", async () => {
    const name = document.getElementById("an-name").value.trim();
    const role = document.getElementById("an-role").value;
    const region = document.getElementById("an-region").value.trim();
    const capacity = Number(document.getElementById("an-capacity").value || 100);
    const publicDomain = document.getElementById("an-public-domain").value.trim();
    const realityIp = document.getElementById("an-reality-ip").value.trim();
    if (!name || !region) { notify("Заполните имя и регион", true); return; }
    const body = { name, role, region, capacity, public_domain: publicDomain, reality_ip: realityIp || null };
    const createBtn = refs.addNodeModal.querySelector("#an-create");
    createBtn.disabled = true;
    try {
      const out = await runAction(`Create node ${name}`, () => req(`/api/v1/admin/nodes`, { method: "POST", body }));
      if (!out) return;
      const resultDiv = refs.addNodeModal.querySelector("#an-result");
      const cmdEl = refs.addNodeModal.querySelector("#an-install-cmd");
      const expEl = refs.addNodeModal.querySelector("#an-expires");
      cmdEl.textContent = out.install_command || "";
      expEl.textContent = out.bootstrap_token_expires_at ? `Токен истекает: ${fmtDate(out.bootstrap_token_expires_at)}` : "";
      resultDiv.style.display = "";
      createBtn.textContent = "Создано";
      _refreshAll().catch(() => {});
    } catch (_) {
      createBtn.disabled = false;
    }
  });
  refs.addNodeModal.addEventListener("click", (ev) => {
    if (ev.target && ev.target.id === "an-copy") {
      const cmdEl = refs.addNodeModal.querySelector("#an-install-cmd");
      if (cmdEl) copyToClipboard(cmdEl.textContent);
    }
  });
}

/* ── bindNodeEvents ────────────────────────────────── */
export function bindNodeEvents() {
  /* Nodes table click delegation */
  refs.nodesBody.addEventListener("click", async (ev) => {
    const t = ev.target; if (!(t instanceof HTMLElement)) return;
    const cfgBtn = t.closest(".node-config"); const abtn = t.closest(".node-action");
    if (cfgBtn && cfgBtn.dataset.id) {
      openNodeConfigModal(cfgBtn.dataset.id);
      return;
    }
    if (abtn && abtn.dataset.id && abtn.dataset.action) {
      const id = abtn.dataset.id; const action = abtn.dataset.action; const nodeName = nodeNameById(id) || shortId(id);
      const ok = await confirmAction(action === "drain" ? "Drain ноды" : "Enable ноды", action === "drain" ? `Перевести "${nodeName}" в режим drain?` : `Активировать ноду "${nodeName}"?`, action === "drain" ? "btn-warn" : "btn-primary");
      if (!ok) return;
      runAction(`Node ${action} ${id}`, () => req(action === "drain" ? `/api/v1/agent/nodes/${encodeURIComponent(id)}/drain` : `/api/v1/agent/nodes/${encodeURIComponent(id)}/enable`, { method: "POST", body: {} })).then(() => _refreshAll()).catch(() => {});
      return;
    }
  });

  /* Clear filters */
  refs.nodesClear.addEventListener("click", () => { refs.nodesSearch.value = ""; refs.nodesHealth.value = ""; refs.nodesState.value = ""; _render(); });

  /* Reload */
  refs.nodesReload.addEventListener("click", () => _refreshAll(true).catch((e) => notify(`Ошибка: ${e.message}`, true)));

  /* Add node */
  if (refs.nodesAdd) refs.nodesAdd.addEventListener("click", () => openAddNodeModal());
}
