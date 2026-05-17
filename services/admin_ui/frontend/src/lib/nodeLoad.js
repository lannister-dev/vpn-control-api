export function nodeLoad(node, opts = {}) {
  // Реальная нагрузка ноды — max(CPU%, Bandwidth%). Коннекты и плейсменты
  // про количество, а не про нагрузку (один коннект может качать гигабит,
  // тысяча простаивать). null/muted когда метрик от агента ещё нет.
  const cpuPct = Number.isFinite(opts.cpuPct) ? Number(opts.cpuPct) : null;
  const bwPct = Number.isFinite(opts.bandwidthPct) ? Number(opts.bandwidthPct) : null;

  const components = [];
  if (cpuPct != null) components.push({ name: "CPU", pct: cpuPct });
  if (bwPct != null) components.push({ name: "Bandwidth", pct: bwPct });

  if (components.length === 0) {
    return {
      pct: null,
      tone: "muted",
      label: "—",
      tooltip: "Нагрузка: нет данных от агента (heartbeat без CPU/bw).",
    };
  }

  const dominant = components.reduce((a, b) => (b.pct > a.pct ? b : a));
  const pct = Math.round(dominant.pct);
  const tone = pct >= 90 ? "bad" : pct >= 70 ? "warn" : "ok";
  const tipLines = components.map((c) => `· ${c.name}: ${Math.round(c.pct)}%`);
  return {
    pct,
    tone,
    label: `${pct}%`,
    tooltip:
      `Нагрузка ${pct}% (доминирует «${dominant.name}»).\n` +
      tipLines.join("\n"),
  };
}

export function regionLoad(nodes) {
  // Region load = mean(CPU) across enabled nodes; null when no CPU data yet.
  const list = (Array.isArray(nodes) ? nodes : []).filter((n) => n?.is_enabled);
  const samples = [];
  for (const n of list) {
    const cpu = n?.cpu_pct;
    if (Number.isFinite(cpu)) samples.push(Number(cpu));
  }
  if (samples.length === 0) {
    return {
      pct: null,
      tone: "muted",
      label: "—",
      tooltip: "Нет данных CPU от агентов — % региона не считается.",
    };
  }
  const mean = samples.reduce((s, x) => s + x, 0) / samples.length;
  const pct = Math.round(mean);
  const tone = pct >= 90 ? "bad" : pct >= 70 ? "warn" : "ok";
  return {
    pct,
    tone,
    label: `${pct}%`,
    tooltip: `Средний CPU ${pct}% по ${samples.length} нодам региона.`,
  };
}
