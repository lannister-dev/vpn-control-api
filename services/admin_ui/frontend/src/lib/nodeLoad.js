export function nodeLoad(node, opts = {}) {
  // Combined "нагрузка": max of multiple normalised signals.
  // 1. placements / capacity  — pre-allocated load
  // 2. live_connections / capacity  — real TCP sessions right now
  // 3. cpu_pct  — agent heartbeat CPU usage (when reported)
  // Worst-of metric → highlights real bottleneck.
  const placements = Number(node?.placements_backend || 0);
  const rawCap = node?.capacity;
  const capacity = Number.isFinite(rawCap) && rawCap > 0 ? Number(rawCap) : null;
  const live = Number.isFinite(opts.liveConnections) ? Number(opts.liveConnections) : null;
  const cpuPct = Number.isFinite(opts.cpuPct) ? Number(opts.cpuPct) : null;

  const components = [];
  if (capacity && capacity > 0) {
    components.push({ name: "плейсменты", pct: (placements / capacity) * 100, used: placements, total: capacity });
    if (live != null) {
      components.push({ name: "live коннекты", pct: (live / capacity) * 100, used: live, total: capacity });
    }
  }
  if (cpuPct != null) {
    components.push({ name: "CPU", pct: cpuPct, used: cpuPct, total: 100 });
  }

  if (components.length === 0) {
    return {
      used: placements,
      capacity: null,
      pct: null,
      tone: "muted",
      label: String(placements),
      tooltip: "Нет данных для расчёта нагрузки.",
    };
  }

  const dominant = components.reduce((a, b) => (b.pct > a.pct ? b : a));
  const pct = Math.round(dominant.pct);
  const tone = pct >= 95 ? "bad" : pct >= 75 ? "warn" : "ok";
  const tipLines = components.map(
    (c) => `· ${c.name}: ${Math.round(c.pct)}% (${c.used}/${c.total})`,
  );
  return {
    used: dominant.used,
    capacity: dominant.total,
    pct,
    tone,
    label: `${dominant.used} / ${dominant.total}`,
    tooltip:
      `Нагрузка ${pct}% (доминирует «${dominant.name}»).\n` +
      tipLines.join("\n"),
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
