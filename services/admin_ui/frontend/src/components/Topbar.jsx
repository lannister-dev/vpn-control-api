import { Icon } from "./Icon.jsx";

export function Topbar({
  crumbs = ["Workspace"],
  theme,
  onToggleTheme,
  onOpenPalette,
  onRefresh,
  lastSync,
  notifCount = 0,
}) {
  return (
    <header className="topbar">
      <div className="crumbs">
        {crumbs.map((c, i) => (
          <span key={i} style={{ display: "inline-flex", alignItems: "center" }}>
            {i > 0 && <Icon className="crumb-sep" name="chevron-right" size={13} />}
            <span className={"crumb " + (i === crumbs.length - 1 ? "current" : "")}>{c}</span>
          </span>
        ))}
      </div>
      <div className="topbar-spacer" />
      <div className="topbar-actions">
        <span className="env-pill"><span className="status-dot ok pulse" /> PROD</span>
        {lastSync && (
          <span className="last-sync-label muted text-xs mono" style={{ marginRight: 8, whiteSpace: "nowrap" }}>
            Обновлено {lastSync}
          </span>
        )}
        <button className="btn btn-ghost btn-icon" onClick={onRefresh} title="Обновить">
          <Icon name="refresh" size={15} />
        </button>
        <button className="btn btn-ghost btn-icon" title="Уведомления" style={{ position: "relative" }}>
          <Icon name="bell" size={15} />
          {notifCount > 0 && (
            <span style={{ position: "absolute", top: 4, right: 4, width: 6, height: 6, borderRadius: "50%", background: "var(--bad)" }} />
          )}
        </button>
        <button className="btn btn-ghost btn-icon" onClick={onToggleTheme} title="Переключить тему">
          <Icon name={theme === "dark" ? "sun" : "moon"} size={15} />
        </button>
        <button className="btn btn-ghost" onClick={onOpenPalette}>
          <Icon name="command" size={13} />
          <span>Команды</span>
          <span className="kbd">K</span>
        </button>
      </div>
    </header>
  );
}
