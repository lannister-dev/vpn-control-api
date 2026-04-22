import { Icon } from "./Icon.jsx";

export function Topbar({ theme, onToggleTheme, onLogout }) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="topbar-search">
          <Icon name="search" size={14} />
          <input placeholder="Быстрый поиск (UUID, имя)…" />
          <kbd>⌘K</kbd>
        </div>
      </div>
      <div className="topbar-right">
        <button className="icon-btn" onClick={onToggleTheme} title="Тема">
          <Icon name={theme === "dark" ? "sun" : "moon"} size={15} />
        </button>
        <button className="icon-btn" onClick={onLogout} title="Выход">
          <Icon name="log-out" size={15} />
        </button>
      </div>
    </header>
  );
}
