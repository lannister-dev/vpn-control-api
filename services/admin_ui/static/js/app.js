import { state, refs, $, initRefs, REFRESH_MS, TABLE_LIMIT, TAB_LABELS } from './state.js';
import { esc, toggleSort, fmtDate, nodeNameById, shortId, nodeGeo } from './utils.js';
import { req, runAction, copyToClipboard, checkSession, setupLogout, isAuthenticated, setNotify, setPushLog } from './api.js';
import { notify, pushLog, confirmAction, initTooltips, initCopyButtons, trackFormDirty, setCommandItems, initCommandPalette, openShortcutsModal, hideModal, showModal } from './ui.js';

// Tab modules
import { renderOverview } from './tabs/overview.js';
import { filteredNodes, renderNodes, openNodeDetail, openAddNodeModal, bindNodeEvents, setCallbacks as setNodeCallbacks } from './tabs/nodes.js';
import { filteredRoutes, renderRoutes, openEntryNodeModal, openRouteCreateModal, openRouteEditModal, bindRouteEvents, setCallbacks as setRouteCallbacks } from './tabs/routes.js';
import { filteredPlacements, renderPlacements, renderPlacementMeta, bindPlacementEvents, setCallbacks as setPlacementCallbacks } from './tabs/placements.js';
import { filteredSubscriptions, renderSubscriptions, renderSubPlanFilter, renderSubUserContext, renderSubscriptionDetail, renderSubscriptionDevices, renderSubscriptionCreateResult, bindSubscriptionEvents, setCallbacks as setSubCallbacks } from './tabs/subscriptions.js';
import { loadTransportData, renderTransportKpi, renderTransportNodes, switchTransportSub, bindTransportEvents, setCallbacks as setTransportCallbacks } from './tabs/transport.js';
import { loadProbes, filteredProbes, renderProbes, bindProbeEvents } from './tabs/probes.js';
import { loadUsers, renderUsers, openUserEditModal, navigateToUserSubscriptions, bindUserEvents, setCallbacks as setUserCallbacks } from './tabs/users.js';
import { loadPlans, renderPlanSelect, renderPlans, openPlanEditModal, bindPlanEvents } from './tabs/plans.js';
import { loadZones, renderZones, bindZoneEvents } from './tabs/zones.js';
import { loadTrafficKeys, updateTrafficKpis, loadTrafficHistory, renderTraffic, renderTrafficHistory, renderTrafficChart, bindTrafficEvents, switchTrafficSub } from './tabs/traffic.js';
import { loadNodesTraffic, bindTrafficNodesEvents } from './tabs/traffic-nodes.js';
import { loadAdminUsers, renderAdminUsers, openEditModal, bindAdminUserEvents } from './tabs/admin-users.js';
import { bindOpsEvents, setCallbacks as setOpsCallbacks } from './tabs/ops.js';

// Wire up late-binding callbacks
setNotify(notify);
setPushLog(pushLog);

// Init DOM refs
initRefs();

// Wire up tab module callbacks
setNodeCallbacks(refreshAll, render);
setRouteCallbacks(refreshAll, render);
setPlacementCallbacks(refreshAll, render);
setSubCallbacks(refreshAll, render);
setTransportCallbacks(refreshAll);
setUserCallbacks(refreshAll, render, setTab);
setOpsCallbacks(refreshAll);

