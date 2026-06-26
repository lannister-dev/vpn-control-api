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
// so keep rendered card sizes == these values (see scenario.css min-heights). ──
export const LANE = { C: 320, L: 178, R: 462 };
export const NODE_W = 258;

export function emptyMessage(id) {
  return { id, type: "message", cx: LANE.C, top: 0, w: NODE_W, h: 112,
    delay_seconds: 3600, condition: "always", repeat: 1, repeatInterval: 0,
    text: "", buttons: [], media: null, stats: { active: 0 } };
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

// ── Auto-layout a branching graph: BFS rows (depth) × lanes (branch side) ──
export function autoLayout(nodes, edges) {
  const ROW = 156;
  const out = {};
  edges.forEach((e) => { (out[e.from] = out[e.from] || []).push(e); });
  const start = (nodes.find((n) => n.type === "trigger") || nodes[0] || {}).id;
  const row = {}, lane = {};
  if (start != null) { row[start] = 0; lane[start] = LANE.C; }
  const queue = start != null ? [start] : [];
  const seen = new Set(queue);
  let guard = 0;
  while (queue.length && guard < 2000) {
    guard += 1;
    const id = queue.shift();
    const r = row[id] || 0;
    const l = lane[id] != null ? lane[id] : LANE.C;
    (out[id] || []).forEach((e) => {
      const childLane = e.branch === "yes" ? LANE.L : e.branch === "no" ? LANE.R : l;
      row[e.to] = Math.max(row[e.to] || 0, r + 1);
      if (lane[e.to] == null) lane[e.to] = childLane;
      if (!seen.has(e.to)) { seen.add(e.to); queue.push(e.to); }
    });
  }
  let maxRow = 0;
  Object.values(row).forEach((r) => { maxRow = Math.max(maxRow, r); });
  nodes.forEach((n) => {
    if (row[n.id] == null) { maxRow += 1; row[n.id] = maxRow; lane[n.id] = LANE.C; }
  });
  return nodes.map((n) => {
    const r = row[n.id] != null ? row[n.id] : 0;
    const l = lane[n.id] != null ? lane[n.id] : LANE.C;
    const w = n.type === "trigger" ? 230 : n.type === "end" ? 220 : NODE_W;
    const h = n.type === "trigger" ? 46 : n.type === "end" ? 60 : n.type === "condition" ? 88 : (n.h || 120);
    return { ...n, cx: l, top: 24 + r * ROW, w, h };
  });
}

// ── New unique node key for a given prefix (m/c), based on existing ids ──
export function nextNodeId(nodes, prefix) {
  let max = 0;
  nodes.forEach((n) => {
    const m = new RegExp(`^${prefix}(\\d+)$`).exec(n.id || "");
    if (m) max = Math.max(max, parseInt(m[1], 10));
  });
  return `${prefix}${max + 1}`;
}

// ── Backend campaign (graph: nodes + edges) → editor graph ──
function apiNodeToGraph(n) {
  const base = { id: n.key, type: n.type, cx: n.pos_cx || LANE.C, top: n.pos_top || 0 };
  if (n.type === "condition") {
    return { ...base, w: NODE_W, h: 88, check: n.check || "connected", yes: "Да", no: "Нет" };
  }
  if (n.type === "end") {
    return { ...base, w: 220, h: 60, conversion: !!n.conversion, label: n.label || "Цепочка завершена" };
  }
  return {
    ...base, w: NODE_W, h: 120,
    delay_seconds: n.delay_seconds || 0,
    condition: n.condition || "always",
    repeat: n.repeat_count || 1,
    repeatInterval: n.repeat_interval_sec || 0,
    text: n.text_body || "",
    media: n.media_url ? { kind: n.media_kind || "image", url: n.media_url, name: "media", size: "" } : null,
    buttons: (n.inline_buttons || []).map((b) => ({ text: b.text || "", url: b.url || "", style: b.style || "", action: b.action || "" })),
    stats: { active: 0 },
  };
}

export function graphFromApi(c) {
  const apiNodes = c.nodes || [];
  const apiEdges = c.edges || [];
  const meta = {
    id: c.id, key: c.key, name: c.name,
    trigger_event: c.trigger_event || "trial_started",
    is_active: !!c.is_active, stats: c.stats || { active: 0, completed: 0 },
  };
  if (!apiNodes.length) {
    const { nodes, edges } = layoutLinear([emptyMessage("m1")], meta.trigger_event);
    return { meta, nodes, edges };
  }
  const positioned = apiNodes.some((n) => (n.pos_top || 0) > 0);
  const entryKey = c.entry_node_key || apiNodes[0].key;

  if (!positioned) {
    // migrated / unpositioned → re-layout the message chain linearly
    const messages = apiNodes
      .filter((n) => n.type === "message")
      .map((n) => {
        const g = apiNodeToGraph(n);
        return { delay_seconds: g.delay_seconds, condition: g.condition, text: g.text, media: g.media, buttons: g.buttons, stats: g.stats };
      });
    const { nodes, edges } = layoutLinear(messages.length ? messages : [emptyMessage("m1")], meta.trigger_event);
    return { meta, nodes, edges };
  }

  const nodes = apiNodes.map(apiNodeToGraph);
  const keyType = {};
  apiNodes.forEach((n) => { keyType[n.key] = n.type; });
  const edges = apiEdges.map((e) => ({
    from: e.from, to: e.to,
    branch: e.branch || undefined,
    delayOf: keyType[e.to] === "message" ? e.to : undefined,
  }));
  const entryNode = nodes.find((n) => n.id === entryKey);
  nodes.unshift({
    id: "trig", type: "trigger", cx: LANE.C,
    top: entryNode ? Math.max(0, entryNode.top - 110) : 24,
    w: 230, h: 46, trigger_event: meta.trigger_event,
  });
  edges.unshift({ from: "trig", to: entryKey, delayOf: keyType[entryKey] === "message" ? entryKey : undefined });
  return { meta, nodes, edges };
}

// ── Editor graph → backend payload (full node/edge graph) ──
export function graphToPayload(meta, nodes, edges) {
  const real = nodes.filter((n) => n.type !== "trigger");
  const trigEdge = (edges || []).find((e) => e.from === "trig");
  const entry = trigEdge ? trigEdge.to : (real[0] && real[0].id) || null;
  const nodeOut = real.map((n) => {
    const base = { key: n.id, type: n.type, pos_cx: Math.round(n.cx || 0), pos_top: Math.round(n.top || 0), condition: "always" };
    if (n.type === "condition") return { ...base, check: n.check || null };
    if (n.type === "end") return { ...base, conversion: !!n.conversion, label: n.label || null };
    return {
      ...base,
      delay_seconds: Math.max(0, Math.round(n.delay_seconds || 0)),
      condition: n.condition || "always",
      repeat_count: Math.max(1, Math.round(n.repeat || 1)),
      repeat_interval_sec: Math.max(0, Math.round(n.repeatInterval || 0)),
      text_body: n.text || null,
      inline_buttons: (n.buttons || [])
        .filter((b) => (b.text || "").trim() && (b.action || (b.url || "").trim()))
        .map((b) => ({ text: b.text.trim(), url: b.action ? "" : (b.url || "").trim(), style: b.style || null, action: b.action || null })),
      media_kind: n.media ? n.media.kind : null,
      media_url: n.media ? n.media.url || null : null,
    };
  });
  const edgeOut = (edges || [])
    .filter((e) => e.from !== "trig" && e.to)
    .map((e) => ({ from: e.from, to: e.to, branch: e.branch || null }));
  return {
    key: (meta.key || "").trim(),
    name: (meta.name || "").trim(),
    trigger_event: meta.trigger_event,
    is_active: meta.is_active,
    entry_node_key: entry,
    nodes: nodeOut,
    edges: edgeOut,
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
