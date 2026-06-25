// Drip / Цепочки — client model: constants, geometry, graph builders.
// Pure JS, no React. Consumed by DripGraph / DripInspector / Drip page.
//
// The CURRENT backend (/support/drip/campaigns) stores a LINEAR list of steps
// (step_order, delay_seconds, condition, text_body, inline_buttons, media).
// `graphFromApi` lays those out as a linear graph; `graphToPayload` writes them
// back. The builder UI additionally renders CONDITION / END nodes and multiple
// branches — that branching model is a backend extension, see README.md.

export const TRIGGERS = {
  trial_started:        { label: "Активировал триал", icon: "zap" },
  purchase:             { label: "Оплатил", icon: "credit-card" },
  user_registered:      { label: "Зарегистрировался", icon: "user-plus" },
  subscription_expired: { label: "Подписка истекла", icon: "clock" },
};

export const CONDITIONS = {
  always:        "Всегда",
  not_connected: "Ещё не подключился",
  not_purchased: "Ещё не купил",
  no_active_sub: "Нет активной подписки",
  connected:     "Подключился к VPN",
  purchased:     "Оплатил подписку",
};

export const UNITS = [
  { v: 60,    l: "мин",   long: "минут" },
  { v: 3600,  l: "ч",     long: "часов" },
  { v: 86400, l: "д",     long: "дней"  },
];

export const BUTTON_STYLES = {
  "":      { l: "По умолчанию", tg: "s-primary" },
  primary: { l: "Синяя",        tg: "s-primary" },
  success: { l: "Зелёная",      tg: "s-success" },
  danger:  { l: "Красная",      tg: "s-danger"  },
};

export const BUTTON_ACTIONS = {
  "":      "Свой URL",
  renew:   "Продлить",
  connect: "Подключение",
  plans:   "Тарифы",
  help:    "Помощь",
};

export const ACTION_ICON = { renew: "refresh", connect: "wifi", plans: "package", help: "help-circle", "": "link" };

