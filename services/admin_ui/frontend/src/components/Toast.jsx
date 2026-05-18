import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Icon } from "./Icon.jsx";

const ToastCtx = createContext({ show: () => {} });
export const useToast = () => useContext(ToastCtx);

let _globalShow = () => {};
export const toast = {
  ok: (message, opts = {}) => _globalShow({ tone: "ok", message, ...opts }),
  warn: (message, opts = {}) => _globalShow({ tone: "warn", message, ...opts }),
  bad: (message, opts = {}) => _globalShow({ tone: "bad", message, ...opts }),
  info: (message, opts = {}) => _globalShow({ tone: "info", message, ...opts }),
};

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const show = useCallback((opts) => {
    const id = Date.now() + Math.random();
    const t = { id, tone: "ok", ttl: 3500, ...(typeof opts === "string" ? { message: opts } : opts) };
    if (t.duration) t.ttl = t.duration;
    setItems((xs) => [...xs, t]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), t.ttl);
  }, []);

  useEffect(() => { _globalShow = show; return () => { _globalShow = () => {}; }; }, [show]);
  const remove = (id) => setItems((xs) => xs.filter((x) => x.id !== id));

  return (
    <ToastCtx.Provider value={{ show }}>
      {children}
      <div className="toast-stack">
        {items.map((t) => {
          const tone = t.tone || "ok";
          const icon = tone === "bad" ? "alert-circle" : tone === "warn" ? "alert-triangle" : tone === "info" ? "bell" : "check";
          const handleClick = () => {
            if (t.action?.onClick) { t.action.onClick(); }
            remove(t.id);
          };
          return (
            <div key={t.id} className={"toast toast-" + tone} onClick={handleClick} role="status" style={{ cursor: t.action ? "pointer" : "default" }}>
              <span className={"toast-icon toast-icon-" + tone}><Icon name={icon} size={12} strokeWidth={2.5} /></span>
              <span className="toast-msg">{t.message}</span>
              {t.action ? (
                <span className="toast-action" style={{ marginLeft: 8, color: "var(--accent)", fontWeight: 600 }}>{t.action.label}</span>
              ) : (
                <span className="toast-close" onClick={(e) => { e.stopPropagation(); remove(t.id); }}><Icon name="x" size={12} /></span>
              )}
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}
