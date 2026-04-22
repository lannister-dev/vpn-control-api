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
    { id: "admin-users", label: "Админы", icon: "settings" },
    { id: "ops", label: "Операции", icon: "shield-check" },
  ]},
];

export function Sidebar({ activeTab, onTab }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <Icon name="shield-check" size={18} />
        <span>VPN Control</span>
      </div>
      <nav className="sidebar-nav">
        {GROUPS.map((group) => (
          <div key={group.title} className="sidebar-group">
            <div className="sidebar-group-title">{group.title}</div>
            {group.items.map((item) => (
              <button
                key={item.id}
                className={"sidebar-item" + (activeTab === item.id ? " active" : "")}
                onClick={() => onTab(item.id)}
              >
                <Icon name={item.icon} size={15} />
                <span>{item.label}</span>
              </button>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
