// REPLACE frontend/src/App.jsx with this file.
// Adds tickets / support-templates / broadcasts routing, palette quick-actions,
// and exposes `ticketsCount` to Sidebar (unanswered count).
import { useState, useEffect, useMemo } from "react";
import { api } from "./api/client.js";
import { useQuery } from "./hooks/useQuery.js";
import { useTicketNotifications } from "./hooks/useTicketNotifications.js";
import { useUserNotifications } from "./hooks/useUserNotifications.js";
import { Sidebar } from "./components/Sidebar.jsx";
import { Topbar } from "./components/Topbar.jsx";
import { Palette } from "./components/Palette.jsx";
import { NodeDrawer } from "./components/NodeDrawer.jsx";
import { AlertsDrawer } from "./components/AlertsDrawer.jsx";
import { LoginPage } from "./pages/Login.jsx";
import { OverviewPage } from "./pages/Overview.jsx";
import { NodesPage } from "./pages/Nodes.jsx";
import { RoutesPage } from "./pages/Routes.jsx";
import { PlacementsPage } from "./pages/Placements.jsx";
import { TransportPage } from "./pages/Transport.jsx";
import { ProbesPage } from "./pages/Probes.jsx";
import { TrafficPage } from "./pages/Traffic.jsx";
import { UsersPage } from "./pages/Users.jsx";
import { PlansPage } from "./pages/Plans.jsx";
import { SubscriptionsPage } from "./pages/Subscriptions.jsx";
import { ZonesPage } from "./pages/Zones.jsx";
import { AdminUsersPage } from "./pages/AdminUsers.jsx";
import { OpsPage } from "./pages/Ops.jsx";
import { SettingsPage } from "./pages/Settings.jsx";
import { TicketsPage } from "./pages/Tickets.jsx";
import { SupportTemplatesPage } from "./pages/SupportTemplates.jsx";
import { BroadcastsPage } from "./pages/Broadcasts.jsx";

const PAGES = {
  overview: OverviewPage,
  nodes: NodesPage,
  routes: RoutesPage,
  placements: PlacementsPage,
  transport: TransportPage,
  probes: ProbesPage,
  traffic: TrafficPage,
  users: UsersPage,
  plans: PlansPage,
  subscriptions: SubscriptionsPage,
  zones: ZonesPage,
  "admin-users": AdminUsersPage,
  ops: OpsPage,
  settings: SettingsPage,
  tickets: TicketsPage,
  "support-templates": SupportTemplatesPage,
  broadcasts: BroadcastsPage,
};

const CRUMBS = {
  overview: ["Workspace", "Главная"],
  nodes: ["Workspace", "Инфраструктура", "Серверы"],
  routes: ["Workspace", "Инфраструктура", "Маршруты"],
  placements: ["Workspace", "Инфраструктура", "Плейсменты"],
  transport: ["Workspace", "Инфраструктура", "Очередь"],
  probes: ["Workspace", "Мониторинг", "Probes"],
  traffic: ["Workspace", "Мониторинг", "Трафик"],
  users: ["Workspace", "Бизнес", "Пользователи"],
  plans: ["Workspace", "Бизнес", "Тарифы"],
  subscriptions: ["Workspace", "Бизнес", "Подписки"],
  tickets: ["Workspace", "Поддержка", "Тикеты"],
  "support-templates": ["Workspace", "Поддержка", "Шаблоны"],
  broadcasts: ["Workspace", "Поддержка", "Рассылки"],
  zones: ["Workspace", "Система", "Зоны"],
  "admin-users": ["Workspace", "Система", "Админы"],
  ops: ["Workspace", "Система", "Операции"],
  settings: ["Workspace", "Система", "Настройки"],
};

function relSync(iso) {
  if (!iso) return "—";
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}с назад`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}м назад`;
  return `${Math.floor(m / 60)}ч назад`;
}

export default function App() {
  const [theme, setTheme] = useState(document.documentElement.getAttribute("data-theme") || "dark");
  const [authState, setAuthState] = useState("checking");
  const [me, setMe] = useState(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      const saved = JSON.parse(localStorage.getItem("vpn-ctrl-state") || "{}");
      localStorage.setItem("vpn-ctrl-state", JSON.stringify({ ...saved, theme }));
    } catch { /* ignore */ }
  }, [theme]);

  const checkAuth = async () => {
    try {
      const data = await api.get("/auth/admin/session");
      if (data?.authenticated) {
        setMe({ username: data.username, role: data.role });
        setAuthState("authed");
      } else {
        setAuthState("guest");
      }
    } catch {
      setAuthState("guest");
    }
  };

  useEffect(() => { checkAuth(); }, []);

  if (authState === "checking") {
    return <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>Загрузка…</div>;
  }

  if (authState === "guest") {
    return (
      <LoginPage
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        onSuccess={() => { setAuthState("checking"); checkAuth(); }}
      />
    );
  }

  return <AuthedApp theme={theme} setTheme={setTheme} me={me} onLogout={() => setAuthState("guest")} />;
}

