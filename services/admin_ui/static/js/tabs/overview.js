import { state, refs, $ } from '../state.js';
import {
  esc, chip, uuidCell, shortId, nodeGeo, nodeNameById,
  routeStatusLabel, formatNumber,
} from '../utils.js';

/**
 * Dashboard overview:
 *   - 4 visual KPI tiles with progress bars
 *   - status banner (ok/warn/bad)
 *   - quick actions
 *   - priority-sorted issues list (left) + activity timeline (right)
 *   - compact readiness / route-distribution / transport chips row
 */

const isEntryNode = (n) => ["whitelist_entry", "entry"].includes(String(n.role || "").toLowerCase());

/* ── NATS stability helper ────────────────────────────
 * Brief disconnects (<30s) render as "reconnecting" (warn) instead of "offline"
 * so the UI doesn't flicker while the backend client is re-negotiating.
 */
const NATS_GRACE_MS = 30_000;
function natsVisualState() {
  const to = state.transportOverview;
  if (!to) return { label: "—", cls: "muted", state: "warn", connected: false };
  if (to.nats_connected) return { label: "online", cls: "ok", state: "ok", connected: true };
  if (state.natsLastOnlineAt && (Date.now() - state.natsLastOnlineAt) < NATS_GRACE_MS) {
    return { label: "reconnecting…", cls: "warn", state: "warn", connected: false, reconnecting: true };
  }
  return { label: "offline", cls: "bad", state: "bad", connected: false };
}

export function renderOverview() {
  renderHeroKpis();
  renderDashTiles();
  const issues = collectIssues();
  renderDashBanner(issues);
  renderDashQuickActions();
  renderDashIssues(issues);
  renderDashActivity();
  renderDashCompact();
  populateOpsDropdowns();
}

/* ── Hero KPIs (small cards at the top) ───────────────── */
function renderHeroKpis() {
  if (state.status) {
    const t = state.status.totals || {};
    if (refs.kpiNodes) refs.kpiNodes.textContent = formatNumber(t.nodes_total || 0);
    const healthy = t.nodes_healthy || 0;
    const draining = t.nodes_draining || 0;
    if (refs.kpiHealthy) refs.kpiHealthy.innerHTML = `${formatNumber(healthy)}${draining > 0 ? ` <span class="muted" style="font-size:11px">· ${draining} drain</span>` : ""}`;
  }
  const healthyRoutes = state.routes.filter((r) => r.health_status === "healthy").length;
  if (refs.kpiRoutes) refs.kpiRoutes.innerHTML = `${formatNumber(healthyRoutes)}<span class="muted" style="font-size:12px"> / ${formatNumber(state.routes.length)}</span>`;
  if (refs.kpiProbeFail) refs.kpiProbeFail.textContent = formatNumber(state.probes.filter((p) => !p.is_reachable).length || 0);
  const natsEl = $("kpi-nats");
  if (natsEl) {
    const n = natsVisualState();
    if (n.cls === "muted") natsEl.textContent = "—";
    else natsEl.innerHTML = `<span class="dot ${n.cls}" style="width:7px;height:7px"></span> ${esc(n.label)}`;
  }
}

