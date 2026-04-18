export const REFRESH_MS = 15000;
export const TABLE_LIMIT = 500;
export const TAB_LABELS = { overview: "Home", nodes: "Серверы", transport: "Transport", routes: "Маршруты", placements: "Плейсменты", users: "Пользователи", plans: "Тарифы", subscriptions: "Подписки", traffic: "Трафик", "traffic-nodes": "Трафик · Серверы", "admin-users": "Админы", probes: "Probes", ops: "Ops" };

export const $ = (id) => document.getElementById(id);

export const state = {
  timer: null, selectedNode: null, status: null, readiness: null,
  routes: [], placements: [], probes: [], subscriptions: [], subscriptionDevices: [],
  logs: [], activeTab: "overview", loading: false,
  users: [], usersTotal: 0, usersLimit: 50, usersOffset: 0,
  plans: [],
  trafficKeys: [], trafficTotal: 0, trafficLimit: 50, trafficOffset: 0,
  trafficHistory: [], trafficHistoryTotal: 0, trafficHistoryLimit: 50, trafficHistoryOffset: 0,
  trafficHistoryKeyId: null, trafficHistoryKeyData: null,
  trafficNodesPeriod: "24h", trafficNodesRole: "",
  trafficNodes: [], trafficPairs: [],
  trafficNodeSelectedId: null, trafficNodeSelectedSide: "auto",
  trafficNodeTimeseries: null,
  adminUsers: [], adminUsersTotal: 0,
  transportOverview: null, transportNodes: [], transportNodeDetail: null,
  outboxItems: [], outboxTotal: 0, outboxOffset: 0,
  eventsItems: [], eventsTotal: 0, eventsOffset: 0,
  transportSubTab: "nodes",
  probesAll: [], probesTotal: 0, probesLimit: 30, probesOffset: 0,
  subscriptionContext: null,
  selectedSubscription: null,
  subCreateOpen: false,
  transportProfiles: [],
};

export const refs = {};