// ── Tab switching ──
function setTab(tab) {
  state.activeTab = tab;
  refs.navButtons.forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  Object.keys(refs.panels).forEach((k) => refs.panels[k].classList.toggle("active", k === tab));
  refs.heroTitle.textContent = TAB_LABELS[tab] || "Home";
  refs.crumbs.textContent = "Dashboard \u2022 " + (TAB_LABELS[tab] || tab);
  if (tab === "users" && state.users.length === 0) loadUsers().catch((e) => notify("Ошибка загрузки пользователей: " + e.message, true));
  if (tab === "plans" && state.plans.length === 0) loadPlans().catch((e) => notify("Ошибка загрузки планов: " + e.message, true));
  if (tab === "zones" && state.zones.length === 0) loadZones().catch((e) => notify("Ошибка загрузки зон: " + e.message, true));
  if (tab === "traffic") {
    switchTrafficSub(state.trafficSubTab || "keys");
    if (state.trafficSubTab === "nodes") {
      if (state.trafficNodes.length === 0) loadNodesTraffic().catch((e) => notify("Ошибка загрузки трафика серверов: " + e.message, true));
    } else if (state.trafficKeys.length === 0) {
      loadTrafficKeys().catch((e) => notify("Ошибка загрузки трафика: " + e.message, true));
    }
  }
  if (tab === "admin-users" && state.adminUsers.length === 0) loadAdminUsers().catch((e) => notify("Ошибка загрузки admin users: " + e.message, true));
  if (tab === "transport") loadTransportData().catch((e) => notify("Transport load error: " + e.message, true));
  if (tab === "subscriptions" && state.plans.length === 0) loadPlans().catch(() => {});
  if (tab === "probes" && state.probesAll.length === 0) loadProbes().catch((e) => notify("Ошибка загрузки probe: " + e.message, true));
}

// ── Main render ──
function render() {
  renderOverview(render);
  renderNodes();
  renderRoutes();
  renderPlacements();
  renderSubscriptions();
  renderSubPlanFilter();
}

// ── RefreshAll + Timer ──
async function refreshAll(fullRefresh) {
  if (fullRefresh === undefined) fullRefresh = true;
  if (!isAuthenticated()) { refs.heroStatus.textContent = "Требуется авторизация."; return; }
  state.loading = true;
  const bar = document.createElement("div"); bar.className = "loading-bar"; refs.contentArea.prepend(bar);
  try {
    const [status, readiness] = await Promise.all([req("/api/v1/admin/status"), req("/api/v1/admin/readiness")]);
    state.status = status; state.readiness = readiness;
    const tab = state.activeTab;
    const fetches = [];
    if (fullRefresh || tab === "overview") {
      fetches.push(Promise.all([req("/api/v1/admin/transport/overview"), req("/api/v1/admin/transport/nodes")]).then(([ov, nl]) => {
        state.transportOverview = ov;
        state.transportNodes = nl.items || [];
        if (ov && ov.nats_connected) state.natsLastOnlineAt = Date.now();
      }).catch(() => {}));
    }
    if (fullRefresh || tab === "routes" || tab === "overview") {
      fetches.push(req("/api/v1/routes?limit=500").then((r) => { state.routes = r; }));
      if (!state.transportProfiles.length) fetches.push(req("/api/v1/routes/transport-profiles?limit=200").then((tp) => { state.transportProfiles = tp; }).catch(() => {}));
    }
    if (!state.zones.length) fetches.push(loadZones().catch(() => {}));
    if (fullRefresh || tab === "overview" || tab === "ops") fetches.push(req("/api/v1/probe/reports/recent?limit=60").then((p) => { state.probes = p; }));
    if (tab === "probes" && state.probesAll.length > 0) fetches.push(loadProbes().catch(() => {}));
    if (fullRefresh || tab === "placements") fetches.push(req("/api/v1/placements?limit=500").then((p) => { state.placements = p; }));
    if (tab === "users" && state.users.length > 0) fetches.push(loadUsers().catch(() => {}));
    if (tab === "traffic" && state.trafficKeys.length > 0) fetches.push(loadTrafficKeys().catch(() => {}));
    if (tab === "transport") fetches.push(loadTransportData().catch(() => {}));
    await Promise.all(fetches);
    refs.heroStatus.textContent = `Снимок состояния: ${fmtDate(status.generated_at)}`;
    refs.readinessText.textContent = readiness.ready ? "ready" : "not ready";
    refs.readyDot.classList.toggle("ok", !!readiness.ready);
    refs.lastSync.textContent = new Date().toLocaleString();
    if (state.selectedNode && status.nodes) { const cur = status.nodes.find((n) => n.id === state.selectedNode.id); if (cur) state.selectedNode = cur; }
    render();
  } finally { state.loading = false; bar.remove(); }
}

