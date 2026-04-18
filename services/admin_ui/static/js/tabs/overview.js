import { state, refs, $ } from '../state.js';
import {
  esc, fmtDate, chip, uuidCell, shortId, nodeGeo, nodeNameById,
  routeStatusLabel, formatNumber, latestProbeForNode, probeChip,
  nodeRoleLabel, nodeRoleClass,
} from '../utils.js';

/**
 * renderOverview(render)
 *
 * Populates the overview / dashboard KPIs, readiness list, route health
 * distribution, probe failure grouping, node alerts, unused entry nodes,
 * transport KPI on dashboard, and ops dropdown population.
 *
 * @param {Function} render - the main render() callback, used only for
 *   re-rendering after ops dropdown population (currently unused but kept
 *   for symmetry).
 */
export function renderOverview(render) {
  /* KPI cards */
  if (state.status) {
    const t = state.status.totals || {};
    refs.kpiNodes.textContent = formatNumber(t.nodes_total || 0);
    refs.kpiHealthy.textContent = formatNumber(t.nodes_healthy || 0);
    refs.kpiDraining.textContent = formatNumber(t.nodes_draining || 0);
    refs.kpiPlacements.textContent = formatNumber(t.placements_total || 0);
  }
  refs.kpiRoutes.textContent = formatNumber(state.routes.length || 0);
  refs.kpiProbeFail.textContent = formatNumber(state.probes.filter((p) => !p.is_reachable).length || 0);

  /* Transport KPI on dashboard */
  const to = state.transportOverview;
  if (to) {
    const natsLabel = to.nats_connected ? "Online" : "Offline";
    $("kpi-nats").innerHTML = `<span class="dot ${to.nats_connected ? "ok" : "bad"}" style="width:7px;height:7px"></span> ${esc(natsLabel)}`;
    const counts = { ok: 0, lag: 0, silent: 0, dead: 0 };
    state.transportNodes.forEach((n) => { counts[n.health_verdict] = (counts[n.health_verdict] || 0) + 1; });
    const failedOutbox = (to.outbox || {}).failed || 0;
    const alerts = [];
    if (counts.dead > 0) alerts.push(chip("bad", `${counts.dead} dead`));
    if (counts.silent > 0) alerts.push(chip("warn", `${counts.silent} silent`));
    if (counts.lag > 0) alerts.push(chip("warn", `${counts.lag} lag`));
    if (counts.ok > 0) alerts.push(chip("ok", `${counts.ok} ok`));
    if (failedOutbox > 0) alerts.push(chip("bad", `${failedOutbox} outbox failed`));
    $("transport-alert-list").innerHTML = alerts.length ? alerts.join(" ") : `<div class="empty">Transport healthy.</div>`;
  } else {
    $("kpi-nats").textContent = "-";
    $("transport-alert-list").innerHTML = `<div class="empty">Transport data not loaded.</div>`;
  }

  /* Readiness list */
  refs.readinessList.innerHTML = state.readiness
    ? ((state.readiness.checks || []).map((c) => `<div class="card">${chip(c.ok ? "ok" : "bad", c.name)}<div class="muted">${esc(c.detail)}</div></div>`).join("") || `<div class="empty">Проверок нет.</div>`)
    : `<div class="empty">Данные readiness отсутствуют.</div>`;

  /* Route health distribution */
  const rc = { healthy: 0, degraded: 0, suspected: 0, blocked: 0, warming_up: 0 };
  state.routes.forEach((r) => { if (Object.prototype.hasOwnProperty.call(rc, r.health_status)) rc[r.health_status] += 1; });
  refs.routeHealthList.innerHTML = Object.keys(rc).map((s) => `<div class="card">${chip(s === "healthy" ? "ok" : (s === "blocked" ? "bad" : "warn"), routeStatusLabel(s))} <span class="mono">${rc[s]}</span></div>`).join("");

  /* Group probe failures by node */
  const probeByNode = {};
  state.probes.forEach((p) => {
    if (!p.node_id) return;
    if (!probeByNode[p.node_id]) probeByNode[p.node_id] = { fails: 0, total: 0, consecutive: 0, counting: true, lastError: null, lastChecked: null };
    const e = probeByNode[p.node_id];
    e.total++;
    if (!p.is_reachable) {
      e.fails++;
      if (!e.lastError) { e.lastError = p.error || "unreachable"; e.lastChecked = p.checked_at; }
      if (e.counting) e.consecutive++;
    } else { e.counting = false; }
  });
  const failedNodes = Object.entries(probeByNode).filter(([, v]) => v.fails > 0).sort(([, a], [, b]) => b.consecutive - a.consecutive);
  refs.probeFailList.innerHTML = failedNodes.length
    ? failedNodes.slice(0, 10).map(([nodeId, v]) => {
      const nName = nodeNameById(nodeId) || shortId(nodeId);
      const consLabel = v.consecutive >= 3 ? chip("bad", v.consecutive + " подряд") : (v.consecutive >= 1 ? chip("warn", v.consecutive + " подряд") : "");
      return `<div class="card"><strong>${esc(nName)}</strong> ${uuidCell(nodeId)} ${chip("bad", v.fails + "/" + v.total + " failed")} ${consLabel}<div class="muted">${esc(v.lastError)} | ${fmtDate(v.lastChecked)}</div></div>`;
    }).join("")
    : `<div class="empty">Сбоев probe не найдено.</div>`;

  /* Node alerts + unused entry nodes */
  const allNodes = (state.status && state.status.nodes) || [];
  const alertNodes = allNodes.filter((n) => {
    const isEntry = ["whitelist_entry", "entry"].includes(String(n.role || "").toLowerCase());
    if (isEntry) return false;
    return !n.is_healthy || n.is_draining || !n.is_enabled;
  }).slice(0, 10);
  const unusedEntryNodes = allNodes.filter((n) => {
    if (!["whitelist_entry", "entry"].includes(String(n.role || "").toLowerCase())) return false;
    return !state.routes.some((r) => r.entry_node_id === n.id);
  });
  const alertHtml = alertNodes.map((n) => { const g = nodeGeo(n.region); return `<div class="card"><div><strong>${esc(n.name)}</strong></div><div class="geo"><span class="flag">${esc(g.flag)}</span>${esc(g.country)}</div><div>${uuidCell(n.id)}</div><div>${n.is_healthy ? "" : chip("bad", "Нездоров")} ${n.is_draining ? chip("warn", "Draining") : ""} ${!n.is_enabled ? chip("bad", "Отключен") : ""}</div></div>`; }).join("");
  const entryAlertHtml = unusedEntryNodes.map((n) => { const g = nodeGeo(n.region); return `<div class="card"><div><strong>${esc(n.name)}</strong></div><div class="geo"><span class="flag">${esc(g.flag)}</span>${esc(g.country)}</div><div>${uuidCell(n.id)}</div><div>${chip("warn", "Entry без маршрутов")}</div></div>`; }).join("");
  refs.nodeAlertList.innerHTML = (alertHtml + entryAlertHtml) || `<div class="empty">Проблемных серверов не обнаружено.</div>`;

  /* Populate ops dropdowns */
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
