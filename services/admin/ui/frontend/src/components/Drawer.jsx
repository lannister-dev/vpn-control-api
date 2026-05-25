import { useEffect, useRef } from "react";
import { Icon } from "./Icon.jsx";

export function Drawer({ title, subtitle, head, onClose, tabs, activeTab, onTab, actions, children, width, className }) {
  useEffect(() => {
    const onEsc = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [onClose]);

  const widthStyle = width ? { width: typeof width === "number" ? `${width}px` : width } : undefined;
  const mouseDownOnBackdropRef = useRef(false);

  return (
    <div
      className="slideover-backdrop"
      onMouseDown={(e) => { mouseDownOnBackdropRef.current = e.target === e.currentTarget; }}
      onMouseUp={(e) => {
        if (e.target === e.currentTarget && mouseDownOnBackdropRef.current) onClose();
        mouseDownOnBackdropRef.current = false;
      }}
    >
      <aside
        className={`slideover ${className || ""}`.trim()}
        style={widthStyle}
      >
        <div className="slideover-head">
          <button className="slideover-back" onClick={onClose} aria-label="Назад" type="button">
            <Icon name="chevron-left" size={20} />
          </button>
          {head || (
            <div className="slideover-title-main">
              <div className="slideover-title">{title}</div>
              {subtitle && <div className="slideover-sub">{subtitle}</div>}
            </div>
          )}
          {actions}
          <button className="btn btn-ghost btn-icon slideover-close" onClick={onClose} title="Закрыть">
            <Icon name="x" size={15} />
          </button>
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
