import { useState, useEffect } from "react";
import { Sidebar } from "./components/Sidebar.jsx";
import { Topbar } from "./components/Topbar.jsx";
import { OverviewPage } from "./pages/Overview.jsx";
import { NodesPage } from "./pages/Nodes.jsx";
import { Placeholder } from "./pages/Placeholder.jsx";

const PAGES = {
  overview: OverviewPage,
  nodes: NodesPage,
  routes: () => <Placeholder title="Маршруты" hint="Переносим таблицу + топологию из старой панели." />,
  placements: () => <Placeholder title="Плейсменты" />,
  transport: () => <Placeholder title="Очередь" />,
  probes: () => <Placeholder title="Probes" />,
  traffic: () => <Placeholder title="Трафик" />,
  users: () => <Placeholder title="Пользователи" />,
  plans: () => <Placeholder title="Тарифы" />,
  subscriptions: () => <Placeholder title="Подписки" />,
  zones: () => <Placeholder title="Зоны" />,
  "admin-users": () => <Placeholder title="Админы" />,
  ops: () => <Placeholder title="Операции" />,
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
