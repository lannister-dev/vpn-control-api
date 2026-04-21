import { state, refs } from '../state.js';
import { esc, nodeGeo, shortId, relTime } from '../utils.js';
import { openModal } from '../ui.js';

const SEV = { ok: 0, idle: 1, warn: 2, bad: 3 };
const worstOf = (...severities) =>
  severities.reduce((acc, s) => (SEV[s] > SEV[acc] ? s : acc), "ok");

const PROBE_FRESH_SEC = 120;
const PROBE_STALE_SEC = 600;

function _latestProbe(predicate) {
  const all = (state.probes || []).concat(state.probesAll || []);
  let best = null;
  for (const p of all) {
    if (!predicate(p)) continue;
    if (!best || new Date(p.checked_at) > new Date(best.checked_at)) best = p;
  }
  return best;
}

function _probeStatus(probe) {
  if (!probe) return "idle";
  const ageSec = (Date.now() - new Date(probe.checked_at).getTime()) / 1000;
  if (!probe.is_reachable) return "bad";
  if (ageSec > PROBE_STALE_SEC) return "idle";
  if (ageSec > PROBE_FRESH_SEC) return "warn";
  return "ok";
}

function _nodeStatus(node) {
  if (!node) return "idle";
  if (!node.is_active || !node.is_enabled) return "bad";
  if (node.is_draining) return "warn";
  if (node.is_healthy === false) return "bad";
  return "ok";
}

function _routeStatus(route) {
  const hs = String(route.health_status || "").toLowerCase();
  if (hs === "healthy") return "ok";
  if (hs === "warming_up") return "warn";
  if (hs === "degraded" || hs === "suspected") return "warn";
  if (hs === "blocked") return "bad";
  return "idle";
}

/* ── Datalayer ──────────────────────────────────────── */
export function buildTopologyGraph() {
  const nodes = (state.status && state.status.nodes) || [];
  const nodesById = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const routes = state.routes || [];
  const profiles = state.transportProfiles || [];
  const profilesById = Object.fromEntries(profiles.map((p) => [p.id, p]));

  const probeSources = new Set();
  for (const p of (state.probes || []).concat(state.probesAll || [])) {
    if (p.source) probeSources.add(p.source);
  }

  const byBackend = new Map();
  for (const r of routes) {
    if (!r || !r.is_active) continue;
    const backendNode = nodesById[r.node_id];
    if (!backendNode) continue;
    if (!byBackend.has(backendNode.id)) {
      byBackend.set(backendNode.id, {
        backend: backendNode,
        directRoutes: [],
        entryRoutes: [],
      });
    }
    const bucket = byBackend.get(backendNode.id);
    if (r.entry_node_id) bucket.entryRoutes.push(r);
    else bucket.directRoutes.push(r);
  }

  const chains = [];
  for (const { backend, directRoutes, entryRoutes } of byBackend.values()) {
    const backendDirectProbe = _latestProbe(
      (p) => p.node_id === backend.id && p.probe_kind === "synthetic_vpn" && p.source && p.source.includes("backend"),
    );
    const backendEntryProbe = _latestProbe(
      (p) => p.node_id === backend.id && p.probe_kind === "synthetic_vpn" && p.source && p.source.includes("entry"),
    );
    const backendStatus = _nodeStatus(backend);

    for (const route of directRoutes) {
      const tp = profilesById[route.transport_profile_id];
      const routeStat = _routeStatus(route);
      const probe = backendEntryProbe || backendDirectProbe;
      const probeStat = _probeStatus(probe);
      chains.push({
        kind: "direct",
        backend,
        route,
        transportProfile: tp,
        probeSources: Array.from(probeSources),
        probe,
        nodes: [
          { id: `probe:${route.id}`, type: "probe", label: "Probe (РФ)", status: probeStat, meta: probe ? { latency: probe.latency_ms, age: probe.checked_at, reachable: probe.is_reachable, source: probe.source } : null },
          { id: `backend:${backend.id}`, type: "backend", label: backend.name, status: worstOf(backendStatus, routeStat), data: backend, meta: { role: backend.role, region: backend.region, route_name: route.name, route_health: route.health_status, weight: route.effective_weight } },
          { id: `profile:${route.id}`, type: "profile", label: tp ? tp.name : "profile?", status: tp ? "ok" : "bad", data: tp },
        ],
        status: worstOf(probeStat, backendStatus, routeStat),
      });
    }

    for (const route of entryRoutes) {
      const entry = nodesById[route.entry_node_id];
      const tp = profilesById[route.transport_profile_id];
      if (!entry) continue;
      const entryStat = _nodeStatus(entry);
      const entryProbe = _latestProbe(
        (p) => p.node_id === entry.id && (p.probe_kind === "synthetic_vpn" || p.probe_kind === "tcp_connect"),
      );
      const entryProbeStat = _probeStatus(entryProbe);
      const routeStat = _routeStatus(route);
      chains.push({
        kind: "via_entry",
        backend,
        entry,
        route,
        transportProfile: tp,
        probe: entryProbe,
        nodes: [
          { id: `probe:${route.id}`, type: "probe", label: "Probe (РФ)", status: entryProbeStat, meta: entryProbe ? { latency: entryProbe.latency_ms, age: entryProbe.checked_at, reachable: entryProbe.is_reachable, source: entryProbe.source, probe_kind: entryProbe.probe_kind } : null },
          { id: `entry:${entry.id}:${route.id}`, type: "entry", label: entry.name, status: worstOf(entryStat, entryProbeStat), data: entry, meta: { role: entry.role, region: entry.region } },
          { id: `backend:${backend.id}:${route.id}`, type: "backend", label: backend.name, status: worstOf(backendStatus, routeStat), data: backend, meta: { role: backend.role, region: backend.region, route_name: route.name, weight: route.effective_weight, route_health: route.health_status } },
          { id: `profile:${route.id}`, type: "profile", label: tp ? tp.name : "profile?", status: tp ? "ok" : "bad", data: tp },
        ],
        status: worstOf(entryProbeStat, entryStat, backendStatus, routeStat),
      });
    }
  }

  chains.sort((a, b) => SEV[b.status] - SEV[a.status] || a.backend.name.localeCompare(b.backend.name));
  return chains;
}

