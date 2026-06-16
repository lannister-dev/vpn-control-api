import { useState, useEffect } from "react";
import { Icon } from "./Icon.jsx";

const COLLAPSE_KEY = "sidebar.collapsedGroups";

function loadCollapsed() {
  try { return new Set(JSON.parse(localStorage.getItem(COLLAPSE_KEY) || "[]")); }
  catch { return new Set(); }
}

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
  { title: "Финансы", items: [
    { id: "fin-overview", label: "Обзор / P&L", icon: "pie-chart" },
    { id: "fin-income", label: "Доходы", icon: "trending-up" },
    { id: "fin-expenses", label: "Расходы", icon: "receipt" },
    { id: "fin-metrics", label: "Метрики", icon: "activity" },
    { id: "fin-rates", label: "Комиссии", icon: "percent" },
  ]},
  { title: "Бизнес", items: [
    { id: "users", label: "Пользователи", icon: "users" },
    { id: "plans", label: "Тарифы", icon: "wallet" },
    { id: "subscriptions", label: "Подписки", icon: "key" },
    { id: "promo", label: "Промокоды", icon: "tag" },
  ]},
  { title: "Поддержка", items: [
    { id: "tickets", label: "Тикеты", icon: "message-square", attentionKey: "unanswered" },
    { id: "support-templates", label: "Шаблоны", icon: "file-text" },
    { id: "broadcasts", label: "Рассылки", icon: "send" },
  ]},
  { title: "Система", items: [
    { id: "zones", label: "Зоны", icon: "globe" },
    { id: "admin-users", label: "Админы", icon: "shield" },
    { id: "ops", label: "Операции", icon: "wrench" },
    { id: "settings", label: "Настройки", icon: "sliders" },
  ]},
];

export function Sidebar({ activeTab, onTab, collapsed, onToggle, onOpenPalette, counts = {}, user, onLogout, mobileOpen, onMobileClose }) {
  const [collapsedGroups, setCollapsedGroups] = useState(loadCollapsed);
  const pick = (id) => {
    onTab(id);
    onMobileClose?.();
  };
  const persist = (next) => {
    localStorage.setItem(COLLAPSE_KEY, JSON.stringify([...next]));
    return next;
  };
  const toggleGroup = (title) => setCollapsedGroups((prev) => {
    const next = new Set(prev);
    if (next.has(title)) next.delete(title); else next.add(title);
    return persist(next);
  });
  useEffect(() => {
    const activeGroup = GROUPS.find((g) => g.items.some((it) => it.id === activeTab));
    if (!activeGroup) return;
    setCollapsedGroups((prev) => {
      if (!prev.has(activeGroup.title)) return prev;
      const next = new Set(prev);
      next.delete(activeGroup.title);
      return persist(next);
    });
  }, [activeTab]);
  return (
    <>
      {mobileOpen && <div className="sidebar-backdrop" onClick={onMobileClose} />}
      <aside className="sidebar" data-collapsed={collapsed} data-mobile-open={mobileOpen || undefined}>
      <div className="workspace" onClick={onToggle} title={collapsed ? "Развернуть" : "Свернуть"}>
        <div className="workspace-logo" style={{ background: "#0a0a0a", color: "oklch(0.72 0.19 48)" }}>R</div>
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
        {GROUPS.map((g) => {
          const open = collapsed || !collapsedGroups.has(g.title);
          return (
          <div key={g.title} className="side-group" data-open={open || undefined}>
            {!collapsed && (
              <button
                className="side-group-title"
                onClick={() => toggleGroup(g.title)}
                aria-expanded={open}
              >
                <span>{g.title}</span>
                <Icon className="side-group-chevron" name="chevron-right" size={12} />
              </button>
            )}
            {open && g.items.map((it) => {
              const count = counts[it.id];
              const isAttention = it.attentionKey && count != null && count > 0;
              return (
                <button
                  key={it.id}
                  className="side-btn"
                  data-active={activeTab === it.id}
                  onClick={() => pick(it.id)}
                >
                  <Icon name={it.icon} size={15} />
                  <span className="side-label">{it.label}</span>
                  {count != null && count > 0 && (
                    <span
                      className="side-count"
                      data-attention={isAttention || undefined}
                      title={isAttention ? "Без ответа" : undefined}
                    >
                      {count > 999 ? `${(count / 1000).toFixed(1)}k` : count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
          );
        })}
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
        <button className="btn btn-ghost btn-icon" title="Настройки" style={{ width: 24, height: 24 }}>
          <Icon name="settings" size={14} />
        </button>
        <button className="btn btn-ghost btn-icon" title="Выход" style={{ width: 24, height: 24 }} onClick={onLogout}>
          <Icon name="log-out" size={14} />
        </button>
      </div>
      </aside>
    </>
  );
}