/* ── Dashboard tiles ──────────────────────────────────── */
function renderDashTiles() {
  if (!refs.dashTiles) return;
  const nodes = (state.status && state.status.nodes) || [];
  const nonEntry = nodes.filter((n) => !isEntryNode(n));
  const healthyNodes = nonEntry.filter((n) => n.is_healthy && n.is_enabled && !n.is_draining).length;
  const draining = nonEntry.filter((n) => n.is_draining).length;
  const disabled = nonEntry.filter((n) => !n.is_enabled).length;
  const unhealthy = nonEntry.filter((n) => !n.is_healthy && n.is_enabled && !n.is_draining).length;
  const totalBackends = nonEntry.length;
  const nodesPct = totalBackends ? Math.round(healthyNodes / totalBackends * 100) : 100;
  const nodesState = (unhealthy > 0 || disabled > 0) ? "bad" : (draining > 0 ? "warn" : "ok");
  const nodesMeta = [];
  if (unhealthy) nodesMeta.push(`${unhealthy} нездоровых`);
  if (draining) nodesMeta.push(`${draining} draining`);
  if (disabled) nodesMeta.push(`${disabled} отключено`);
  if (!nodesMeta.length) nodesMeta.push(totalBackends ? "все бэкенды здоровы" : "нет бэкендов");

  const routesTotal = state.routes.length;
  const routesHealthy = state.routes.filter((r) => r.health_status === "healthy").length;
  const routesDegraded = state.routes.filter((r) => r.health_status === "degraded" || r.health_status === "suspected").length;
  const routesBlocked = state.routes.filter((r) => r.health_status === "blocked").length;
  const routesPct = routesTotal ? Math.round(routesHealthy / routesTotal * 100) : 100;
  const routesState = routesBlocked > 0 ? "bad" : (routesDegraded > 0 ? "warn" : "ok");
  const routesMeta = [];
  if (routesBlocked) routesMeta.push(`${routesBlocked} блок.`);
  if (routesDegraded) routesMeta.push(`${routesDegraded} деград.`);
  if (!routesMeta.length) routesMeta.push(routesTotal ? "все маршруты healthy" : "маршрутов нет");

  const probes = state.probes || [];
  const probesOk = probes.filter((p) => p.is_reachable).length;
  const probesFail = probes.filter((p) => !p.is_reachable).length;
  const probesPct = probes.length ? Math.round(probesOk / probes.length * 100) : 100;
  const probesState = probes.length === 0 ? "ok" : (probesPct >= 95 ? "ok" : (probesPct >= 85 ? "warn" : "bad"));

  const to = state.transportOverview;
  const nats = natsVisualState();
  const tN = state.transportNodes || [];
  const alive = tN.filter((n) => n.health_verdict === "ok" || n.health_verdict === "lag").length;
  const dead = tN.filter((n) => n.health_verdict === "dead").length;
  const silent = tN.filter((n) => n.health_verdict === "silent").length;
  const tPct = tN.length ? Math.round(alive / tN.length * 100) : 100;
  const tState = !to ? "warn"
    : !nats.connected ? (nats.reconnecting ? "warn" : "bad")
    : (dead > 0 ? "bad" : (silent > 0 ? "warn" : "ok"));

  const tiles = [
    tileHtml({
      icon: "🖥", label: "Серверы",
      value: totalBackends ? `${healthyNodes}<span class="dash-tile-slash">/</span><span class="dash-tile-sub">${totalBackends}</span>` : "—",
      barPct: nodesPct, state: nodesState,
      meta: nodesMeta.join(" · "),
    }),
    tileHtml({
      icon: "🛣", label: "Маршруты",
      value: routesTotal ? `${routesHealthy}<span class="dash-tile-slash">/</span><span class="dash-tile-sub">${routesTotal}</span>` : "—",
      barPct: routesPct, state: routesState,
      meta: routesMeta.join(" · "),
    }),
    tileHtml({
      icon: "🔍", label: "Probes · 24ч",
      value: probes.length ? `${probesPct}<span class="dash-tile-slash">%</span>` : "—",
      barPct: probesPct, state: probesState,
      meta: probes.length ? `${probesFail} сбоев из ${probes.length}` : "нет данных",
    }),
    tileHtml({
      icon: "🚀", label: "Agents",
      value: !to ? "—"
        : nats.connected ? (tN.length ? `${alive}<span class="dash-tile-slash">/</span><span class="dash-tile-sub">${tN.length}</span>` : "—")
        : nats.reconnecting ? `<span class="dash-tile-reconnect">reconnecting…</span>`
        : `<span class="dash-tile-offline">offline</span>`,
      barPct: nats.connected ? tPct : 0, state: tState,
      meta: !to ? "транспорт не загружен"
           : nats.reconnecting ? "NATS восстанавливает связь"
           : !nats.connected ? "NATS не подключен"
           : (dead + silent > 0 ? [`${dead ? dead + " dead" : ""}`, `${silent ? silent + " silent" : ""}`].filter(Boolean).join(" · ")
              : tN.length ? "связь со всеми" : "агентов ещё нет"),
    }),
  ];
  refs.dashTiles.innerHTML = tiles.join("");
}

function tileHtml({ icon, label, value, barPct, state, meta }) {
  return `<div class="dash-tile state-${esc(state)}">
    <div class="dash-tile-header">
      <span class="dash-tile-label">${esc(label)}</span>
      <span class="dash-tile-icon">${esc(icon)}</span>
    </div>
    <div class="dash-tile-value">${value}</div>
    <div class="dash-tile-bar"><div class="dash-tile-bar-fill ${esc(state)}" style="width:${barPct}%"></div></div>
    <div class="dash-tile-meta">${esc(meta)}</div>
  </div>`;
}