function AuthedApp({ theme, setTheme, me, onLogout }) {
  const [tab, setTab] = useState(() => {
    try { return JSON.parse(localStorage.getItem("vpn-ctrl-state") || "{}").tab || "overview"; } catch { return "overview"; }
  });
  const [pendingAction, setPendingAction] = useState(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [drawerNode, setDrawerNode] = useState(null);
  const [drawerOpts, setDrawerOpts] = useState(null);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  const openNode = (node, opts) => {
    setDrawerNode(node || null);
    setDrawerOpts(node ? (opts || null) : null);
  };

  const goto = (nextTab, opts) => {
    setTab(nextTab);
    setPendingAction(opts?.action || null);
  };
  const [collapsed, setCollapsed] = useState(() => {
    try { return !!JSON.parse(localStorage.getItem("vpn-ctrl-state") || "{}").collapsed; } catch { return false; }
  });

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("vpn-ctrl-state") || "{}");
      localStorage.setItem("vpn-ctrl-state", JSON.stringify({ ...saved, tab, collapsed }));
    } catch { /* ignore */ }
  }, [tab, collapsed]);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useTicketNotifications(setTab);
  useUserNotifications(setTab);

  const status = useQuery(() => api.get("/admin/status"), { interval: 20000 });
  const routesData = useQuery(() => api.get("/routes?limit=500"), { interval: 30000 });
  const usersData = useQuery(() => api.get("/users?limit=1").catch(() => null), { interval: 60000 });
  const subsStats = useQuery(() => api.get("/subscriptions/stats").catch(() => null), { interval: 60000 });
  const alertsCount = useQuery(() => api.get("/admin/alerts/unread-count").catch(() => null), { interval: 15000 });
  // Tickets unanswered count (graceful 404 if endpoint not deployed)
  const ticketsStats = useQuery(
    () => api.get("/support/tickets/stats").catch(() => null),
    { interval: 30000 },
  );

  const counts = useMemo(() => {
    const out = {};
    if (status.data?.totals?.nodes_total != null) out.nodes = status.data.totals.nodes_total;
    if (routesData.data) out.routes = routesData.data.length;
    if (usersData.data?.total != null) out.users = usersData.data.total;
    if (subsStats.data?.active != null) out.subscriptions = subsStats.data.active;
    if (ticketsStats.data?.open != null) out.tickets = ticketsStats.data.open;
    return out;
  }, [status.data, routesData.data, usersData.data, subsStats.data, ticketsStats.data]);

  const lastSync = relSync(status.data?.generated_at);
  const Page = PAGES[tab] || PAGES.overview;
  const crumbs = CRUMBS[tab] || ["Workspace"];

  const logout = async () => {
    try { await api.post("/auth/admin/logout"); } catch { /* ignore */ }
    onLogout();
  };

  const onPaletteSelect = (item) => {
    setPaletteOpen(false);
    if (item.action) {
      setTab(item.id);
      setPendingAction(item.action);
    } else {
      setTab(item.id);
    }
  };

  return (
    <div className="app-shell">
      <Sidebar
        activeTab={tab}
        onTab={setTab}
        collapsed={collapsed}
        onToggle={() => setCollapsed((v) => !v)}
        onOpenPalette={() => setPaletteOpen(true)}
        counts={counts}
        user={me}
        onLogout={logout}
        mobileOpen={mobileSidebarOpen}
        onMobileClose={() => setMobileSidebarOpen(false)}
      />
      <div className="app-main">
        <Topbar
          crumbs={crumbs}
          theme={theme}
          onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          onOpenPalette={() => setPaletteOpen(true)}
          onRefresh={() => { status.refetch(); routesData.refetch(); alertsCount.refetch(); }}
          lastSync={lastSync}
          notifCount={alertsCount.data?.unread || 0}
          onOpenAlerts={() => setAlertsOpen(true)}
          onOpenMobileSidebar={() => setMobileSidebarOpen(true)}
        />
        <div className="app-content">
          <Page
            onGoto={goto}
            onOpenNode={openNode}
            initialAction={pendingAction}
            onActionConsumed={() => setPendingAction(null)}
          />
        </div>
      </div>
      <Palette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onSelect={onPaletteSelect}
      />
      {drawerNode && (
        <NodeDrawer
          node={drawerNode}
          initialTab={drawerOpts?.initialTab}
          focusRouteId={drawerOpts?.focusRouteId}
          onClose={() => { setDrawerNode(null); setDrawerOpts(null); }}
          onGoto={goto}
          onOpenNode={openNode}
        />
      )}
      {alertsOpen && (
        <AlertsDrawer
          onClose={() => setAlertsOpen(false)}
          onChanged={() => alertsCount.refetch()}
        />
      )}
    </div>
  );
}