function updateTimer() {
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
  const interval = Number(refs.refreshInterval.value || REFRESH_MS);
  if (refs.live.checked) state.timer = setInterval(() => refreshAll(false).catch((e) => notify(`Ошибка обновления: ${e.message}`, true)), interval);
}

// ── Command palette items ──
setCommandItems([
  { label: "Серверы", icon: "\uD83D\uDDA5", section: "Навигация", action: () => setTab("nodes") },
  { label: "Transport", icon: "\uD83D\uDE80", section: "Навигация", action: () => setTab("transport") },
  { label: "Маршруты", icon: "\uD83D\uDEE3", section: "Навигация", action: () => setTab("routes") },
  { label: "Плейсменты", icon: "\uD83D\uDCCD", section: "Навигация", action: () => setTab("placements") },
  { label: "Пользователи", icon: "\uD83D\uDC65", section: "Навигация", action: () => setTab("users") },
  { label: "Тарифы", icon: "\uD83D\uDCB0", section: "Навигация", action: () => setTab("plans") },
  { label: "Зоны", icon: "\uD83C\uDF0D", section: "Навигация", action: () => setTab("zones") },
  { label: "Подписки", icon: "\uD83D\uDD10", section: "Навигация", action: () => setTab("subscriptions") },
  { label: "Трафик · Ключи", icon: "\uD83D\uDCCA", section: "Навигация", action: () => { setTab("traffic"); switchTrafficSub("keys"); } },
  { label: "Трафик · Сервера", icon: "\uD83D\uDCE1", section: "Навигация", action: () => { setTab("traffic"); switchTrafficSub("nodes"); } },
  { label: "Админы", icon: "\u2699", section: "Навигация", action: () => setTab("admin-users") },
  { label: "Проверки", icon: "\uD83D\uDD0D", section: "Навигация", action: () => setTab("probes") },
]);
initCommandPalette();

// ── Event listeners ──
refs.navButtons.forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
if (refs.refreshAll) refs.refreshAll.addEventListener("click", () => refreshAll(true).catch((e) => notify(`Ошибка обновления: ${e.message}`, true)));
refs.live.addEventListener("change", updateTimer);
refs.refreshInterval.addEventListener("change", updateTimer);

// Filter change handlers trigger re-render
[refs.nodesSearch, refs.nodesHealth, refs.nodesState, refs.routesStatus, refs.routesSearch, refs.placementsNode, refs.placementsKey, refs.placementsDesired, refs.placementsApplied].forEach((el) => {
  el.addEventListener("input", render); el.addEventListener("change", render);
});

// Bind all tab module events
bindNodeEvents();
bindRouteEvents();
bindPlacementEvents();
bindSubscriptionEvents(setTab, render);
bindTransportEvents();
bindProbeEvents();
bindUserEvents();
bindPlanEvents();
bindZoneEvents();
bindTrafficEvents();
bindTrafficNodesEvents();
bindAdminUserEvents();
bindOpsEvents();
setupLogout();

// Dashboard delegated click: quick actions + priority issues
const tabOverviewEl = document.getElementById("tab-overview");
if (tabOverviewEl) {
  tabOverviewEl.addEventListener("click", (ev) => {
    const target = ev.target;
    if (!(target instanceof HTMLElement)) return;

    const qa = target.closest(".dash-quick-btn");
    if (qa && qa.dataset.qa) {
      const act = qa.dataset.qa;
      if (act === "add-node") openAddNodeModal();
      else if (act === "add-route") openRouteCreateModal();
      else if (act === "add-plan") { setTab("plans"); setTimeout(() => document.getElementById("plans-create-btn")?.click(), 0); }
      else if (act === "add-user") { setTab("users"); setTimeout(() => document.getElementById("users-create-btn")?.click(), 0); }
      else if (act === "ops") setTab("ops");
      return;
    }

    const issueBtn = target.closest(".dash-issue");
    if (issueBtn && issueBtn.dataset.idx != null) {
      const host = document.getElementById("dash-issues");
      const issues = host && host._issues;
      if (!issues) return;
      const item = issues[Number(issueBtn.dataset.idx)];
      if (!item || !item.target) return;
      const t = item.target;
      if (t.type === "node" && t.id) {
        setTab("nodes");
        setTimeout(() => openNodeDetail(t.id), 0);
      } else if (t.type === "routes") {
        setTab("routes");
      } else if (t.type === "probes") {
        setTab("probes");
      } else if (t.type === "transport") {
        setTab("transport");
      }
      return;
    }
  });
}