/* ── Status banner ────────────────────────────────────── */
function renderDashBanner(issues) {
  if (!refs.dashBanner) return;
  const high = issues.filter((i) => i.severity === "high").length;
  const medium = issues.filter((i) => i.severity === "medium").length;
  const low = issues.filter((i) => i.severity === "low").length;
  let cls, icon, title, subtitle;
  if (!issues.length) {
    cls = "ok"; icon = "✓"; title = "Все системы работают штатно";
    const nodes = ((state.status && state.status.nodes) || []).filter((n) => !isEntryNode(n)).length;
    const routes = state.routes.length;
    subtitle = `${nodes} бэкендов · ${routes} маршрутов · NATS ${natsVisualState().label}`;
  } else if (high > 0) {
    cls = "bad"; icon = "⚠";
    title = `${high} критичн${plural(high, "ая проблема", "ых проблемы", "ых проблем")}${medium ? ` · ${medium} средн${plural(medium, "ее", "их", "их")}` : ""}${low ? ` · ${low} низк${plural(low, "ое", "их", "их")}` : ""}`;
    subtitle = issues[0] ? `Top: ${issues[0].title} — ${issues[0].detail}` : "";
  } else if (medium > 0) {
    cls = "warn"; icon = "⚠";
    title = `${medium} предупрежден${plural(medium, "ие", "ия", "ий")}${low ? ` · ${low} низк${plural(low, "ое", "их", "их")}` : ""}`;
    subtitle = issues[0] ? `${issues[0].title} — ${issues[0].detail}` : "";
  } else {
    cls = "info"; icon = "ℹ";
    title = `${low} замечани${plural(low, "е", "я", "й")}`;
    subtitle = issues[0] ? `${issues[0].title} — ${issues[0].detail}` : "";
  }
  refs.dashBanner.className = `dash-banner ${cls}`;
  refs.dashBanner.innerHTML = `
    <span class="dash-banner-icon">${icon}</span>
    <div class="dash-banner-text">
      <div class="dash-banner-title">${esc(title)}</div>
      ${subtitle ? `<div class="dash-banner-subtitle">${esc(subtitle)}</div>` : ""}
    </div>`;
}

function plural(n, one, few, many) {
  const mod100 = n % 100, mod10 = n % 10;
  if (mod100 >= 11 && mod100 <= 14) return many;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}

/* ── Quick actions ────────────────────────────────────── */
function renderDashQuickActions() {
  if (!refs.dashQuickActions) return;
  refs.dashQuickActions.innerHTML = `
    <button class="dash-quick-btn" data-qa="add-node"><span class="dqa-plus">+</span> Сервер</button>
    <button class="dash-quick-btn" data-qa="add-route"><span class="dqa-plus">+</span> Маршрут</button>
    <button class="dash-quick-btn" data-qa="add-plan"><span class="dqa-plus">+</span> Тариф</button>
    <button class="dash-quick-btn" data-qa="add-user"><span class="dqa-plus">+</span> Пользователь</button>
    <button class="dash-quick-btn dash-quick-btn-ghost" data-qa="ops">Операции →</button>
  `;
}

