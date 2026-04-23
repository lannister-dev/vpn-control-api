import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Icon } from "./Icon.jsx";

const ToastCtx = createContext({ show: () => {} });
export const useToast = () => useContext(ToastCtx);

let _globalShow = () => {};
export const toast = {
  ok: (message) => _globalShow({ tone: "ok", message }),
  warn: (message) => _globalShow({ tone: "warn", message }),
  bad: (message) => _globalShow({ tone: "bad", message }),
};

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const show = useCallback((opts) => {
    const id = Date.now() + Math.random();
    const t = { id, tone: "ok", ttl: 3500, ...(typeof opts === "string" ? { message: opts } : opts) };
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
          const icon = tone === "bad" ? "alert-circle" : tone === "warn" ? "alert-triangle" : "check";
          return (
            <div key={t.id} className={"toast toast-" + tone} onClick={() => remove(t.id)} role="status">
              <span className={"toast-icon toast-icon-" + tone}><Icon name={icon} size={12} strokeWidth={2.5} /></span>
              <span className="toast-msg">{t.message}</span>
              <span className="toast-close"><Icon name="x" size={12} /></span>
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}
