export function nodeLoad(node) {
  const used = Number(node?.placements_backend || 0);
  const rawCap = node?.capacity;
  const capacity = Number.isFinite(rawCap) && rawCap > 0 ? Number(rawCap) : null;

  if (capacity === null) {
    return {
      used,
      capacity: null,
      pct: null,
      tone: "muted",
      label: String(used),
      tooltip:
        `Активных назначений: ${used}. ` +
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
      `Активных назначений: ${used}. ` +
      `Лимит (capacity): ${capacity}. ` +
      `Использовано ${pct}% слота.`,
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
