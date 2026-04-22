import { useEffect } from "react";
import { Icon } from "./Icon.jsx";

export function Drawer({ title, subtitle, onClose, tabs, activeTab, onTab, children }) {
  useEffect(() => {
    const onEsc = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [onClose]);

  return (
    <div className="slideover-backdrop" onClick={onClose}>
      <aside className="slideover" onClick={(e) => e.stopPropagation()}>
        <div className="slideover-head">
          <div className="slideover-title-main">
            <div className="slideover-title">{title}</div>
            {subtitle && <div className="slideover-sub">{subtitle}</div>}
          </div>
          <button className="btn btn-ghost btn-icon btn-xs" onClick={onClose}><Icon name="chevron-right" size={14} /></button>
        </div>
        {tabs && (
          <div className="slideover-tabs">
            {tabs.map((t) => (
              <button key={t.id} className="slideover-tab" data-active={activeTab === t.id} onClick={() => onTab(t.id)}>
                {t.label}
              </button>
            ))}
          </div>
        )}
        <div className="slideover-body">{children}</div>
      </aside>
    </div>
  );
}