// Global delegated click: UUID copy + sortable headers + row selection
document.addEventListener("click", (ev) => {
  const el = ev.target; if (!(el instanceof HTMLElement)) return;
  const uuid = el.closest(".uuid");
  if (uuid && uuid.dataset.copy) { copyToClipboard(uuid.dataset.copy); return; }
  const th = el.closest("th.sortable");
  if (th && th.dataset.sortKey && th.dataset.sortTable) { toggleSort(th.dataset.sortTable, th.dataset.sortKey); render(); return; }
  const auEdit = el.closest(".au-edit-btn");
  if (auEdit) { openEditModal(auEdit.dataset.uid, auEdit.dataset.uname, auEdit.dataset.urole, auEdit.dataset.uactive === "true"); return; }
  const row = el.closest("tr[data-focusable]");
  if (row) { row.classList.toggle("selected"); return; }
});

// Keyboard navigation in tables
document.addEventListener("keydown", (ev) => {
  if (ev.key === "ArrowUp" || ev.key === "ArrowDown") {
    const row = ev.target.closest("tr[data-focusable]");
    if (!row) return;
    ev.preventDefault();
    const allRows = Array.from(row.parentElement.querySelectorAll("tr[data-focusable]"));
    const idx = allRows.indexOf(row);
    const nextIdx = ev.key === "ArrowDown" ? Math.min(idx + 1, allRows.length - 1) : Math.max(idx - 1, 0);
    if (allRows[nextIdx]) allRows[nextIdx].focus();
  }
});

// Global keyboard shortcuts
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    const sidebar = document.querySelector(".sidebar");
    if (sidebar && sidebar.classList.contains("mobile-open")) {
      closeMobileSidebar();
      e.preventDefault();
    }
  }
});

// Mobile sidebar
function openMobileSidebar() {
  const sidebar = document.querySelector(".sidebar");
  const backdrop = $("sidebar-backdrop");
  if (sidebar) sidebar.classList.add("mobile-open");
  if (backdrop) backdrop.classList.add("active");
}
function closeMobileSidebar() {
  const sidebar = document.querySelector(".sidebar");
  const backdrop = $("sidebar-backdrop");
  if (sidebar) sidebar.classList.remove("mobile-open");
  if (backdrop) backdrop.classList.remove("active");
}
const sidebarToggle = $("sidebar-toggle");
const sidebarBackdrop = $("sidebar-backdrop");
if (sidebarToggle) {
  sidebarToggle.addEventListener("click", () => {
    const sidebar = document.querySelector(".sidebar");
    if (sidebar && sidebar.classList.contains("mobile-open")) closeMobileSidebar();
    else openMobileSidebar();
  });
}
if (sidebarBackdrop) sidebarBackdrop.addEventListener("click", closeMobileSidebar);
document.querySelectorAll(".nav button[data-tab]").forEach(btn => {
  btn.addEventListener("click", () => { if (window.innerWidth < 900) closeMobileSidebar(); });
});

// ── Init ──
pushLog("Панель", "инициализирована", false);
updateTimer();
initTooltips();
initCopyButtons();
document.querySelectorAll("form").forEach(trackFormDirty);

(async () => {
  const hasSession = await checkSession();
  if (hasSession) { refreshAll().catch((e) => notify(`Ошибка начальной загрузки: ${e.message}`, true)); }
  else { window.location.href = "/api/v1/auth/admin/login"; }
})();