/* ── Render ─────────────────────────────────────────── */
const LANE_GAP_X = 220;
const LANE_PAD_X = 40;
const ROW_H = 92;
const ROW_GAP = 14;
const NODE_W = 176;
const NODE_H = 64;

function renderTopology() {
  if (!refs.topoCanvas) return;
  let chains = buildTopologyGraph();
  if (state.topoOnlyIssues) chains = chains.filter((c) => c.status !== "ok");

  if (!chains.length) {
    refs.topoCanvas.innerHTML = "";
    refs.topoEmpty.style.display = "";
    refs.topoEmpty.textContent = state.topoOnlyIssues
      ? "Нет проблемных маршрутов — всё зелёное."
      : "Нет активных маршрутов.";
    return;
  }
  refs.topoEmpty.style.display = "none";

  const maxCols = Math.max(...chains.map((c) => c.nodes.length));
  const widthPx = LANE_PAD_X * 2 + maxCols * NODE_W + (maxCols - 1) * (LANE_GAP_X - NODE_W);
  const heightPx = chains.length * ROW_H + (chains.length + 1) * ROW_GAP;

  const rowSvgs = chains.map((chain, rowIdx) => {
    const y = ROW_GAP + rowIdx * (ROW_H + ROW_GAP);
    const centerY = y + ROW_H / 2;
    const nodeSvgs = chain.nodes.map((n, i) => {
      const x = LANE_PAD_X + i * LANE_GAP_X;
      return _nodeCard(n, x, centerY - NODE_H / 2, chain);
    }).join("");

    const edgeSvgs = chain.nodes.slice(1).map((_, i) => {
      const from = chain.nodes[i];
      const to = chain.nodes[i + 1];
      const x1 = LANE_PAD_X + i * LANE_GAP_X + NODE_W;
      const x2 = LANE_PAD_X + (i + 1) * LANE_GAP_X;
      const edgeStatus = worstOf(from.status, to.status);
      return _edge(x1, centerY, x2, centerY, edgeStatus);
    }).join("");

    const chainColor = `topo-chain-${chain.status}`;
    return `<g class="topo-row ${chainColor}" data-chain-idx="${rowIdx}">${edgeSvgs}${nodeSvgs}</g>`;
  }).join("");

  refs.topoCanvas.innerHTML = `
    <svg viewBox="0 0 ${widthPx} ${heightPx}" preserveAspectRatio="xMidYMin meet" class="topo-svg" style="min-height:${heightPx}px">
      <defs>
        <marker id="topo-arrow-ok" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#22c55e"/></marker>
        <marker id="topo-arrow-warn" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#f59e0b"/></marker>
        <marker id="topo-arrow-bad" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#ef4444"/></marker>
        <marker id="topo-arrow-idle" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b"/></marker>
      </defs>
      ${rowSvgs}
    </svg>
  `;
}

function _nodeCard(node, x, y, chain) {
  const icon = { probe: "🛰", entry: "🛡", backend: "🖥", profile: "⚙" }[node.type] || "•";
  const sub = node.type === "profile" ? (node.data ? `${node.data.security}/${node.data.network}` : "")
    : node.type === "backend" ? (node.data ? (nodeGeo(node.data.region).flag + " " + nodeGeo(node.data.region).country) : "")
    : node.type === "entry" ? (node.data ? (nodeGeo(node.data.region).flag + " " + node.data.role) : "")
    : node.type === "probe" ? (node.meta && node.meta.source ? node.meta.source : "")
    : "";
  const latency = node.meta && node.meta.latency != null ? `<tspan class="topo-meta">${node.meta.latency}ms</tspan>` : "";
  return `
    <g class="topo-node topo-node-${node.status}" data-node-id="${esc(node.id)}" transform="translate(${x},${y})">
      <rect class="topo-node-bg" width="${NODE_W}" height="${NODE_H}" rx="12" />
      <circle class="topo-node-dot" cx="14" cy="14" r="6"/>
      <text class="topo-node-icon" x="26" y="19">${icon}</text>
      <text class="topo-node-title" x="14" y="38">${esc(_truncate(node.label, 20))}</text>
      <text class="topo-node-sub" x="14" y="54">${esc(sub)} ${latency}</text>
    </g>
  `;
}