export function initRefs() {
  refs.refreshAll = $("refresh-all");
  refs.live = $("live-refresh");
  refs.refreshInterval = $("refresh-interval");
  refs.sessionUserInfo = $("session-user-info");
  refs.sessionUsername = $("session-username");
  refs.sessionRole = $("session-role");
  refs.btnLogout = $("btn-logout");
  refs.readyDot = $("ready-dot");
  refs.readinessText = $("readiness-text");
  refs.lastSync = $("last-sync");
  refs.heroStatus = $("hero-status");
  refs.heroTitle = $("hero-title");
  refs.crumbs = $("crumbs");
  refs.contentArea = $("content-area");
  refs.kpiNodes = $("kpi-nodes");
  refs.kpiHealthy = $("kpi-healthy");
  refs.kpiDraining = $("kpi-draining");
  refs.kpiPlacements = $("kpi-placements");
  refs.kpiRoutes = $("kpi-routes");
  refs.kpiProbeFail = $("kpi-probe-fail");
  refs.kpiTrafficKeys = $("kpi-traffic-keys");
  refs.kpiTrafficRevoked = $("kpi-traffic-revoked");
  refs.kpiTrafficTotal = $("kpi-traffic-total");
  refs.readinessList = $("readiness-list");
  refs.routeHealthList = $("route-health-list");
  refs.probeFailList = $("probe-fail-list");
  refs.nodeAlertList = $("node-alert-list");
  refs.selectedNodeCard = $("selected-node-card");
  refs.actionLog = $("action-log");
  refs.nodeConfigModal = $("node-config-modal");
  refs.nodesHead = $("nodes-head");
  refs.nodesBody = $("nodes-body");
  refs.routesHead = $("routes-head");
  refs.routesBody = $("routes-body");
  refs.placementsBody = $("placements-body");
  refs.placementsMeta = $("placements-meta");
  refs.subsHead = $("subs-head");
  refs.subsBody = $("subs-body");
  refs.subCreateResult = $("sub-create-result");
  refs.subDetailContainer = $("sub-detail-container");
  refs.subDevicesContainer = $("sub-devices-container");
  refs.subUserContext = $("sub-user-context");
  refs.subFilterUser = $("sub-filter-user");
  refs.subFilterPlan = $("sub-filter-plan");
  refs.subFilterActive = $("sub-filter-active");
  refs.subSearchBtn = $("sub-search-btn");
  refs.subClearBtn = $("sub-clear-btn");
  refs.subCreateTrigger = $("sub-create-trigger");
  refs.subCreateContent = $("sub-create-content");
  refs.subCreateArrow = $("sub-create-arrow");
  refs.nodesSearch = $("nodes-search");
  refs.nodesHealth = $("nodes-health");
  refs.nodesState = $("nodes-state");
  refs.nodesClear = $("nodes-clear");
  refs.nodesReload = $("nodes-reload");
  refs.nodesAdd = $("nodes-add");
  refs.addNodeModal = $("add-node-modal");
  refs.routesStatus = $("routes-status");
  refs.routesSearch = $("routes-search");
  refs.routesReload = $("routes-reload");
  refs.placementsNode = $("placements-node");
  refs.placementsKey = $("placements-key");
  refs.placementsDesired = $("placements-desired");
  refs.placementsApplied = $("placements-applied");
  refs.placementsReload = $("placements-reload");
  refs.formSubCreate = $("form-sub-create");
  refs.probesStatus = $("probes-status");
  refs.probesKind = $("probes-kind");
  refs.probesSource = $("probes-source");
  refs.probesSearch = $("probes-search");
  refs.probesReload = $("probes-reload");
  refs.probesHead = $("probes-head");
  refs.probesBody = $("probes-body");
  refs.probesPagination = $("probes-pagination");
  refs.probesMeta = $("probes-meta");
  refs.probesSummary = $("probes-summary");
  refs.probesNodeSummary = $("probes-node-summary");
  refs.formMigrate = $("form-migrate");
  refs.formProbeAuto = $("form-probe-auto");
  refs.formRouteHealth = $("form-route-health");
  refs.formProbeManual = $("form-probe-manual");
  refs.btnWarmup = $("btn-warmup");
  refs.btnCleanupProbe = $("btn-cleanup-probe");
  refs.usersSearch = $("users-search");
  refs.usersStatus = $("users-status");
  refs.usersReload = $("users-reload");
  refs.usersCreateBtn = $("users-create-btn");
  refs.usersHead = $("users-head");
  refs.usersBody = $("users-body");
  refs.usersPagination = $("users-pagination");
  refs.plansReload = $("plans-reload");
  refs.plansCreateBtn = $("plans-create-btn");
  refs.plansHead = $("plans-head");
  refs.plansBody = $("plans-body");
  refs.trafficSearch = $("traffic-search");
  refs.trafficUserId = $("traffic-user-id");
  refs.trafficRevoked = $("traffic-revoked");
  refs.trafficReload = $("traffic-reload");
  refs.trafficHead = $("traffic-head");
  refs.trafficBody = $("traffic-body");
  refs.trafficMeta = $("traffic-meta");
  refs.trafficPagination = $("traffic-pagination");
  refs.trafficHistorySection = $("traffic-history-section");
  refs.trafficHistoryKeyLabel = $("traffic-history-key-label");
  refs.trafficHistoryKeyInfo = $("traffic-history-key-info");
  refs.trafficHistoryFrom = $("traffic-history-from");
  refs.trafficHistoryTo = $("traffic-history-to");
  refs.trafficHistoryReload = $("traffic-history-reload");
  refs.trafficHistoryClose = $("traffic-history-close");
  refs.trafficHistoryBody = $("traffic-history-body");
  refs.trafficHistoryPagination = $("traffic-history-pagination");
  refs.trafficChartContainer = $("traffic-chart-container");
  refs.trafficChart = $("traffic-chart");
  refs.trafficNodesPeriod = $("traffic-nodes-period");
  refs.trafficNodesRole = $("traffic-nodes-role");
  refs.trafficNodesReload = $("traffic-nodes-reload");
  refs.trafficNodesMeta = $("traffic-nodes-meta");
  refs.trafficNodesBody = $("traffic-nodes-body");
  refs.trafficPairsBody = $("traffic-pairs-body");
  refs.trafficNodeDetailSection = $("traffic-node-detail-section");
  refs.trafficNodeDetailLabel = $("traffic-node-detail-label");
  refs.trafficNodeDetailClose = $("traffic-node-detail-close");
  refs.trafficNodeSide = $("traffic-node-side");
  refs.trafficNodeChartContainer = $("traffic-node-chart-container");
  refs.trafficNodeChart = $("traffic-node-chart");
  refs.trafficNodeTimeseriesMeta = $("traffic-node-timeseries-meta");
  refs.toastContainer = $("toast-container");
  refs.confirmModal = $("confirm-modal");
  refs.navButtons = Array.from(document.querySelectorAll(".nav button[data-tab]"));
  refs.panels = {
    overview: $("tab-overview"), nodes: $("tab-nodes"), transport: $("tab-transport"),
    routes: $("tab-routes"), placements: $("tab-placements"), users: $("tab-users"),
    plans: $("tab-plans"), subscriptions: $("tab-subscriptions"), traffic: $("tab-traffic"),
    "traffic-nodes": $("tab-traffic-nodes"),
    "admin-users": $("tab-admin-users"), probes: $("tab-probes"), ops: $("tab-ops"),
  };
}
