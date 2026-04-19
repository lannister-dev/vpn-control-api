import { state, refs, $ } from '../state.js';
import {
  esc, fmtDate, chip, uuidCell, shortId, nodeGeo, nodeNameById,
  routeStatusLabel, latestProbeForNode, capacityBar, relTime,
  nodeRoleLabel, nodeRoleClass, routingReasonLabel, routeReasonLabel,
  sortTh, sortedBy,
} from '../utils.js';
import { req, runAction, copyToClipboard } from '../api.js';
import { notify, confirmAction, openModal } from '../ui.js';

/* ── Late-binding callbacks (set by app.js) ────────── */
let _refreshAll = () => {};
let _render = () => {};
export function setCallbacks(refreshAll, render) { _refreshAll = refreshAll; _render = render; }

const SUBS = ["overview", "routes", "placements", "probes", "transport"];
const isEntryNode = (n) => ["whitelist_entry", "entry"].includes(String(n.role || "").toLowerCase());
let _lastOverviewRenderNodeId = null;

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
    if (q) {
      const g = nodeGeo(n.region);
      const hay = [n.name, n.id, n.role, n.public_domain, n.reality_ip, n.region, g.country, g.code].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
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
  refs.nodesHead.innerHTML = `<tr>${sortTh("nodes", "name", "Сервер")}${sortTh("nodes", "region", "Гео")}${sortTh("nodes", "health", "Здоровье")}<th>Состояние</th>${sortTh("nodes", "load", "Нагрузка")}${sortTh("nodes", "heartbeat", "Heartbeat")}<th></th></tr>`;
  const nodes = sortedBy(filteredNodes(), "nodes", nodeComparators);
  const selectedId = state.selectedNode ? state.selectedNode.id : null;
  const allNodes = (state.status && state.status.nodes) || [];
  const filterActive = !!(refs.nodesSearch.value || refs.nodesHealth.value || refs.nodesState.value);
  refs.nodesBody.innerHTML = nodes.length
    ? nodes.map((n) => {
      const g = nodeGeo(n.region);
      const entry = isEntryNode(n);
      const routingHint = n.routing_eligible
        ? `<div style="margin-top:3px">${chip("ok", "eligible")}</div>`
        : (n.routing_reason ? `<div style="margin-top:3px">${chip("warn", routingReasonLabel(n.routing_reason))}</div>` : "");
      const healthCol = entry ? chip("info", "Relay") : (n.is_healthy ? chip("ok", "Здоров") : chip("bad", "Нездоров"));
      const nodeProbe = latestProbeForNode(n.id);
      const probeLine = nodeProbe
        ? `<div class="muted" style="font-size:10px;margin-top:3px">${nodeProbe.is_reachable ? "probe ok" : "probe fail"}${nodeProbe.latency_ms != null ? " · " + nodeProbe.latency_ms + "ms" : ""}</div>`
        : "";
      const heartbeatCol = entry
        ? (nodeProbe
          ? `${nodeProbe.is_reachable ? chip("ok", "OK") : chip("bad", "FAIL")}${nodeProbe.latency_ms != null ? `<div class="mono muted" style="font-size:10px;margin-top:2px">${nodeProbe.latency_ms}ms</div>` : ""}`
          : `<span class="muted">no probe</span>`)
        : `<span title="${esc(fmtDate(n.last_seen_at))}">${relTime(n.last_seen_at)}</span>${probeLine}`;
      const loadCol = entry
        ? (n.upstream_node_id
          ? `<span class="muted" style="font-size:11px">→ ${esc(nodeNameById(n.upstream_node_id) || shortId(n.upstream_node_id))}</span>`
          : `<span class="muted" style="font-size:11px">upstream —</span>`)
        : capacityBar(n.placements_backend, n.capacity);
      const rowCls = "node-row" + (n.id === selectedId ? " node-row-selected" : "");
      return `<tr class="${rowCls}" data-node-id="${esc(n.id)}">`
        + `<td><strong>${esc(n.name)}</strong> ${chip(nodeRoleClass(n.role), nodeRoleLabel(n.role))}<div>${uuidCell(n.id)}</div>${n.public_domain ? `<div class="mono muted" style="font-size:11px">${esc(n.public_domain)}</div>` : ""}${n.reality_ip ? `<div class="mono muted" style="font-size:11px">reality: ${esc(n.reality_ip)}</div>` : ""}</td>`
        + `<td><div class="geo"><span class="flag">${esc(g.flag)}</span>${esc(g.country)}</div><div class="mono muted">${esc(g.regionText)}</div></td>`
        + `<td>${healthCol}</td>`
        + `<td>${n.is_draining ? chip("warn", "Draining") : (!n.is_enabled ? chip("bad", "Отключен") : chip("ok", "Активен"))}${routingHint}</td>`
        + `<td>${loadCol}</td>`
        + `<td>${heartbeatCol}</td>`
        + `<td><button class="btn-mini node-open" data-id="${esc(n.id)}">Открыть →</button></td>`
        + `</tr>`;
    }).join("")
    : (!filterActive && allNodes.length === 0
      ? `<tr><td colspan="7"><div class="empty-state">
          <div class="empty-state-icon">🖥</div>
          <div class="empty-state-title">Серверов пока нет</div>
          <div class="empty-state-hint">Добавьте первую VPN-ноду — сгенерируется bootstrap-команда для новой VM.</div>
          <div class="empty-state-action"><button class="btn btn-primary nodes-empty-add" style="width:auto">+ Добавить сервер</button></div>
        </div></td></tr>`
      : `<tr><td colspan="7" class="empty">Нет серверов по текущим фильтрам.</td></tr>`);
  renderNodeDetail();
}

