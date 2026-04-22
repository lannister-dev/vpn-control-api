import { useState, useEffect } from "react";
import { Sidebar } from "./components/Sidebar.jsx";
import { Topbar } from "./components/Topbar.jsx";
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

export default function App() {
  const [tab, setTab] = useState(() => {
    try { return JSON.parse(localStorage.getItem("vpn-ctrl-state") || "{}").tab || "overview"; } catch { return "overview"; }
  });
  const [theme, setTheme] = useState(document.documentElement.getAttribute("data-theme") || "dark");

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("vpn-ctrl-state") || "{}");
      localStorage.setItem("vpn-ctrl-state", JSON.stringify({ ...saved, tab, theme }));
    } catch { /* ignore */ }
    document.documentElement.setAttribute("data-theme", theme);
  }, [tab, theme]);

  const Page = PAGES[tab] || PAGES.overview;

  return (
    <div className="app-shell">
      <Sidebar activeTab={tab} onTab={setTab} />
      <div className="app-main">
        <Topbar
          theme={theme}
          onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          onLogout={() => (window.location.href = "/api/v1/auth/admin/logout")}
        />
        <div className="app-content">
          <Page />
        </div>
      </div>
    </div>
  );
}
