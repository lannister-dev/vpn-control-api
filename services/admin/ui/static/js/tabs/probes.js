import { state, refs, $ } from '../state.js';
import { esc, chip, uuidCell, shortId, fmtDate, relTime, nodeNameById, sortTh, sortedBy } from '../utils.js';
import { req } from '../api.js';
import { notify, renderPagination } from '../ui.js';

/* ── Load probes ────────────────────────────────────── */
export async function loadProbes() {
  const params = new URLSearchParams();
  params.set("limit", String(state.probesLimit));
  const nodeFilter = refs.probesSearch.value.trim();
  if (nodeFilter && nodeFilter.match(/^[0-9a-f-]{36}$/i)) params.set("node_id", nodeFilter);
  const sourceFilter = refs.probesSource.value;
  if (sourceFilter) params.set("source", sourceFilter);
  const data = await req(`/api/v1/probe/reports/recent?${params}`);
  state.probesAll = Array.isArray(data) ? data : (data.items || []);
  state.probesTotal = state.probesAll.length;
  populateProbeSourceFilter();
  renderProbes();
}

/* ── Populate source filter ─────────────────────────── */
function populateProbeSourceFilter() {
  const sources = new Set();
  state.probesAll.forEach((p) => { if (p.source) sources.add(p.source); });
  const current = refs.probesSource.value;
  const opts = [`<option value="">Все источники</option>`].concat(
    [...sources].sort().map((s) => `<option value="${esc(s)}"${s === current ? " selected" : ""}>${esc(s)}</option>`)
  );
  refs.probesSource.innerHTML = opts.join("");
}