/* ── Issues ───────────────────────────────────────────── */
function collectIssues() {
  const issues = [];
  const nodes = (state.status && state.status.nodes) || [];

  nodes.forEach((n) => {
    if (isEntryNode(n)) return;
    if (!n.is_enabled) issues.push({ severity: "high", icon: "🖥", title: n.name, detail: "Отключен", target: { type: "node", id: n.id } });
    else if (!n.is_healthy) issues.push({ severity: "high", icon: "🖥", title: n.name, detail: "Нездоров", target: { type: "node", id: n.id } });
    else if (n.is_draining) issues.push({ severity: "medium", icon: "🖥", title: n.name, detail: "Draining", target: { type: "node", id: n.id } });
  });

  state.routes.forEach((r) => {
    if (r.health_status === "blocked") issues.push({ severity: "high", icon: "🛣", title: r.name, detail: "Маршрут заблокирован", target: { type: "routes" } });
    else if (r.health_status === "degraded") issues.push({ severity: "medium", icon: "🛣", title: r.name, detail: "Деградация", target: { type: "routes" } });
    else if (r.health_status === "suspected") issues.push({ severity: "low", icon: "🛣", title: r.name, detail: "Подозрение", target: { type: "routes" } });
  });

  /* Probe failures, consecutive-grouped */
  const probeByNode = {};
  state.probes.forEach((p) => {
    if (!p.node_id) return;
    if (!probeByNode[p.node_id]) probeByNode[p.node_id] = { fails: 0, consec: 0, counting: true };
    const e = probeByNode[p.node_id];
    if (!p.is_reachable) { e.fails++; if (e.counting) e.consec++; }
    else { e.counting = false; }
  });
  Object.entries(probeByNode).forEach(([nid, info]) => {
    if (info.consec >= 3) issues.push({ severity: "high", icon: "🔍", title: nodeNameById(nid) || shortId(nid), detail: `${info.consec} probe-сбоев подряд`, target: { type: "probes" } });
    else if (info.consec >= 1) issues.push({ severity: "low", icon: "🔍", title: nodeNameById(nid) || shortId(nid), detail: `${info.consec} probe fail`, target: { type: "probes" } });
  });

  (state.transportNodes || []).forEach((tn) => {
    if (tn.health_verdict === "dead") issues.push({ severity: "high", icon: "🚀", title: tn.name, detail: "Нет связи с агентом", target: { type: "transport" } });
    else if (tn.health_verdict === "silent") issues.push({ severity: "medium", icon: "🚀", title: tn.name, detail: "Агент молчит", target: { type: "transport" } });
  });

  if (state.transportOverview) {
    const failed = (state.transportOverview.outbox || {}).failed || 0;
    if (failed > 0) issues.push({ severity: failed > 5 ? "high" : "medium", icon: "📬", title: "Outbox", detail: `${failed} ошибок доставки в очереди`, target: { type: "transport" } });
    /* Only report NATS as an issue if we're past the reconnect grace — brief flaps shouldn't alarm. */
    const nats = natsVisualState();
    if (!nats.connected && !nats.reconnecting) {
      issues.unshift({ severity: "high", icon: "⚡", title: "NATS", detail: "Не подключен", target: { type: "transport" } });
    }
  }

  nodes.forEach((n) => {
    if (!isEntryNode(n)) return;
    if (!state.routes.some((r) => r.entry_node_id === n.id)) {
      issues.push({ severity: "low", icon: "🛰", title: n.name, detail: "Entry без маршрутов", target: { type: "node", id: n.id } });
    }
  });

  const order = { high: 0, medium: 1, low: 2 };
  issues.sort((a, b) => order[a.severity] - order[b.severity]);
  return issues;
}

function renderDashIssues(issues) {
  if (!refs.dashIssues) return;
  const sevLabel = { high: "high", medium: "med", low: "low" };
  if (refs.dashIssuesCount) refs.dashIssuesCount.textContent = issues.length ? String(issues.length) : "";

  if (!issues.length) {
    refs.dashIssues.innerHTML = `<div class="dash-empty">
      <div class="dash-empty-icon">✓</div>
      <div class="dash-empty-title">Ничего не горит</div>
      <div class="dash-empty-hint">Все ноды, маршруты и агенты работают штатно.</div>
    </div>`;
    refs.dashIssues._issues = [];
    return;
  }
  const visible = issues.slice(0, 12);
  const rest = issues.length - visible.length;
  refs.dashIssues.innerHTML = visible.map((i, idx) => `
    <button class="dash-issue" data-idx="${idx}">
      <span class="dash-issue-icon ${esc(i.severity)}">${esc(i.icon)}</span>
      <span class="dash-issue-body">
        <span class="dash-issue-title">${esc(i.title)}</span>
        <span class="dash-issue-detail">${esc(i.detail)}</span>
      </span>
      <span class="dash-issue-severity ${esc(i.severity)}">${esc(sevLabel[i.severity])}</span>
    </button>
  `).join("") + (rest > 0 ? `<div class="dash-issue-more muted">+ ещё ${rest} проблем${plural(rest, "а", "ы", "")}</div>` : "");
  refs.dashIssues._issues = visible;
}

/* ── Activity timeline ────────────────────────────────── */
function renderDashActivity() {
  if (!refs.dashActivity) return;
  const logs = state.logs || [];
  /* Stash refresher for pushLog to call when a new item lands. */
  refs.dashActivity._refresh = () => renderDashActivity();
  if (!logs.length) {
    refs.dashActivity.innerHTML = `<div class="dash-empty">
      <div class="dash-empty-icon">📋</div>
      <div class="dash-empty-title">Пока тихо</div>
      <div class="dash-empty-hint">Здесь появится лента ваших операций.</div>
    </div>`;
    return;
  }
  refs.dashActivity.innerHTML = logs.slice(0, 15).map((item) => {
    const iconCls = item.isError ? "bad" : "ok";
    const icon = item.isError ? "✕" : "✓";
    const raw = typeof item.payload === "string" ? item.payload : JSON.stringify(item.payload);
    const short = raw.length > 120 ? raw.slice(0, 120) + "…" : raw;
    return `<div class="dash-activity-item${item.isError ? " error" : ""}">
      <span class="dash-activity-icon ${iconCls}">${icon}</span>
      <div class="dash-activity-body">
        <div class="dash-activity-title">${esc(item.title)}</div>
        <div class="dash-activity-meta"><span>${esc(item.at)}</span>${short ? ` · <span class="mono">${esc(short)}</span>` : ""}</div>
      </div>
    </div>`;
  }).join("");
}

