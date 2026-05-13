/* ─────────────────────────────────────────────────────────────────────
   PATCH for frontend/src/pages/Overview.jsx
   Adds two KPI cards to the existing kpi-hero strip:
     • Открытых тикетов  (--bad if > 10)
     • Avg время ответа (--warn if > 30 min)

   The strip is `grid-template-columns: 1.6fr repeat(4, 1fr)` (5 cells).
   We add 2 cards → bump to repeat(6, 1fr) so it stays balanced.

   The data hook + cards are below. Paste:
     A) the imports + hook (top of the file)
     B) the two <KpiCell /> right after the existing 4 KpiCells
     C) the small CSS override for the wider strip (in `styles.css`
        or inline-block on the .sec)
   ───────────────────────────────────────────────────────────────────── */

// A) IMPORTS — add to the top of Overview.jsx near other useQuery imports:
//
//     // (api, useQuery, Icon already imported)
//
// B) INSIDE OverviewPage(), with the other useQuery calls:
//
//     const ticketsStats = useQuery(
//       () => api.get("/support/tickets/stats").catch(() => null),
//       { interval: 30000 },
//     );

// C) INSIDE the existing `<div className="kpi-hero">`, after the
//    existing four <KpiCell /> entries (Active subs / Traffic / Latency
//    / Probe success), insert:

/*
          <KpiCell
            label="Открытых тикетов"
            value={ticketsStats.data?.open ?? "—"}
            unit=""
            delta={
              ticketsStats.data?.unanswered != null
                ? `${ticketsStats.data.unanswered} без ответа`
                : "—"
            }
            deltaTone={(ticketsStats.data?.open || 0) > 10 ? "down" : "up"}
            icon="message-square"
            sparkSeed={71}
            sparkColor={
              (ticketsStats.data?.open || 0) > 10
                ? "var(--bad)"
                : "var(--accent)"
            }
            realSpark={ticketsStats.data?.open_spark_24h}
          />
          <KpiCell
            label="Avg время ответа"
            value={
              ticketsStats.data?.avg_reply_minutes != null
                ? String(ticketsStats.data.avg_reply_minutes)
                : "—"
            }
            unit={ticketsStats.data?.avg_reply_minutes != null ? "мин" : ""}
            delta={
              ticketsStats.data?.avg_reply_change != null
                ? `${ticketsStats.data.avg_reply_change > 0 ? "+" : ""}${ticketsStats.data.avg_reply_change}м vs вчера`
                : "—"
            }
            deltaTone={
              (ticketsStats.data?.avg_reply_minutes || 0) > 30
                ? "down"
                : "up"
            }
            icon="clock"
            sparkSeed={53}
            sparkColor={
              (ticketsStats.data?.avg_reply_minutes || 0) > 30
                ? "var(--warn)"
                : "var(--ok)"
            }
            realSpark={ticketsStats.data?.reply_spark_24h}
          />
*/

// D) CSS — add to frontend/src/styles.css just below the existing
//    `.kpi-hero { ... }` rule (around line 466), so the strip can host
//    6 cells without overflowing on wide screens:

/*
.kpi-hero[data-cells="6"] {
  grid-template-columns: 1.4fr repeat(5, 1fr);
}
@media (max-width: 1380px) {
  .kpi-hero[data-cells="6"] { grid-template-columns: 1fr 1fr 1fr; }
  .kpi-hero[data-cells="6"] .kpi-cell.primary { grid-column: 1 / -1; border-bottom: 1px solid var(--border); }
}
*/

// And mark the strip in Overview.jsx with the attribute:
//
//     <div className="kpi-hero" data-cells="6">

// That's it. Backend payload expected from /support/tickets/stats:
//
//   {
//     "open":              22,
//     "unanswered":         3,
//     "avg_reply_minutes": 14,
//     "avg_reply_change":  -3,        // negative is better
//     "closed_today":      18,
//     "open_spark_24h":   [..22 values],
//     "reply_spark_24h":  [..22 values]
//   }
//
// All fields are optional — missing fields fall back to "—".