function _edge(x1, y1, x2, y2, status) {
  const mx = (x1 + x2) / 2;
  const path = `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
  return `<path class="topo-edge topo-edge-${status}" d="${path}" marker-end="url(#topo-arrow-${status})"/>`;
}

function _truncate(s, n) {
  s = String(s || "");
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

/* ── Detail drawer on click ─────────────────────────── */
function _openDetail(node, chain) {
  const meta = node.meta || {};
  const rows = [];
  if (node.data) {
    if (node.type === "backend" || node.type === "entry") {
      rows.push(["Роль", node.data.role]);
      rows.push(["Регион", node.data.region]);
      rows.push(["Статус", node.data.is_active ? (node.data.is_draining ? "draining" : (node.data.is_enabled ? "active" : "disabled")) : "inactive"]);
      if (node.data.is_healthy !== undefined) rows.push(["Healthy", String(node.data.is_healthy)]);
      if (node.data.public_domain) rows.push(["Public domain", node.data.public_domain]);
      if (node.data.reality_ip) rows.push(["Reality IP", node.data.reality_ip]);
    }
    if (node.type === "profile") {
      rows.push(["Protocol", `${node.data.security}/${node.data.network}`]);
      if (node.data.reality_server_name) rows.push(["SNI", node.data.reality_server_name]);
      if (node.data.port) rows.push(["Port", node.data.port]);
    }
  }
  if (meta.route_name) rows.push(["Route name", meta.route_name]);
  if (meta.route_health) rows.push(["Route health", meta.route_health]);
  if (meta.weight != null) rows.push(["Weight", meta.weight]);
  if (node.type === "probe" && meta.source) {
    rows.push(["Source", meta.source]);
    rows.push(["Reachable", String(meta.reachable)]);
    if (meta.latency != null) rows.push(["Latency", `${meta.latency} ms`]);
    if (meta.age) rows.push(["Checked", relTime(meta.age)]);
    if (meta.probe_kind) rows.push(["Kind", meta.probe_kind]);
  }

  const bodyHtml = `
    <div class="card" style="margin-bottom:10px">
      <div class="card-title">${esc(node.label)} <span class="muted" style="font-size:11px;margin-left:8px">${esc(node.type)} · <span class="topo-chip topo-chip-${node.status}">${node.status}</span></span></div>
    </div>
    <table class="data-table">${rows.map(([k, v]) => `<tr><th style="text-align:left;padding:4px 10px 4px 0">${esc(k)}</th><td>${esc(String(v))}</td></tr>`).join("")}</table>
    <div class="muted" style="font-size:11px;margin-top:10px">Chain: ${esc(chain.kind)} · ${esc(chain.backend.name)}${chain.entry ? " через " + esc(chain.entry.name) : ""}</div>
  `;
  openModal({
    title: `${node.label}`,
    bodyHtml,
    footerHtml: `<button class="btn btn-ghost" data-act="close">Закрыть</button>`,
    onMount: ({ root, close }) => {
      root.querySelector('[data-act="close"]').addEventListener("click", close);
    },
  });
}

/* ── Events ─────────────────────────────────────────── */
export function bindTopologyEvents() {
  if (refs.routesViewToggle) {
    refs.routesViewToggle.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-routes-view]");
      if (!btn) return;
      const view = btn.dataset.routesView;
      state.routesView = view;
      refs.routesViewToggle.querySelectorAll("[data-routes-view]").forEach((b) =>
        b.classList.toggle("active", b.dataset.routesView === view),
      );
      refs.routesViewList.hidden = view !== "list";
      refs.routesViewTopology.hidden = view !== "topology";
      if (view === "topology") renderTopology();
    });
  }
  if (refs.topoOnlyIssues) {
    refs.topoOnlyIssues.addEventListener("change", () => {
      state.topoOnlyIssues = refs.topoOnlyIssues.checked;
      renderTopology();
    });
  }
  if (refs.topoCanvas) {
    refs.topoCanvas.addEventListener("click", (ev) => {
      const nodeEl = ev.target.closest("[data-node-id]");
      if (!nodeEl) return;
      const chainEl = nodeEl.closest("[data-chain-idx]");
      if (!chainEl) return;
      const chains = buildTopologyGraph().filter((c) => !state.topoOnlyIssues || c.status !== "ok");
      const chain = chains[Number(chainEl.dataset.chainIdx)];
      if (!chain) return;
      const node = chain.nodes.find((n) => n.id === nodeEl.dataset.nodeId);
      if (!node) return;
      _openDetail(node, chain);
    });
  }
}

export function rerenderTopologyIfVisible() {
  if (state.routesView === "topology") renderTopology();
}