/* ── Compact status strip ─────────────────────────────── */
function renderDashCompact() {
  if (!refs.dashCompact) return;
  const readiness = state.readiness ? (state.readiness.checks || []) : [];
  const routeDist = { healthy: 0, degraded: 0, suspected: 0, blocked: 0, warming_up: 0 };
  state.routes.forEach((r) => { if (Object.prototype.hasOwnProperty.call(routeDist, r.health_status)) routeDist[r.health_status]++; });
  const to = state.transportOverview;
  const tN = state.transportNodes || [];
  const tCounts = { ok: 0, lag: 0, silent: 0, dead: 0 };
  tN.forEach((n) => { tCounts[n.health_verdict] = (tCounts[n.health_verdict] || 0) + 1; });

  const cards = [];

  cards.push(`<div class="dash-compact-card">
    <div class="dash-compact-title">Readiness</div>
    <div class="dash-compact-chips">${
      readiness.length
        ? readiness.map((c) => chip(c.ok ? "ok" : "bad", c.name)).join("")
        : '<span class="muted">нет данных</span>'
    }</div>
  </div>`);

  const routeChips = Object.keys(routeDist).filter((k) => routeDist[k] > 0).map((k) => {
    const cls = k === "healthy" ? "ok" : (k === "blocked" ? "bad" : "warn");
    return chip(cls, `${routeStatusLabel(k)}: ${routeDist[k]}`);
  });
  cards.push(`<div class="dash-compact-card">
    <div class="dash-compact-title">Маршруты</div>
    <div class="dash-compact-chips">${routeChips.join("") || '<span class="muted">маршрутов нет</span>'}</div>
  </div>`);

  if (to) {
    const nats = natsVisualState();
    const tChips = [
      `<span class="badge ${nats.cls}"><span class="dot ${nats.cls}" style="width:6px;height:6px;margin-right:4px"></span>NATS ${nats.label}</span>`,
      ...Object.keys(tCounts).filter((k) => tCounts[k] > 0).map((k) => {
        const cls = k === "ok" ? "ok" : (k === "dead" ? "bad" : "warn");
        return chip(cls, `${k}: ${tCounts[k]}`);
      }),
    ];
    cards.push(`<div class="dash-compact-card">
      <div class="dash-compact-title">Transport</div>
      <div class="dash-compact-chips">${tChips.join("")}</div>
    </div>`);
  } else {
    cards.push(`<div class="dash-compact-card">
      <div class="dash-compact-title">Transport</div>
      <div class="dash-compact-chips"><span class="muted">не загружен</span></div>
    </div>`);
  }

  refs.dashCompact.innerHTML = cards.join("");
}

/* ── Ops dropdowns population (kept from old overview) ── */
function populateOpsDropdowns() {
  const opsNodes = ((state.status && state.status.nodes) || []).filter((n) => String(n.role || "").toLowerCase() === "backend");
  document.querySelectorAll(".ops-node-select").forEach((sel) => {
    const current = sel.value;
    const firstOpt = sel.querySelector("option:first-child");
    const firstLabel = firstOpt ? firstOpt.textContent : "";
    sel.innerHTML = `<option value="">${esc(firstLabel)}</option>` + opsNodes.map((n) => `<option value="${esc(n.id)}"${n.id === current ? " selected" : ""}>${esc(n.name)} (${esc(shortId(n.id))})</option>`).join("");
  });
  document.querySelectorAll(".ops-route-select").forEach((sel) => {
    const current = sel.value;
    const firstOpt = sel.querySelector("option:first-child");
    const firstLabel = firstOpt ? firstOpt.textContent : "";
    sel.innerHTML = `<option value="">${esc(firstLabel)}</option>` + state.routes.map((r) => `<option value="${esc(r.id)}"${r.id === current ? " selected" : ""}>${esc(r.name)} (${esc(shortId(r.id))})</option>`).join("");
  });
}