/* ── Filtered probes ────────────────────────────────── */
export function filteredProbes() {
  const statusF = refs.probesStatus.value;
  const kindF = refs.probesKind.value;
  const q = refs.probesSearch.value.trim().toLowerCase();
  return state.probesAll.filter((p) => {
    if (statusF === "failed" && p.is_reachable) return false;
    if (statusF === "ok" && !p.is_reachable) return false;
    if (kindF && p.probe_kind !== kindF) return false;
    if (q && !q.match(/^[0-9a-f-]{36}$/i)) {
      const hay = [p.source, p.node_id, p.route_id, p.error, p.target_host, p.transport_kind, p.error_phase].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

/* ── Comparators ────────────────────────────────────── */
export const probeComparators = {
  source: (a, b) => (a.source || "").localeCompare(b.source || ""),
  node: (a, b) => (nodeNameById(a.node_id) || a.node_id || "").localeCompare(nodeNameById(b.node_id) || b.node_id || ""),
  status: (a, b) => (a.is_reachable === b.is_reachable ? 0 : a.is_reachable ? -1 : 1),
  latency: (a, b) => ((a.latency_ms || 0) - (b.latency_ms || 0)),
  time: (a, b) => (new Date(a.checked_at || 0).getTime() - new Date(b.checked_at || 0).getTime()),
};

/* ── Render probes ──────────────────────────────────── */
export function renderProbes() {
  const all = state.probesAll;
  const failCount = all.filter((p) => !p.is_reachable).length;
  const okCount = all.filter((p) => p.is_reachable).length;
  const sources = new Set(all.map((p) => p.source));
  refs.probesMeta.innerHTML = `${chip("info", "всего: " + all.length)} ${chip("ok", "доступных: " + okCount)} ${chip("bad", "сбоев: " + failCount)} ${chip("warn", "источников: " + sources.size)}`;

  /* Node summary — group failures by node, show consecutive failures */
  const nodeFailMap = {};
  all.forEach((p) => {
    if (!p.node_id) return;
    if (!nodeFailMap[p.node_id]) nodeFailMap[p.node_id] = { total: 0, fails: 0, consecutive: 0, counting: true, lastFail: null, latencies: [] };
    const entry = nodeFailMap[p.node_id];
    entry.total++;
    if (p.latency_ms != null && p.is_reachable) entry.latencies.push(p.latency_ms);
    if (!p.is_reachable) {
      entry.fails++;
      if (!entry.lastFail) entry.lastFail = p;
      if (entry.counting) entry.consecutive++;
    } else {
      entry.counting = false;
    }
  });
  const problemNodes = Object.entries(nodeFailMap)
    .filter(([, v]) => v.fails > 0)
    .sort(([, a], [, b]) => b.consecutive - a.consecutive);
  if (problemNodes.length) {
    refs.probesNodeSummary.innerHTML = `<div class="card"><div class="card-title"><span class="card-icon red">\u2718</span> Проблемные ноды по probe</div><div class="stack">${problemNodes.map(([nodeId, v]) => {
      const nName = nodeNameById(nodeId) || shortId(nodeId);
      const avgLat = v.latencies.length ? Math.round(v.latencies.reduce((a, b) => a + b, 0) / v.latencies.length) : null;
      const consChip = v.consecutive >= 3 ? chip("bad", v.consecutive + " подряд") : (v.consecutive >= 1 ? chip("warn", v.consecutive + " подряд") : "");
      return `<div style="display:flex;align-items:center;gap:8px;font-size:12px"><strong>${esc(nName)}</strong> ${uuidCell(nodeId)} ${chip("bad", v.fails + "/" + v.total + " failed")} ${consChip}${avgLat !== null ? ` <span class="muted">avg ${avgLat}ms</span>` : ""}${v.lastFail && v.lastFail.error ? ` <span class="muted" style="font-size:11px">${esc(v.lastFail.error)}</span>` : ""}</div>`;
    }).join("")}</div></div>`;
  } else {
    refs.probesNodeSummary.innerHTML = "";
  }

  refs.probesHead.innerHTML = `<tr>${sortTh("probes", "source", "Источник")}${sortTh("probes", "node", "Нода")}<th>Маршрут</th><th>Тип</th>${sortTh("probes", "status", "Статус")}${sortTh("probes", "latency", "Latency")}<th>Фаза ошибки</th><th>Ошибка</th>${sortTh("probes", "time", "Время")}</tr>`;
  const filtered = filteredProbes();
  const page = filtered.slice(state.probesOffset, state.probesOffset + state.probesLimit);
  const sorted = sortedBy(page, "probes", probeComparators);
  refs.probesBody.innerHTML = sorted.length
    ? sorted.map((p) => {
      const nName = nodeNameById(p.node_id);
      const rName = p.route_id ? (state.routes.find((r) => r.id === p.route_id) || {}).name : null;
      const probeNode = ((state.status && state.status.nodes) || []).find((n) => n.id === p.node_id);
      const probeRole = probeNode ? String(probeNode.role || "").toLowerCase() : "";
      const viaEntry = probeRole === "entry" || probeRole === "whitelist_entry";
      const statusChip = p.is_reachable ? chip("ok", "OK") : chip("bad", "FAIL");
      const baseKind = p.probe_kind === "synthetic_vpn" ? "Synthetic" : "TCP";
      const kindLabel = p.probe_kind === "synthetic_vpn"
        ? (viaEntry ? `${baseKind} · via entry` : `${baseKind} · direct`)
        : baseKind;
      const tLabel = p.transport_kind || "";
      const latency = p.latency_ms != null ? `<span class="mono">${p.latency_ms}ms</span>` : `<span class="muted">-</span>`;
      const errorPhase = p.error_phase ? chip("warn", p.error_phase) : `<span class="muted">-</span>`;
      const rowStyle = p.is_reachable ? "" : ' style="background:rgba(255,127,133,0.04)"';
      return `<tr${rowStyle}><td>${chip("info", p.source)}</td><td>${nName ? `<strong>${esc(nName)}</strong> ` : ""}${uuidCell(p.node_id)}</td><td>${rName ? `${esc(rName)} ` : ""}${p.route_id ? uuidCell(p.route_id) : '<span class="muted">node-scope</span>'}</td><td>${esc(kindLabel)}${tLabel ? `<div class="muted" style="font-size:10px">${esc(tLabel)}</div>` : ""}</td><td>${statusChip}</td><td>${latency}</td><td>${errorPhase}</td><td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(p.error || "")}">${p.error ? `<span style="font-size:11px">${esc(p.error)}</span>` : '<span class="muted">-</span>'}</td><td><span title="${esc(fmtDate(p.checked_at))}">${relTime(p.checked_at)}</span></td></tr>`;
    }).join("")
    : `<tr><td colspan="9" class="empty">Нет probe-сигналов по фильтрам.</td></tr>`;
  renderPagination(refs.probesPagination, filtered.length, state.probesLimit, state.probesOffset, (page) => {
    state.probesOffset = page * state.probesLimit;
    renderProbes();
  });
}

/* ── Bind probe event listeners ─────────────────────── */
export function bindProbeEvents() {
  refs.probesReload.addEventListener("click", () => { state.probesOffset = 0; loadProbes().catch((e) => notify("Ошибка загрузки probe: " + e.message, true)); });
  refs.probesSearch.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); refs.probesReload.click(); } });
  refs.probesStatus.addEventListener("change", () => { state.probesOffset = 0; renderProbes(); });
  refs.probesKind.addEventListener("change", () => { state.probesOffset = 0; renderProbes(); });
  refs.probesSource.addEventListener("change", () => { state.probesOffset = 0; refs.probesReload.click(); });
}
