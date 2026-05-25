import { useEffect, useRef } from "react";
import { api } from "../api/client.js";
import { toast } from "../components/Toast.jsx";

const POLL_MS = 30000;
const STORAGE_KEY = "vpn-ctrl-last-user-seen";

export function useUserNotifications(onGotoUsers) {
  const lastSeenRef = useRef(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      lastSeenRef.current = raw ? Number(raw) : null;
    } catch { /* ignore */ }

    let stop = false;
    const poll = async () => {
      try {
        const list = await api.get("/users?limit=5");
        const items = list?.items || [];
        if (!items.length) return;
        const newest = items
          .map((u) => new Date(u.created_at).getTime())
          .filter((n) => Number.isFinite(n))
          .reduce((a, b) => Math.max(a, b), 0);
        if (lastSeenRef.current == null) {
          lastSeenRef.current = newest;
          localStorage.setItem(STORAGE_KEY, String(newest));
          return;
        }
        if (newest <= lastSeenRef.current) return;
        const fresh = items.filter((u) => new Date(u.created_at).getTime() > lastSeenRef.current);
        for (const u of fresh.slice(0, 3)) {
          const who = u.username ? `@${u.username}` : `tg:${u.telegram_id || "—"}`;
          toast.info(`Новый пользователь: ${who}`, {
            action: { label: "Открыть", onClick: () => onGotoUsers?.("users") },
            duration: 8000,
          });
        }
        lastSeenRef.current = newest;
        localStorage.setItem(STORAGE_KEY, String(newest));
      } catch { /* ignore */ }
    };

    poll();
    const id = setInterval(() => { if (!stop) poll(); }, POLL_MS);
    return () => { stop = true; clearInterval(id); };
  }, [onGotoUsers]);
}
