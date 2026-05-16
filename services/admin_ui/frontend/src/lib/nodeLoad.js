export function nodeLoad(node, liveDist) {
  // Prefer live connection count (sing-box clash-API via NATS KV), fall back
  // to static placements_backend if live stats unavailable.
  const slot = liveDist
    ? (node?.role === "backend" ? liveDist.as_backend : liveDist.as_entry)
    : null;
  const liveUsed = slot?.device_count;
  const used = Number(
    liveUsed != null ? liveUsed : (node?.placements_backend || 0),
  );
  const rawCap = node?.capacity;
  const capacity = Number.isFinite(rawCap) && rawCap > 0 ? Number(rawCap) : null;
  const liveLabel = liveUsed != null ? " (live)" : "";

  if (capacity === null) {
    return {
      used,
      capacity: null,
      pct: null,
      tone: "muted",
      label: String(used),
      tooltip:
        `Активных коннектов${liveLabel}: ${used}. ` +
        `Лимит не задан (capacity = 0/null) — нет цели для расчёта %.`,
    };
  }

  const pct = Math.round((used / capacity) * 100);
  const tone = pct >= 95 ? "bad" : pct >= 75 ? "warn" : "ok";
  return {
    used,
    capacity,
    pct,
    tone,
    label: `${used} / ${capacity}`,
    tooltip:
      `Активных коннектов${liveLabel}: ${used}. ` +
      `Лимит (capacity): ${capacity}. ` +
      `Использовано ${pct}%.`,
  };
}

export function regionLoad(nodes) {
  const list = Array.isArray(nodes) ? nodes : [];
  let usedSum = 0;
  let capSum = 0;
  let unknownCount = 0;
  for (const n of list) {
    const { used, capacity } = nodeLoad(n);
    usedSum += used;
    if (capacity == null) unknownCount += 1;
    else capSum += capacity;
  }
  if (capSum === 0) {
    return {
      used: usedSum,
      capacity: null,
      pct: null,
      tone: "muted",
      label: String(usedSum),
      tooltip:
        `Активных назначений в регионе: ${usedSum}. ` +
        `Capacity не задан ни у одной ноды — % не считается.`,
    };
  }
  const pct = Math.round((usedSum / capSum) * 100);
  const tone = pct >= 95 ? "bad" : pct >= 75 ? "warn" : "ok";
  const note = unknownCount > 0
    ? ` (${unknownCount} нод без capacity в расчёт не вошли)`
    : "";
  return {
    used: usedSum,
    capacity: capSum,
    pct,
    tone,
    label: `${usedSum} / ${capSum}`,
    tooltip:
      `Активных назначений: ${usedSum}. ` +
      `Суммарный capacity: ${capSum}. ` +
      `Загрузка региона ${pct}%${note}.`,
  };
}