export function stripTags(s) { return (s || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim(); }

export function fmtDelay(sec) {
  if (!sec) return "сразу";
  for (let i = UNITS.length - 1; i >= 0; i--) {
    if (sec % UNITS[i].v === 0) return `${sec / UNITS[i].v} ${UNITS[i].l}`;
  }
  return `${Math.round(sec / 60)} мин`;
}
export function splitDelay(sec) {
  const s = sec || 0;
  if (s && s % 86400 === 0) return [s / 86400, 86400];
  if (s && s % 3600 === 0) return [s / 3600, 3600];
  return [Math.round(s / 60) || 0, 60];
}

// ── Lane geometry (graph-space px). Node anchors are computed from cx/top/w/h,
// so keep rendered card sizes == these values (see drip.css min-heights). ──
export const LANE = { C: 320, L: 178, R: 462 };
export const NODE_W = 258;

export function emptyMessage(id) {
  return { id, type: "message", cx: LANE.C, top: 0, w: NODE_W, h: 112,
    delay_seconds: 3600, condition: "always", text: "", buttons: [], media: null, stats: { active: 0 } };
}

// ── Linear layout: trigger → messages → end, centre lane ──
export function layoutLinear(messages, triggerEvent) {
  const nodes = [];
  const edges = [];
  let y = 24;
  const trig = { id: "trig", type: "trigger", cx: LANE.C, top: y, w: 230, h: 46, trigger_event: triggerEvent };
  nodes.push(trig);
  y += trig.h + 64;
  let prev = "trig";
  messages.forEach((m, i) => {
    const h = 112 + (m.buttons?.length > 1 ? 26 : 0) + (m.media ? 0 : 0);
    const node = { ...m, id: m.id || `m${i + 1}`, type: "message", cx: LANE.C, top: y, w: NODE_W, h };
    nodes.push(node);
    edges.push({ from: prev, to: node.id, delayOf: node.id });
    prev = node.id;
    y += h + 64;
  });
  const end = { id: "end", type: "end", cx: LANE.C, top: y, w: 220, h: 60, conversion: false, label: "Цепочка завершена" };
  nodes.push(end);
  edges.push({ from: prev, to: "end" });
  return { nodes, edges };
}

// ── Backend campaign (linear) → graph ──
export function graphFromApi(c) {
  const messages = (c.steps || [])
    .slice()
    .sort((a, b) => a.step_order - b.step_order)
    .map((s, i) => ({
      id: `m${i + 1}`,
      delay_seconds: s.delay_seconds || 0,
      condition: s.condition || "always",
      text: s.text_body || "",
      media: s.media_url ? { kind: s.media_kind || "image", name: "media", size: "" } : null,
      buttons: (s.inline_buttons || []).map((b) => ({ text: b.text || "", url: b.url || "", style: b.style || "", action: b.action || "" })),
      stats: { active: s.active || 0 },
    }));
  const { nodes, edges } = layoutLinear(messages, c.trigger_event || "trial_started");
  return {
    meta: { id: c.id, key: c.key, name: c.name, trigger_event: c.trigger_event || "trial_started", is_active: !!c.is_active,
      stats: c.stats || { active: 0, completed: 0 } },
    nodes, edges,
  };
}

// ── Graph → backend payload (LINEAR graphs only). Branching graphs need the
// extended contract documented in README.md. ──
export function graphToPayload(meta, nodes) {
  const messages = nodes.filter((n) => n.type === "message");
  return {
    key: (meta.key || "").trim(),
    name: (meta.name || "").trim(),
    trigger_event: meta.trigger_event,
    is_active: meta.is_active,
    steps: messages.map((s, i) => ({
      step_order: i,
      delay_seconds: Math.max(0, Math.round(s.delay_seconds || 0)),
      condition: s.condition,
      text_body: s.text || "",
      inline_buttons: (s.buttons || [])
        .filter((b) => b.text.trim() && (b.action || b.url.trim()))
        .map((b) => ({ text: b.text.trim(), url: b.action ? "" : b.url.trim(), style: b.style || null, action: b.action || null })),
      media_kind: s.media ? s.media.kind : null,
      media_url: s.media ? s.media.url || null : null,
    })),
  };
}

// ── Demo / mock: branching chain shown when the API is empty or undeployed.
// Positions are hand-tuned to showcase split + merge. ──
export function mockChain() {
  const nodes = [
    { id: "trig", type: "trigger", cx: LANE.C, top: 24, w: 230, h: 46, trigger_event: "trial_started" },
    { id: "m1", type: "message", cx: LANE.C, top: 150, w: NODE_W, h: 112, delay_seconds: 300, condition: "always",
      text: "Привет, {name}! 🎉<br>Твой пробный период активирован на 3 дня. Подключайся и тестируй на максималках.",
      buttons: [{ text: "Как подключиться", action: "connect", style: "primary" }], media: null, stats: { active: 412 } },
    { id: "c1", type: "condition", cx: LANE.C, top: 322, w: NODE_W, h: 88, check: "connected", yes: "Да", no: "Нет" },
    { id: "m2", type: "message", cx: LANE.L, top: 490, w: 252, h: 112, delay_seconds: 86400, condition: "always",
      text: "Видим, ты уже в деле 😎<br>Вот 3 совета, чтобы выжать максимум скорости из подписки.",
      buttons: [], media: { kind: "image", name: "tips-speed.png", size: "184 KB" }, stats: { active: 96 } },
    { id: "m3", type: "message", cx: LANE.R, top: 490, w: 252, h: 150, delay_seconds: 7200, condition: "not_connected",
      text: "Заметили, ты ещё не подключился — давай помогу 👇<br>Это займёт меньше минуты, а инструкция уже готова.",
      buttons: [{ text: "Подключить за 1 клик", action: "connect", style: "success" }, { text: "Написать в поддержку", action: "help", style: "" }],
      media: null, stats: { active: 188 } },
    { id: "c2", type: "condition", cx: LANE.C, top: 712, w: NODE_W, h: 88, check: "purchased", yes: "Да", no: "Нет" },
    { id: "end1", type: "end", cx: LANE.L, top: 880, w: 220, h: 60, conversion: true, label: "Сконвертился" },
    { id: "m4", type: "message", cx: LANE.R, top: 880, w: 252, h: 132, delay_seconds: 86400, condition: "no_active_sub",
      text: "Триал заканчивается ⏳<br>Для тебя скидка <b>30%</b> на первый месяц — только сегодня.",
      buttons: [{ text: "Забрать скидку −30%", action: "renew", style: "danger" }], media: null, stats: { active: 143 } },
    { id: "end2", type: "end", cx: LANE.R, top: 1052, w: 220, h: 60, conversion: false, label: "Цепочка завершена" },
  ];
  const edges = [
    { from: "trig", to: "m1", delayOf: "m1" },
    { from: "m1", to: "c1" },
    { from: "c1", to: "m2", branch: "yes", delayOf: "m2" },
    { from: "c1", to: "m3", branch: "no", delayOf: "m3" },
    { from: "m2", to: "c2" },
    { from: "m3", to: "c2" },
    { from: "c2", to: "end1", branch: "yes" },
    { from: "c2", to: "m4", branch: "no", delayOf: "m4" },
    { from: "m4", to: "end2" },
  ];
  return {
    meta: { id: null, key: "trial_activation", name: "Триал → активация → конверсия",
      trigger_event: "trial_started", is_active: true, stats: { active: 1027, completed: 8344 } },
    nodes, edges,
  };
}
