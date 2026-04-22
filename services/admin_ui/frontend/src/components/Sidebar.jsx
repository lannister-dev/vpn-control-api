import { Icon } from "./Icon.jsx";

const GROUPS = [
  { title: "Мониторинг", items: [
    { id: "overview", label: "Главная", icon: "layout-dashboard" },
    { id: "probes", label: "Probes", icon: "radar" },
    { id: "traffic", label: "Трафик", icon: "bar-chart" },
  ]},
  { title: "Инфраструктура", items: [
    { id: "nodes", label: "Серверы", icon: "server" },
    { id: "routes", label: "Маршруты", icon: "route" },
    { id: "placements", label: "Плейсменты", icon: "map-pin" },
    { id: "transport", label: "Очередь", icon: "activity" },
  ]},
  { title: "Бизнес", items: [
    { id: "users", label: "Пользователи", icon: "users" },
    { id: "plans", label: "Тарифы", icon: "wallet" },
    { id: "subscriptions", label: "Подписки", icon: "key" },
  ]},
  { title: "Система", items: [
    { id: "zones", label: "Зоны", icon: "globe" },
    { id: "admin-users", label: "Админы", icon: "shield" },
    { id: "ops", label: "Операции", icon: "wrench" },
  ]},
];

export function Sidebar({ activeTab, onTab, collapsed, onToggle, onOpenPalette, counts = {}, user, onLogout }) {
  return (
    <aside className="sidebar" data-collapsed={collapsed}>
      <div className="workspace" onClick={onToggle} title={collapsed ? "Развернуть" : "Свернуть"}>
        <div className="workspace-logo">V</div>
        <div className="workspace-text">
          <div className="workspace-name">VPN Control</div>
          <div className="workspace-env">prod · admin</div>
        </div>
      </div>

      <div className="side-search">
        <button className="side-search-btn" onClick={onOpenPalette}>
          <Icon name="search" size={14} />
          <span>Поиск или команда</span>
          <span className="kbd-inline">
            <span className="kbd">⌘</span><span className="kbd">K</span>
          </span>
        </button>
      </div>

      <nav className="side-nav">
        {GROUPS.map((g) => (
          <div key={g.title} className="side-group">
            <div className="side-group-title">{g.title}</div>
            {g.items.map((it) => {
              const count = counts[it.id];
              return (
                <button
                  key={it.id}
                  className="side-btn"
                  data-active={activeTab === it.id}
                  onClick={() => onTab(it.id)}
                >
                  <Icon name={it.icon} size={15} />
                  <span className="side-label">{it.label}</span>
                  {count != null && (
                    <span className="side-count">{count > 999 ? `${(count / 1000).toFixed(1)}k` : count}</span>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="side-footer">
        <div className="user-avatar">{(user?.username || "ad").slice(0, 2).toUpperCase()}</div>
        <div className="side-footer-user">
          <div className="side-footer-name">{user?.username || "admin"}</div>
          <div className="side-footer-status">
            <span className="side-footer-dot" />
            <span>{user?.role || "admin"}</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          <button className="btn btn-ghost btn-icon" title="Настройки" style={{ width: 24, height: 24 }}>
            <Icon name="settings" size={14} />
          </button>
          <button className="btn btn-ghost btn-icon" title="Выход" style={{ width: 24, height: 24 }} onClick={onLogout}>
            <Icon name="log-out" size={14} />
          </button>
        </div>
      </div>
    </aside>
  );
}
