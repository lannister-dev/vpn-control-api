import { useState, useEffect, useMemo } from "react";
import { api } from "./api/client.js";
import { useQuery } from "./hooks/useQuery.js";
import { Sidebar } from "./components/Sidebar.jsx";
import { Topbar } from "./components/Topbar.jsx";
import { Palette } from "./components/Palette.jsx";
import { NodeDrawer } from "./components/NodeDrawer.jsx";
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
  zones: ["Workspace", "Система", "Зоны"],
  "admin-users": ["Workspace", "Система", "Админы"],
  ops: ["Workspace", "Система", "Операции"],
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
  const [tab, setTab] = useState(() => {
    try { return JSON.parse(localStorage.getItem("vpn-ctrl-state") || "{}").tab || "overview"; } catch { return "overview"; }
  });
  const [theme, setTheme] = useState(document.documentElement.getAttribute("data-theme") || "dark");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [drawerNode, setDrawerNode] = useState(null);
  const [collapsed, setCollapsed] = useState(() => {
    try { return !!JSON.parse(localStorage.getItem("vpn-ctrl-state") || "{}").collapsed; } catch { return false; }
  });

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("vpn-ctrl-state") || "{}");
      localStorage.setItem("vpn-ctrl-state", JSON.stringify({ ...saved, tab, theme, collapsed }));
    } catch { /* ignore */ }
    document.documentElement.setAttribute("data-theme", theme);
  }, [tab, theme, collapsed]);

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

  const status = useQuery(() => api.get("/admin/status"), { interval: 20000 });
  const routesData = useQuery(() => api.get("/routes?limit=500"), { interval: 30000 });
  const me = useQuery(() => api.get("/auth/admin/me").catch(() => null), { interval: 0 });

  const counts = useMemo(() => {
    const out = {};
    if (status.data?.totals?.nodes_total != null) out.nodes = status.data.totals.nodes_total;
    if (routesData.data) out.routes = routesData.data.length;
    return out;
  }, [status.data, routesData.data]);

  const lastSync = relSync(status.data?.generated_at);

  const Page = PAGES[tab] || PAGES.overview;
  const crumbs = CRUMBS[tab] || ["Workspace"];

  return (
    <div className="app-shell">
      <Sidebar
        activeTab={tab}
        onTab={setTab}
        collapsed={collapsed}
        onToggle={() => setCollapsed((v) => !v)}
        onOpenPalette={() => setPaletteOpen(true)}
        counts={counts}
        user={me.data}
      />
      <div className="app-main">
        <Topbar
          crumbs={crumbs}
          theme={theme}
          onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          onOpenPalette={() => setPaletteOpen(true)}
          onRefresh={() => { status.refetch(); routesData.refetch(); }}
          lastSync={lastSync}
          notifCount={0}
        />
        <div className="app-content">
          <Page onGoto={setTab} onOpenNode={setDrawerNode} />
        </div>
      </div>
      <Palette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onSelect={(item) => { setTab(item.id); setPaletteOpen(false); }}
      />
      {drawerNode && <NodeDrawer node={drawerNode} onClose={() => setDrawerNode(null)} />}
    </div>
  );
}
