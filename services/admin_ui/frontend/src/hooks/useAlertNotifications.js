import { useEffect, useRef } from "react";
import { api } from "../api/client.js";
import { toast } from "../components/Toast.jsx";

const POLL_MS = 20000;
const STORAGE_KEY = "vpn-ctrl-last-alert-seen";

export function useAlertNotifications(onOpenAlerts) {
  const lastSeenRef = useRef(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      lastSeenRef.current = raw ? Number(raw) : null;
    } catch { /* ignore */ }

    let stop = false;
    const poll = async () => {
      try {
        const list = await api.get("/admin/alerts?limit=10");
        const items = list?.items || [];
        if (!items.length) return;
        const newest = items
          .map((a) => new Date(a.last_seen_at || a.created_at).getTime())
          .filter((n) => Number.isFinite(n))
          .reduce((a, b) => Math.max(a, b), 0);
        if (lastSeenRef.current == null) {
          lastSeenRef.current = newest;
          localStorage.setItem(STORAGE_KEY, String(newest));
          return;
        }
        if (newest <= lastSeenRef.current) return;
        const fresh = items.filter((a) => {
          const ts = new Date(a.last_seen_at || a.created_at).getTime();
          return ts > lastSeenRef.current && !a.read_at;
        });
        for (const a of fresh.slice(0, 3)) {
          const tone = a.level === "critical" ? "bad" : a.level === "warning" ? "warn" : "info";
          toast[tone](a.title, {
            action: { label: "Открыть", onClick: () => onOpenAlerts?.() },
            duration: 10000,
          });
        }
        lastSeenRef.current = newest;
        localStorage.setItem(STORAGE_KEY, String(newest));
      } catch { /* ignore */ }
    };

    poll();
    const id = setInterval(() => { if (!stop) poll(); }, POLL_MS);
    return () => { stop = true; clearInterval(id); };
  }, [onOpenAlerts]);
}