/* ── open/close detail ─────────────────────────────── */
export function openNodeDetail(nodeId) {
  if (!state.status || !state.status.nodes) return;
  const n = state.status.nodes.find((x) => x.id === nodeId);
  if (!n) { notify("Сервер не найден", true); return; }
  state.selectedNode = n;
  if (!state.selectedNodeSubTab) state.selectedNodeSubTab = "overview";
  renderNodes();
  if (refs.nodeDetail) {
    refs.nodeDetail.scrollTop = 0;
    /* On narrow screens detail stacks under the table — scroll it into view. */
    if (window.matchMedia("(max-width: 1180px)").matches) {
      refs.nodeDetail.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
}

export function closeNodeDetail() {
  state.selectedNode = null;
  _lastOverviewRenderNodeId = null;
  const panel = document.getElementById("tab-nodes");
  if (panel) panel.classList.remove("has-detail");
  if (refs.nodeDetail) refs.nodeDetail.hidden = true;
  renderNodes();
}

/* Backward compatibility (called from app.js import list) */
export const openNodeConfigModal = openNodeDetail;

/* ── renderNodeDetail (container) ──────────────────── */
export function renderNodeDetail() {
  const panel = document.getElementById("tab-nodes");
  if (!panel || !refs.nodeDetail) return;
  if (!state.selectedNode) {
    panel.classList.remove("has-detail");
    refs.nodeDetail.hidden = true;
    return;
  }
  const node = (state.status && state.status.nodes || []).find((x) => x.id === state.selectedNode.id);
  if (!node) {
    closeNodeDetail();
    return;
  }
  state.selectedNode = node;
  panel.classList.add("has-detail");
  refs.nodeDetail.hidden = false;

  const g = nodeGeo(node.region);
  refs.ndTitle.innerHTML = `${esc(node.name)} ${chip(nodeRoleClass(node.role), nodeRoleLabel(node.role))}`;
  refs.ndSubtitle.innerHTML = `<span class="flag">${esc(g.flag)}</span>${esc(g.country)} · <span class="mono">${esc(g.regionText)}</span> · ${uuidCell(node.id)}`;

  refs.ndQuickActions.innerHTML = renderQuickActions(node);

  const routesForNode = state.routes.filter((r) => r.node_id === node.id || r.entry_node_id === node.id);
  const placementsForNode = state.placements.filter((p) => p.backend_node_id === node.id);
  if (refs.ndRoutesCount) refs.ndRoutesCount.textContent = String(routesForNode.length);
  if (refs.ndPlacementsCount) refs.ndPlacementsCount.textContent = String(placementsForNode.length);

  const active = SUBS.includes(state.selectedNodeSubTab) ? state.selectedNodeSubTab : "overview";
  switchNodeSub(active);
}

function switchNodeSub(sub, opts) {
  if (!SUBS.includes(sub)) sub = "overview";
  state.selectedNodeSubTab = sub;
  const force = !!(opts && opts.force);
  document.querySelectorAll(".node-sub[data-nsub]").forEach((b) => b.classList.toggle("active", b.dataset.nsub === sub));
  SUBS.forEach((s) => {
    const el = refs["nd" + s.charAt(0).toUpperCase() + s.slice(1)];
    if (el) el.hidden = (s !== sub);
  });
  const node = state.selectedNode;
  if (!node) return;
  if (sub === "overview") {
    /* Preserve form state on auto-refresh: only re-render if node changed or explicit force. */
    if (force || _lastOverviewRenderNodeId !== node.id) {
      renderNdOverview(node);
      _lastOverviewRenderNodeId = node.id;
    }
  } else if (sub === "routes") renderNdRoutes(node);
  else if (sub === "placements") renderNdPlacements(node);
  else if (sub === "probes") renderNdProbes(node);
  else if (sub === "transport") renderNdTransport(node);
}

/* ── Quick actions bar ─────────────────────────────── */
function renderQuickActions(node) {
  const buttons = [];
  if (node.is_draining || !node.is_enabled) {
    buttons.push(`<button class="btn-mini nd-action" data-action="enable">✓ Активировать</button>`);
  } else {
    buttons.push(`<button class="btn-mini nd-action" data-action="drain">⏳ Drain</button>`);
  }
  return buttons.join("");
}

/* ── Sub: Overview ─────────────────────────────────── */
function renderNdOverview(node) {
  const entry = isEntryNode(node);
  const g = nodeGeo(node.region);
  const nodeProbe = latestProbeForNode(node.id);

  const infoRows = [
    ["Роль", chip(nodeRoleClass(node.role), nodeRoleLabel(node.role))],
    ["Состояние", `${entry ? chip("info", "Relay") : (node.is_healthy ? chip("ok", "Здоров") : chip("bad", "Нездоров"))} ${node.is_draining ? chip("warn", "Draining") : (!node.is_enabled ? chip("bad", "Отключен") : chip("ok", "Активен"))}`],
    ["Регион", `<span class="flag">${esc(g.flag)}</span>${esc(g.country)} · <span class="mono">${esc(g.regionText)}</span>`],
    ["Heartbeat", `<span title="${esc(fmtDate(node.last_seen_at))}">${relTime(node.last_seen_at)}</span>`],
  ];
  if (!entry) infoRows.push(["Нагрузка", capacityBar(node.placements_backend, node.capacity)]);
  if (entry && node.upstream_node_id) {
    const up = (state.status && state.status.nodes || []).find((x) => x.id === node.upstream_node_id);
    infoRows.push(["Upstream", up
      ? `<strong>${esc(up.name)}</strong> <span class="muted mono">${esc(nodeGeo(up.region).short)}</span>`
      : `<span class="muted mono">${esc(shortId(node.upstream_node_id))}</span>`]);
  }
  if (node.public_domain) infoRows.push(["Domain", `<span class="mono">${esc(node.public_domain)}</span>`]);
  if (node.reality_ip) infoRows.push([entry ? "IP" : "Reality IP", `<span class="mono">${esc(node.reality_ip)}</span>`]);

  const probeHtml = nodeProbe
    ? `<div>${nodeProbe.is_reachable ? chip("ok", "OK") : chip("bad", "FAIL")}${nodeProbe.latency_ms != null ? ` <span class="mono">${nodeProbe.latency_ms}ms</span>` : ""}${nodeProbe.error_phase ? " " + chip("warn", nodeProbe.error_phase) : ""}</div>`
      + (nodeProbe.error ? `<div class="muted" style="font-size:11px;margin-top:2px">${esc(nodeProbe.error)}</div>` : "")
      + `<div class="muted" style="font-size:10px;margin-top:4px">${esc(nodeProbe.source || "")} · ${esc(fmtDate(nodeProbe.checked_at))}</div>`
    : `<div class="empty" style="padding:4px 0">Нет данных probe.</div>`;

  const entryNodes = ((state.status && state.status.nodes) || []).filter((b) => ["whitelist_entry", "entry"].includes(String(b.role || "").toLowerCase()));
  const backendNodes = ((state.status && state.status.nodes) || []).filter((b) => String(b.role || "").toLowerCase() === "backend");
  const upstreamOpts = entry
    ? [`<option value="">— нет —</option>`].concat(backendNodes.filter((b) => b.is_active !== false).map((b) => {
      const bg = nodeGeo(b.region);
      return `<option value="${esc(b.id)}"${node.upstream_node_id === b.id ? " selected" : ""}>${esc(b.name)} (${esc(bg.short)})</option>`;
    })).join("")
    : "";

  refs.ndOverview.innerHTML = `
    <div class="nd-section-title">Сводка</div>
    <dl class="nd-info-grid">${infoRows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>
    <div class="nd-section-title">Последний probe</div>
    ${probeHtml}
    <div class="nd-section-title">Конфигурация</div>
    <div class="form-group"><label class="form-label">Role</label>
      <select id="nd-edit-role" class="select">
        <option value="backend"${node.role === "backend" ? " selected" : ""}>backend</option>
        <option value="whitelist_entry"${node.role === "whitelist_entry" ? " selected" : ""}>whitelist_entry</option>
        <option value="entry"${node.role === "entry" ? " selected" : ""}>entry</option>
      </select></div>
    <div class="form-group"><label class="form-label">Region</label>
      <input id="nd-edit-region" class="input" value="${esc(node.region || "")}" /></div>
    ${entry ? "" : `<div class="form-group"><label class="form-label">Public domain</label>
      <input id="nd-edit-public-domain" class="input" value="${esc(node.public_domain || "")}" /></div>`}
    <div class="form-group"><label class="form-label">${entry ? "Адрес (IP)" : "Reality IP"}</label>
      <input id="nd-edit-reality-ip" class="input" value="${esc(node.reality_ip || "")}" placeholder="${entry ? "IP entry ноды" : ""}" /></div>
    ${entry
      ? `<div class="form-group"><label class="form-label">Upstream бэкенд</label>
          <select id="nd-edit-upstream" class="select">${upstreamOpts}</select></div>`
      : `<div class="form-group"><label class="form-label">Capacity</label>
          <input id="nd-edit-capacity" class="input" type="number" min="1" max="10000" value="${node.capacity || ""}" /></div>`}
    <div class="actions" style="margin-top:10px"><button id="nd-save" class="btn btn-primary" style="width:auto">Сохранить конфигурацию</button></div>
  `;
}

/* ── Sub: Routes ───────────────────────────────────── */
function renderNdRoutes(node) {
  const entry = isEntryNode(node);
  const rs = state.routes.filter((r) => r.node_id === node.id || r.entry_node_id === node.id);
  if (!rs.length) {
    refs.ndRoutes.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🛣</div><div class="empty-state-title">Нет маршрутов</div><div class="empty-state-hint">${entry ? "Этот entry-сервер ещё не используется ни одним маршрутом." : "Ни один маршрут пока не указывает на этот бэкенд."}</div></div>`;
    return;
  }
  refs.ndRoutes.innerHTML = `<table class="nd-mini-table">
    <thead><tr><th>Маршрут</th><th>Путь</th><th>Статус</th><th>Вес</th><th></th></tr></thead>
    <tbody>${rs.map((r) => {
      const sCls = r.health_status === "healthy" ? "ok" : (r.health_status === "blocked" ? "bad" : "warn");
      const backendName = nodeNameById(r.node_id) || shortId(r.node_id);
      const entryName = r.entry_node_id ? (nodeNameById(r.entry_node_id) || shortId(r.entry_node_id)) : null;
      const pathHtml = entryName
        ? `<span class="muted">${esc(entryName)}</span> → <strong>${esc(backendName)}</strong>`
        : `<strong>${esc(backendName)}</strong>`;
      const reasonHint = !r.routing_eligible && r.routing_reason
        ? `<div style="margin-top:2px">${chip("warn", routeReasonLabel(r.routing_reason))}</div>` : "";
      return `<tr data-rid="${esc(r.id)}">
        <td><strong>${esc(r.name)}</strong><div class="muted" style="font-size:11px">${uuidCell(r.id)}</div></td>
        <td>${pathHtml}</td>
        <td>${chip(sCls, routeStatusLabel(r.health_status))}${reasonHint}</td>
        <td class="mono">${esc(r.effective_weight)}/${esc(r.base_weight)}</td>
        <td><div class="actions">
          <button class="btn-mini nd-route-action" data-id="${esc(r.id)}" data-action="set_healthy" title="Healthy">✓</button>
          <button class="btn-mini nd-route-action" data-id="${esc(r.id)}" data-action="set_degraded" title="Degrade">~</button>
          <button class="btn-mini nd-route-action" data-id="${esc(r.id)}" data-action="block" title="Block">✕</button>
        </div></td>
      </tr>`;
    }).join("")}</tbody></table>`;
}

/* ── Sub: Placements ───────────────────────────────── */
function renderNdPlacements(node) {
  if (isEntryNode(node)) {
    refs.ndPlacements.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📍</div><div class="empty-state-title">Нет плейсментов</div><div class="empty-state-hint">Entry-ноды не несут VPN-ключей — плейсменты живут на бэкендах.</div></div>`;
    return;
  }
  const ps = state.placements.filter((p) => p.backend_node_id === node.id);
  if (!ps.length) {
    refs.ndPlacements.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📍</div><div class="empty-state-title">Ключей на этом бэкенде нет</div><div class="empty-state-hint">Как только сюда будут назначены ключи, они появятся здесь.</div></div>`;
    return;
  }
  refs.ndPlacements.innerHTML = `<table class="nd-mini-table">
    <thead><tr><th>Ключ</th><th>Версия</th><th>Desired</th><th>Applied</th><th>Обновлено</th></tr></thead>
    <tbody>${ps.map((p) => {
      const unsync = p.op_version !== p.applied_version;
      const appliedChip = p.applied_state === "applied" ? chip("ok", "applied")
        : (p.applied_state === "pending" ? chip("warn", "pending") : chip("bad", "error"));
      return `<tr>
        <td>${uuidCell(p.key_id)}</td>
        <td class="mono">${esc(p.op_version)}/${esc(p.applied_version != null ? p.applied_version : "?")}${unsync ? " " + chip("warn", "unsync") : ""}</td>
        <td>${p.desired_state === "active" ? chip("ok", "active") : chip("warn", "inactive")}</td>
        <td>${appliedChip}</td>
        <td class="muted" style="font-size:11px">${esc(relTime(p.updated_at))}</td>
      </tr>`;
    }).join("")}</tbody></table>`;
}

/* ── Sub: Probes ───────────────────────────────────── */
function renderNdProbes(node) {
  const routeIds = new Set(state.routes.filter((r) => r.node_id === node.id || r.entry_node_id === node.id).map((r) => r.id));
  const probes = state.probes.filter((p) => p.node_id === node.id || (p.route_id && routeIds.has(p.route_id)));
  if (!probes.length) {
    refs.ndProbes.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🔍</div><div class="empty-state-title">Нет probe-отчётов</div><div class="empty-state-hint">Пока ни один внешний источник не проверил эту ноду.</div></div>`;
    return;
  }
  const fail = probes.filter((p) => !p.is_reachable).length;
  const summary = `<div style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap">${chip("info", `всего: ${probes.length}`)}${fail > 0 ? chip("bad", `сбоев: ${fail}`) : chip("ok", "без сбоев")}</div>`;
  refs.ndProbes.innerHTML = summary + `<table class="nd-mini-table">
    <thead><tr><th>Статус</th><th>Latency</th><th>Источник</th><th>Детали</th><th>Время</th></tr></thead>
    <tbody>${probes.slice(0, 50).map((p) => {
      return `<tr>
        <td>${p.is_reachable ? chip("ok", "OK") : chip("bad", "FAIL")}</td>
        <td class="mono">${p.latency_ms != null ? p.latency_ms + "ms" : "-"}</td>
        <td class="muted" style="font-size:11px">${esc(p.source || "-")}</td>
        <td class="muted" style="font-size:11px;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(p.error || "")}">${esc(p.error_phase || p.error || "-")}</td>
        <td class="muted" style="font-size:11px" title="${esc(fmtDate(p.checked_at))}">${esc(relTime(p.checked_at))}</td>
      </tr>`;
    }).join("")}</tbody></table>`;
}

/* ── Sub: Transport ────────────────────────────────── */
function renderNdTransport(node) {
  const t = (state.transportNodes || []).find((x) => x.node_id === node.id);
  if (!t) {
    refs.ndTransport.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🚀</div><div class="empty-state-title">Нет данных от агента</div><div class="empty-state-hint">Откройте вкладку Transport, чтобы подтянуть журнал NATS.</div><div class="empty-state-action"><button class="btn btn-ghost nd-goto-transport">Открыть Transport</button></div></div>`;
    return;
  }
  const verdictCls = t.health_verdict || "ok";
  const verdictLabel = { ok: "Норма", lag: "Задержка", silent: "Молчит", dead: "Нет связи" }[verdictCls] || verdictCls;
  const rows = [
    ["Вердикт", `<span class="t-verdict ${verdictCls}"><span class="t-verdict-dot"></span>${esc(verdictLabel)}</span>`],
    ["Эпоха", `<span class="mono">${esc(t.current_epoch)}</span>`],
    ["Heartbeat", `<span title="${esc(fmtDate(t.last_heartbeat_received_at))}">${esc(relTime(t.last_heartbeat_received_at))}</span>`],
    ["Последняя команда", `<span title="${esc(fmtDate(t.last_command_published_at))}">${esc(relTime(t.last_command_published_at))}</span>`],
    ["Последний результат", `<span title="${esc(fmtDate(t.last_result_received_at))}">${esc(relTime(t.last_result_received_at))}</span>`],
    ["Последний sync", `<span title="${esc(fmtDate(t.last_sync_report_received_at))}">${esc(relTime(t.last_sync_report_received_at))}</span>`],
  ];
  const pending = t.outbox_pending || 0;
  const failed = t.outbox_failed || 0;
  const outboxCls = failed > 0 ? "fail" : (pending > 0 ? "warn" : "clean");
  const outboxLabel = failed > 0 ? `${pending} + ${failed} ошибок` : (pending > 0 ? `${pending} ожидают` : "пусто");
  rows.push(["Очередь", `<span class="t-outbox-count ${outboxCls}">${esc(outboxLabel)}</span>`]);
  refs.ndTransport.innerHTML = `
    <dl class="nd-info-grid">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>
    <div class="actions" style="margin-top:10px"><button class="btn btn-ghost nd-goto-transport" style="width:auto">Открыть полный журнал →</button></div>
  `;
}

/* ── Save overview config ──────────────────────────── */
async function saveOverviewConfig(node) {
  const body = {};
  const role = document.getElementById("nd-edit-role").value;
  const region = document.getElementById("nd-edit-region").value;
  const publicDomainEl = document.getElementById("nd-edit-public-domain");
  const publicDomain = publicDomainEl ? publicDomainEl.value : "";
  const realityIp = document.getElementById("nd-edit-reality-ip").value;
  const capacityEl = document.getElementById("nd-edit-capacity");
  const upstreamEl = document.getElementById("nd-edit-upstream");
  const capacity = capacityEl ? capacityEl.value : "";
  const upstream = upstreamEl ? upstreamEl.value : "";
  if (role !== (node.role || "backend")) body.role = role;
  if (region !== (node.region || "")) body.region = region;
  if (publicDomainEl && publicDomain !== (node.public_domain || "")) body.public_domain = publicDomain;
  if (realityIp !== (node.reality_ip || "")) body.reality_ip = realityIp || null;
  if (capacity !== "" && Number(capacity) !== node.capacity) body.capacity = Number(capacity);
  if (upstreamEl && upstream !== (node.upstream_node_id || "")) body.upstream_node_id = upstream || null;
  if (!Object.keys(body).length) { notify("Нет изменений", false); return; }
  try {
    await runAction(`Update node config ${node.id}`, () => req(`/api/v1/agent/nodes/${encodeURIComponent(node.id)}`, { method: "PATCH", body }));
    _lastOverviewRenderNodeId = null; /* force overview re-render with fresh values after save */
    await _refreshAll();
  } catch (_) {}
}

/* ── openAddNodeModal ──────────────────────────────── */
export function openAddNodeModal() {
  const bodyHtml = `
    <div class="form-section">
      <div class="form-section-title">Параметры ноды</div>
      <div class="form-group"><label class="form-label">Имя</label><input id="an-name" class="input" placeholder="например, vpn-yc-entry-03" /></div>
      <div class="form-group"><label class="form-label">Роль</label><select id="an-role" class="select">
        <option value="backend">backend — Xray backend</option>
        <option value="entry">entry — TCP relay</option>
        <option value="whitelist_entry">whitelist_entry — whitelisted IP entry</option>
      </select></div>
      <div class="row-2">
        <div class="form-group"><label class="form-label">Регион</label><input id="an-region" class="input" placeholder="ru-central1-d" /></div>
        <div class="form-group"><label class="form-label">Capacity</label><input id="an-capacity" class="input" type="number" min="1" max="10000" value="100" /></div>
      </div>
      <div class="form-group"><label class="form-label">Public domain <span class="muted">(опционально)</span></label><input id="an-public-domain" class="input" placeholder="leave empty for entry/relay roles" /></div>
      <div class="form-group"><label class="form-label">Reality IP <span class="muted">(опционально)</span></label><input id="an-reality-ip" class="input" /></div>
    </div>
    <div id="an-result" class="form-section" style="display:none">
      <div class="form-section-title">Установщик готов</div>
      <div class="muted" style="font-size:12px;margin-bottom:8px">Скопируйте команду и выполните на новой VM под root. Токен одноразовый.</div>
      <pre id="an-install-cmd" class="mono" style="white-space:pre-wrap;word-break:break-all;padding:10px;background:rgba(15,23,42,0.6);border:1px solid var(--line);border-radius:8px;font-size:12px"></pre>
      <div style="margin-top:6px"><button id="an-copy" class="btn btn-ghost" style="width:auto">Скопировать</button></div>
      <div id="an-expires" class="muted" style="font-size:11px;margin-top:6px"></div>
    </div>`;
  const footerHtml = `<button class="btn btn-ghost" id="an-cancel">Закрыть</button><button class="btn btn-primary" id="an-create">Создать ноду</button>`;

  openModal({
    title: "Добавить VPN-сервер",
    bodyHtml,
    footerHtml,
    wide: true,
    onMount: ({ root, close }) => {
      root.querySelector("#an-cancel").addEventListener("click", close);
      root.querySelector("#an-create").addEventListener("click", async () => {
        const name = root.querySelector("#an-name").value.trim();
        const role = root.querySelector("#an-role").value;
        const region = root.querySelector("#an-region").value.trim();
        const capacity = Number(root.querySelector("#an-capacity").value || 100);
        const publicDomain = root.querySelector("#an-public-domain").value.trim();
        const realityIp = root.querySelector("#an-reality-ip").value.trim();
        if (!name || !region) { notify("Заполните имя и регион", true); return; }
        const body = { name, role, region, capacity, public_domain: publicDomain, reality_ip: realityIp || null };
        const createBtn = root.querySelector("#an-create");
        createBtn.disabled = true;
        try {
          const out = await runAction(`Create node ${name}`, () => req(`/api/v1/admin/nodes`, { method: "POST", body }));
          if (!out) return;
          root.querySelector("#an-install-cmd").textContent = out.install_command || "";
          root.querySelector("#an-expires").textContent = out.bootstrap_token_expires_at ? `Токен истекает: ${fmtDate(out.bootstrap_token_expires_at)}` : "";
          root.querySelector("#an-result").style.display = "";
          createBtn.textContent = "Создано";
          _refreshAll().catch(() => {});
        } catch (_) {
          createBtn.disabled = false;
        }
      });
      root.querySelector("#an-copy")?.addEventListener("click", () => {
        const cmdEl = root.querySelector("#an-install-cmd");
        if (cmdEl) copyToClipboard(cmdEl.textContent);
      });
      /* Delegated handler for copy button that becomes visible after create. */
      root.addEventListener("click", (ev) => {
        if (ev.target && ev.target.id === "an-copy") {
          const cmdEl = root.querySelector("#an-install-cmd");
          if (cmdEl) copyToClipboard(cmdEl.textContent);
        }
      });
    },
  });
}

/* ── bindNodeEvents ────────────────────────────────── */
export function bindNodeEvents() {
  /* Row click → open detail, or empty-state CTA → add node */
  refs.nodesBody.addEventListener("click", (ev) => {
    const t = ev.target;
    if (!(t instanceof HTMLElement)) return;
    if (t.closest(".nodes-empty-add")) { openAddNodeModal(); return; }
    if (t.closest(".uuid")) return;
    const row = t.closest("tr[data-node-id]");
    if (row && row.dataset.nodeId) {
      openNodeDetail(row.dataset.nodeId);
    }
  });

  /* Detail panel delegation */
  if (refs.nodeDetail) {
    refs.nodeDetail.addEventListener("click", async (ev) => {
      const t = ev.target;
      if (!(t instanceof HTMLElement)) return;
      const subBtn = t.closest(".node-sub[data-nsub]");
      if (subBtn) { switchNodeSub(subBtn.dataset.nsub, { force: true }); return; }

      const node = state.selectedNode;
      if (!node) return;

      const saveBtn = t.closest("#nd-save");
      if (saveBtn) { saveOverviewConfig(node); return; }

      const quick = t.closest(".nd-action");
      if (quick && quick.dataset.action) {
        const action = quick.dataset.action;
        const title = action === "drain" ? "Drain ноды" : "Enable ноды";
        const body = action === "drain" ? `Перевести "${esc(node.name)}" в режим drain?` : `Активировать ноду "${esc(node.name)}"?`;
        const cls = action === "drain" ? "btn-warn" : "btn-primary";
        const ok = await confirmAction(title, body, cls);
        if (!ok) return;
        const endpoint = action === "drain" ? "drain" : "enable";
        runAction(`Node ${action} ${node.id}`, () => req(`/api/v1/agent/nodes/${encodeURIComponent(node.id)}/${endpoint}`, { method: "POST", body: {} }))
          .then(() => _refreshAll()).catch(() => {});
        return;
      }

      const routeAct = t.closest(".nd-route-action");
      if (routeAct && routeAct.dataset.id && routeAct.dataset.action) {
        const action = routeAct.dataset.action;
        if (action === "block") {
          const ok = await confirmAction("Блокировка маршрута", `Заблокировать маршрут ${shortId(routeAct.dataset.id)}…?`);
          if (!ok) return;
        }
        runAction(`Route ${action} ${routeAct.dataset.id}`, () => req("/api/v1/admin/set-route-health", {
          method: "POST",
          body: { route_id: routeAct.dataset.id, action, cooldown_hours: 6 },
        })).then(() => _refreshAll()).catch(() => {});
        return;
      }

      const gotoTransport = t.closest(".nd-goto-transport");
      if (gotoTransport) {
        const btn = document.querySelector('.nav button[data-tab="transport"]');
        if (btn) btn.click();
        return;
      }
    });
  }

  /* Close detail */
  if (refs.ndClose) refs.ndClose.addEventListener("click", () => closeNodeDetail());

  /* Esc closes detail when it's open and no modal is shown */
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!state.selectedNode) return;
    const hasModal = document.querySelector(".modal-overlay");
    if (hasModal) return;
    closeNodeDetail();
  });

  /* Filters */
  refs.nodesClear.addEventListener("click", () => {
    refs.nodesSearch.value = "";
    refs.nodesHealth.value = "";
    refs.nodesState.value = "";
    _render();
  });

  /* Reload */
  refs.nodesReload.addEventListener("click", () => _refreshAll(true).catch((e) => notify(`Ошибка: ${e.message}`, true)));

  /* Add node */
  if (refs.nodesAdd) refs.nodesAdd.addEventListener("click", () => openAddNodeModal());
}
