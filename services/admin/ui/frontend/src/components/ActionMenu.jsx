import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon.jsx";
import { useIsMobile } from "../hooks/useIsMobile.js";
import { BottomSheet, BottomSheetItem } from "./BottomSheet.jsx";

export function ActionMenu({ title = "Действия", items = [] }) {
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null);
  const btnRef = useRef(null);
  const popRef = useRef(null);
  const visible = items.filter(Boolean);

  useLayoutEffect(() => {
    if (!open || isMobile) return;
    const r = btnRef.current?.getBoundingClientRect();
    if (r) setPos({ top: r.bottom + 6, right: Math.max(8, window.innerWidth - r.right) });
  }, [open, isMobile]);

  useEffect(() => {
    if (!open || isMobile) return;
    const onDown = (e) => {
      if (btnRef.current?.contains(e.target) || popRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    const close = () => setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", close, true);
    window.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", close, true);
      window.removeEventListener("scroll", close, true);
    };
  }, [open, isMobile]);

  const run = (it) => { setOpen(false); it.onClick?.(); };

  const trigger = (
    <button
      ref={btnRef}
      className="btn btn-ghost btn-icon"
      title={title}
      aria-haspopup="menu"
      aria-expanded={open}
      onClick={() => setOpen((o) => !o)}
    >
      <Icon name="more-vertical" size={15} />
    </button>
  );

  if (isMobile) {
    return (
      <>
        {trigger}
        <BottomSheet open={open} onClose={() => setOpen(false)} title={title}>
          {visible.map((it, i) => (
            <BottomSheetItem
              key={i}
              icon={it.icon}
              label={it.label}
              sub={it.sub}
              danger={it.danger}
              disabled={it.disabled}
              onClick={() => run(it)}
            />
          ))}
        </BottomSheet>
      </>
    );
  }

  return (
    <>
      {trigger}
      {open && pos && createPortal(
        <div ref={popRef} className="action-menu-pop" role="menu" style={{ top: pos.top, right: pos.right }}>
          {visible.map((it, i) => (
            <button
              key={i}
              type="button"
              role="menuitem"
              className={"action-menu-item" + (it.danger ? " danger" : "")}
              disabled={it.disabled}
              onClick={() => run(it)}
            >
              {it.icon && <span className="action-menu-ico"><Icon name={it.icon} size={15} /></span>}
              <span className="action-menu-main">
                <span className="action-menu-label">{it.label}</span>
                {it.sub && <span className="action-menu-sub">{it.sub}</span>}
              </span>
            </button>
          ))}
        </div>,
        document.body,
      )}
    </>
  );
}
