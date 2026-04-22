import { Icon } from "./Icon.jsx";

export function Topbar({ theme, onToggleTheme, onLogout, onOpenPalette }) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <button type="button" className="topbar-search" onClick={onOpenPalette} style={{ width: "100%", textAlign: "left", cursor: "pointer" }}>
          <Icon name="search" size={14} />
          <span style={{ flex: 1, color: "var(--text-muted)", fontSize: 13 }}>Быстрый поиск (⌘K)</span>
          <kbd>⌘K</kbd>
        </button>
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
