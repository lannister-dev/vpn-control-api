import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon.jsx";

export function BottomSheet({ open, onClose, title, children, height = "auto" }) {
  const [dragY, setDragY] = useState(0);
  const [dragging, setDragging] = useState(false);
  const startYRef = useRef(0);
  const sheetRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  useEffect(() => { if (!open) setDragY(0); }, [open]);

  const onTouchStart = (e) => {
    startYRef.current = e.touches[0].clientY;
    setDragging(true);
  };
  const onTouchMove = (e) => {
    if (!dragging) return;
    const dy = e.touches[0].clientY - startYRef.current;
    if (dy > 0) setDragY(dy);
  };
  const onTouchEnd = () => {
    setDragging(false);
    if (dragY > 120) onClose?.();
    else setDragY(0);
  };

  if (!open) return null;

  return (
    <div className="bsheet-backdrop" onClick={onClose}>
      <div
        ref={sheetRef}
        className="bsheet"
        style={{ transform: `translateY(${dragY}px)`, transition: dragging ? "none" : "transform 220ms cubic-bezier(.22,1,.36,1)", height }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="bsheet-handle-wrap"
          onTouchStart={onTouchStart}
          onTouchMove={onTouchMove}
          onTouchEnd={onTouchEnd}
        >
          <div className="bsheet-handle" />
        </div>
        {title && (
          <div className="bsheet-head">
            <div className="bsheet-title">{title}</div>
            <button className="bsheet-close" onClick={onClose} aria-label="Закрыть" type="button">
              <Icon name="x" size={16} />
            </button>
          </div>
        )}
        <div className="bsheet-body">{children}</div>
      </div>
    </div>
  );
}

export function BottomSheetItem({ icon, label, sub, onClick, danger, disabled }) {
  return (
    <button
      type="button"
      className={"bsheet-item" + (danger ? " danger" : "")}
      onClick={onClick}
      disabled={disabled}
    >
      {icon && <span className="bsheet-item-icon"><Icon name={icon} size={16} /></span>}
      <span className="bsheet-item-main">
        <span className="bsheet-item-label">{label}</span>
        {sub && <span className="bsheet-item-sub">{sub}</span>}
      </span>
    </button>
  );
}
