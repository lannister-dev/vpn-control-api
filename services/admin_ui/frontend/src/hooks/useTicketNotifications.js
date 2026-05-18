import { useEffect, useRef } from "react";
import { api } from "../api/client.js";
import { toast } from "../components/Toast.jsx";

const POLL_MS = 15000;
const STORAGE_KEY = "vpn-ctrl-last-ticket-seen";

export function useTicketNotifications(onOpenTickets) {
  const lastSeenRef = useRef(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      lastSeenRef.current = raw ? Number(raw) : null;
    } catch { /* ignore */ }

    let stop = false;
    const poll = async () => {
      try {
        const list = await api.get("/support/tickets?limit=10&status=open");
        const items = list?.items || [];
        if (!items.length) return;
        const newest = items
          .map((t) => new Date(t.last_message_at || t.updated_at || t.created_at).getTime())
          .filter((n) => Number.isFinite(n))
          .reduce((a, b) => Math.max(a, b), 0);
        if (lastSeenRef.current == null) {
          lastSeenRef.current = newest;
          localStorage.setItem(STORAGE_KEY, String(newest));
          return;
        }
        if (newest <= lastSeenRef.current) return;
        const fresh = items.filter((t) => {
          const ts = new Date(t.last_message_at || t.updated_at || t.created_at).getTime();
          return ts > lastSeenRef.current;
        });
        for (const t of fresh.slice(0, 3)) {
          const who = t.user_username ? `@${t.user_username}` : `tg:${t.user_telegram_id || "—"}`;
          const subject = (t.subject || "Без темы").slice(0, 60);
          toast.info(`Новый тикет от ${who}: ${subject}`, {
            action: { label: "Открыть", onClick: () => onOpenTickets?.("tickets") },
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
  }, [onOpenTickets]);
}
