# Support module · install

Drop-in mirror for `frontend/src/`. Paths in this folder match exactly what should land in the repo.

## What's inside

```
frontend/src/
├─ App.jsx                                  (replace)
├─ components/
│  ├─ Icon.jsx                              (replace — adds 17 icons, keeps all existing)
│  ├─ Sidebar.jsx                           (replace — adds "Поддержка" group + attention badge)
│  ├─ Palette.jsx                           (replace — adds 3 quick-action commands)
│  └─ support/
│     ├─ SupportPrimitives.jsx              (NEW — TicketStatusPill, PriorityDot, MessageBubble, MediaThumb, Lightbox, Composer, TemplatesPopover)
│     ├─ TicketDrawer.jsx                   (NEW — chat drawer with KPI ribbon, quick actions, context, meta, chat scroller, composer)
│     └─ support.css                        (NEW — all support visual styles, only uses tokens from styles.css)
├─ pages/
│  ├─ Tickets.jsx                           (NEW)
│  ├─ SupportTemplates.jsx                  (NEW)
│  ├─ Broadcasts.jsx                        (NEW)
│  └─ Overview.patch.md                     (patch instructions for the existing file)
```

## Apply

1. Copy each file to its mirrored path under `frontend/src/`.
2. Apply the two manual edits documented in `pages/Overview.patch.md`:
   - add `ticketsStats` useQuery call
   - add 2 `<KpiCell />` entries to the kpi-hero
   - add `.kpi-hero[data-cells="6"]` block to `styles.css`
   - mark the strip `<div className="kpi-hero" data-cells="6">`
3. `npm install` is **not** required — no new dependencies.
4. `npm run dev` and check:
   - sidebar shows "Поддержка" with three items between "Бизнес" and "Система";
   - clicking Тикеты renders the operator inbox (with mock fallback if the API isn't deployed);
   - ⌘K palette shows new "Поддержка — действия" group;
   - Overview shows two new KPIs;
   - Tickets count badge on the sidebar pulls from `/support/tickets/stats`.

## Backend contract (expected endpoints)

The frontend degrades gracefully (mock data) when these aren't deployed — UI works either way.

```
GET    /support/tickets/stats                  → { open, unanswered, avg_reply_minutes, avg_reply_change, closed_today, open_spark_24h, reply_spark_24h }
GET    /support/tickets                        → { items: Ticket[], total }
       ?search, ?assignee=me, ?status, ?unanswered_minutes, ?category, ?priority
POST   /support/tickets                        → Ticket
GET    /support/tickets/:id                    → Ticket
PATCH  /support/tickets/:id                    → { status?, priority?, category?, assignee? }
POST   /support/tickets/bulk-update            → { ids: string[], status?, priority?, assignee? }
GET    /support/tickets/:id/messages           → { items: Message[] }
POST   /support/tickets/:id/messages           multipart: text, is_note, files[]
POST   /support/tickets/:id/grant-day          → { ok }
POST   /support/tickets/:id/refund             → { ok }

GET    /support/templates                      → { items: Template[] }
POST   /support/templates                      → Template
PATCH  /support/templates/:id                  → Template
DELETE /support/templates/:id                  → { ok }

GET    /support/broadcasts                     → { items: Broadcast[] }
GET    /support/broadcasts/audience-size?audience=…&plan_id=… → { count }
POST   /support/broadcasts                     multipart: audience, plan_id?, text, buttons (json), media?, status, scheduled_at?
```

### Schemas

```ts
type Ticket = {
  id: string;
  subject: string;
  status: "new" | "in_progress" | "waiting_user" | "closed";
  priority: "low" | "normal" | "high" | "urgent";
  category: "payment" | "technical" | "account" | "speed" | "connection" | "refund" | "other";
  assignee: string | null;          // username, "me" allowed in patch payload
  has_media: boolean;
  attachments_count: number;
  created_at: string;
  updated_at: string;
  last_activity_at: string;
  user: {
    id: string; username?: string; telegram_id: number;
    balance: number; plan_name?: string; expires_at?: string;
    lifetime_spend?: number;
  };
};

type Message = {
  id: string;
  from: "user" | "operator" | "system";
  kind?: "text" | "system";
  text?: string;
  media?: Array<{
    kind: "image" | "video" | "voice" | "audio" | "document";
    url: string;
    thumb_url?: string;
    file_name?: string;
    file_size?: number;
    duration?: number;             // seconds — for video/voice
  }>;
  created_at: string;
  delivered?: boolean;              // for operator → user
  read?: boolean;
  is_note?: boolean;                // internal note, not delivered
  author?: { label: string };
};

type Template = {
  id: string; tag: string;
  title: string; body: string;
  used_count?: number;
};

type Broadcast = {
  id: string;
  audience: "all" | "active" | "expiring" | "by_plan" | "trial" | "no_sub";
  audience_label?: string;
  preview: string;
  status: "draft" | "scheduled" | "sending" | "sent" | "failed";
  delivered?: number;
  errors?: number;
  clicks?: number;
  sent_at?: string;
  scheduled_at?: string;
  created_at: string;
};
```

## Design constraints respected

- Только токены из `styles.css`. Все цвета, радиусы, тени — через `var(--…)`.
- `data-density` через CSS-переменные родителя — таблица тикетов наследует `--row-h`, `--pad-y`, `--pad-x`.
- Моноширинный шрифт (`var(--font-mono)`) для всех технических ID: ticket `#xxxx`, hwid, telegram_id, UUID-фрагменты, цифры доставлено/ошибки/click-rate, переменные шаблонов `{user_name}` и т.д.
- Реюз компонентов: `Drawer`, `Modal`, `Field`, `Toast`, `Empty`, `UserAvatar`, `BalancePill`, `DaysCountdown`, `FilterChip`, `FilterPresets`, `UserDrawer` (открывается из тикета).
- Lucide-style иконки — без сторонних шрифтов, все добавлены в `Icon.jsx`.
- Empty / loading / error состояния — для каждой страницы.
- Mobile-friendly: список тикетов схлопывается в карточки на ≤960px (`.tk-mobile-list`), drawer — full-screen на mobile (через существующие правила `.slideover`); медиа — лайтбокс по тапу.

## Notes

- TicketDrawer использует `Drawer` через prop `actions` — кнопка `×` остаётся за компонентом Drawer, не дублируется.
- В composer `⌘+Enter` отправляет сообщение, `Ctrl+Enter` — то же на Windows/Linux.
- TemplatesPopover ищет по title + body; переменные подставляются на момент инсёрта (видны в виде уже подставленного текста, что соответствует UX Telegram-помощников).
- Bulk-приоритет — popup-меню в bulk-bar, чтобы не плодить 4 отдельные кнопки.
- Lightbox: ←/→/Esc, click outside чтобы закрыть, для видео — нативный `controls`.
- В Broadcasts композер MarkdownV2 рендерит `*bold*`, `_italic_`, `` `code` `` — этого достаточно для превью; на бэке используйте Bot API напрямую.
