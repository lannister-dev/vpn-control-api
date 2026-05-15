import { useEffect, useRef } from "react";

export function Modal({ title, children, footer, onClose }) {
  useEffect(() => {
    const onEsc = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [onClose]);

  const mouseDownOnBackdropRef = useRef(false);

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => { mouseDownOnBackdropRef.current = e.target === e.currentTarget; }}
      onMouseUp={(e) => {
        if (e.target === e.currentTarget && mouseDownOnBackdropRef.current) onClose();
        mouseDownOnBackdropRef.current = false;
      }}
    >
      <div className="modal">
        <div className="modal-head">
          <h3 className="modal-title">{title}</h3>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}
