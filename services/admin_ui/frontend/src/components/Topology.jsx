import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "./Icon.jsx";
import { nodeGeo } from "../lib/geo.js";
import { nodeLoad } from "../lib/nodeLoad.js";

function edgeStatusClass(s) {
  if (s === "healthy") return "active";
  if (s === "degraded" || s === "suspected") return "warn";
  if (s === "warming_up") return "info";
  if (s === "blocked") return "bad";
  return "";
}

export function Topology({ routes = [], nodes = [], probes = [], userCountByBackendName = {}, liveByBackendName = {}, liveByEntryId = {}, usersByEntryId = {}, onOpenNode }) {
  const canvasRef = useRef(null);
  const [edges, setEdges] = useState([]);
  const [focus, setFocus] = useState(null);
  const [focusedRoute, setFocusedRoute] = useState(null);
  const [hoverEdge, setHoverEdge] = useState(null);
  const [onlyProblems, setOnlyProblems] = useState(false);

  const nodesById = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);
  const entries = useMemo(() => nodes.filter((n) => n.role === "entry" || n.role === "whitelist_entry"), [nodes]);
  const backends = useMemo(() => nodes.filter((n) => n.role === "backend"), [nodes]);

  const latencyByBackend = useMemo(() => {
    const map = {};
    for (const p of probes) {
      if (p.probe_kind !== "synthetic_vpn" || !p.is_reachable) continue;
      const cur = map[p.node_id];
      if (!cur || new Date(p.checked_at) > new Date(cur.checked_at)) map[p.node_id] = p;
    }
    const out = {};
    for (const [id, p] of Object.entries(map)) out[id] = p.latency_ms;
    return out;
  }, [probes]);

  const enrichedRoutes = useMemo(() =>
    routes
      .filter((r) => r.entry_node_id && r.node_id)
      .map((r) => {
        const entryNode = nodesById[r.entry_node_id];
        const backendNode = nodesById[r.node_id];
        const endpointBlocked =
          (entryNode && (!entryNode.is_enabled || entryNode.is_draining || entryNode.is_healthy === false)) ||
          (backendNode && (!backendNode.is_enabled || backendNode.is_draining || backendNode.is_healthy === false));
        return {
          id: r.id,
          entry_id: r.entry_node_id,
          backend_id: r.node_id,
          entry: entryNode?.name,
          backend: backendNode?.name,
          status: endpointBlocked ? "blocked" : r.health_status,
          weight: r.effective_weight,
          is_active: r.is_active,
          latency: latencyByBackend[r.node_id] ?? null,
        };
      })
      .filter((r) => r.entry && r.backend),
    [routes, nodesById, latencyByBackend]);

  const sortedEntries = entries;
  const sortedBackends = useMemo(() => {
    const entryIndex = {};
    entries.forEach((e, i) => { entryIndex[e.name] = i; });
    return [...backends].sort((a, b) => {
      const ai = enrichedRoutes.filter((r) => r.backend === a.name).map((r) => entryIndex[r.entry] ?? 99);
      const bi = enrichedRoutes.filter((r) => r.backend === b.name).map((r) => entryIndex[r.entry] ?? 99);
      const avg = (xs) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : 99);
      return avg(ai) - avg(bi);
    });
  }, [entries, backends, enrichedRoutes]);

  const recalc = () => {
    const c = canvasRef.current;
    if (!c) return;
    const rect = c.getBoundingClientRect();
    const boxes = {};
    c.querySelectorAll("[data-topo-id]").forEach((el) => {
      boxes[el.getAttribute("data-topo-id")] = el.getBoundingClientRect();
    });

    const entryOrder = {}; const backendOrder = {};
    for (const en of sortedEntries) {
      const outs = enrichedRoutes.filter((r) => r.entry === en.name);
      outs.sort((a, b) => (boxes[a.backend]?.top ?? 0) - (boxes[b.backend]?.top ?? 0));
      outs.forEach((r, i) => { entryOrder[r.id] = { idx: i, total: outs.length }; });
    }
    for (const bn of sortedBackends) {
      const ins = enrichedRoutes.filter((r) => r.backend === bn.name);
      ins.sort((a, b) => (boxes[a.entry]?.top ?? 0) - (boxes[b.entry]?.top ?? 0));
      ins.forEach((r, i) => { backendOrder[r.id] = { idx: i, total: ins.length }; });
    }

    const xSlot = {};
    enrichedRoutes.slice().sort((a, b) => a.id.localeCompare(b.id)).forEach((r, i) => { xSlot[r.id] = i; });
    const xSlotCount = Math.max(enrichedRoutes.length, 1);

    const next = enrichedRoutes.map((r) => {
      const a = boxes[r.entry]; const b = boxes[r.backend];
      if (!a || !b) return null;
      const eo = entryOrder[r.id] || { idx: 0, total: 1 };
      const bo = backendOrder[r.id] || { idx: 0, total: 1 };
      const anchorY = (box, { idx, total }) => {
        if (total <= 1) return box.top + box.height / 2 - rect.top;
        const pad = 8;
        const top = box.top + pad - rect.top;
        const bot = box.top + box.height - pad - rect.top;
        return top + ((bot - top) * idx) / (total - 1);
      };
      const x1 = a.right - rect.left;
      const y1 = anchorY(a, eo);
      const x2 = b.left - rect.left;
      const y2 = anchorY(b, bo);
      const totalGap = Math.max(40, x2 - x1 - 80);
      const midX = x1 + 40 + totalGap * ((xSlot[r.id] + 0.5) / xSlotCount);
      const clampedMidX = Math.min(x2 - 20, Math.max(x1 + 20, midX));
      const d = `M ${x1} ${y1} L ${clampedMidX - 8} ${y1} Q ${clampedMidX} ${y1}, ${clampedMidX} ${(y1 + y2) / 2} Q ${clampedMidX} ${y2}, ${clampedMidX + 8} ${y2} L ${x2} ${y2}`;
      const w = r.weight || 0;
      const thickness = w >= 80 ? 2.5 : w >= 40 ? 1.8 : w > 0 ? 1.3 : 1;
      return { ...r, d, x1, y1, x2, y2, midX: clampedMidX, midY: (y1 + y2) / 2, thickness };
    }).filter(Boolean);
    setEdges(next);
  };

  useEffect(() => {
    recalc();
    const ro = new ResizeObserver(recalc);
    if (canvasRef.current) ro.observe(canvasRef.current);
    window.addEventListener("resize", recalc);
    return () => { ro.disconnect(); window.removeEventListener("resize", recalc); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sortedEntries, sortedBackends, enrichedRoutes]);

  const isEdgeVisible = (e) => !(onlyProblems && e.status === "healthy");
  const isEdgeFocused = (e) => {
    if (focusedRoute) return e.id === focusedRoute;
    if (focus) return e.entry === focus || e.backend === focus;
    return true;
  };
  const isNodeFocused = (name) => {
    if (focusedRoute) {
      const r = edges.find((e) => e.id === focusedRoute);
      return r && (r.entry === name || r.backend === name);
    }
    if (!focus) return true;
    if (focus === name) return true;
    return edges.some((e) => (e.entry === focus && e.backend === name) || (e.backend === focus && e.entry === name));
  };

  const nodeRouteStats = useMemo(() => {
    const m = {};
    for (const r of enrichedRoutes) {
      m[r.entry] = m[r.entry] || { total: 0, problems: 0 };
      m[r.backend] = m[r.backend] || { total: 0, problems: 0 };
      m[r.entry].total++; m[r.backend].total++;
      if (r.status !== "healthy") { m[r.entry].problems++; m[r.backend].problems++; }
    }
    return m;
  }, [enrichedRoutes]);

  const healthTone = (n) => {
    if (!n) return "bad";
    if (!n.is_enabled) return "bad";
    if (n.is_draining) return "warn";
    return n.is_healthy ? "ok" : "bad";
  };

  return (
    <div>
      <div className="filterbar">
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "var(--text-secondary)", cursor: "pointer" }}>
          <input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} /> Только проблемные
        </label>
        {(focus || focusedRoute) && (
          <button className="btn btn-xs" onClick={() => { setFocus(null); setFocusedRoute(null); }}>
            <Icon name="x" size={11} /> Сбросить фокус
          </button>
        )}
        <div className="topo-summary-inline">
          <span><span className="status-dot ok" /> {edges.filter((e) => e.status === "healthy").length} healthy</span>
          <span><span className="status-dot warn" /> {edges.filter((e) => e.status === "degraded" || e.status === "suspected").length} degraded</span>
          <span><span className="status-dot bad" /> {edges.filter((e) => e.status === "blocked").length} blocked</span>
          <span><span className="status-dot info" /> {edges.filter((e) => e.status === "warming_up").length} warming</span>
        </div>
        <div style={{ display: "flex", gap: 10, marginLeft: "auto", fontSize: 11, alignItems: "center" }}>
          <span className="muted">Толщина = вес маршрута · Анимация = healthy</span>
        </div>
      </div>

      <div className="topo-v2-scroll">
      <div
        className={`topo-v2 ${(focus || focusedRoute) ? "has-focus" : ""}`}
        ref={canvasRef}
        onClick={(e) => {
          // click on empty canvas → reset focus (SVG hit-paths + node cards call stopPropagation)
          if (e.target === e.currentTarget || e.target.classList?.contains("topo-v2-svg")) {
            setFocus(null);
            setFocusedRoute(null);
          }
        }}
      >
        <div className="topo-v2-header topo-v2-header-left">
          <span>Entry · точка входа</span>
        </div>
        <div className="topo-v2-header topo-v2-header-right">
          <span>Backend · обработка</span>
        </div>

        <div className="topo-v2-nodes topo-v2-nodes-left">
          {sortedEntries.map((n) => {
            const stats = nodeRouteStats[n.name] || { total: 0, problems: 0 };
            return (
              <div
                key={n.id}
                data-topo-id={n.name}
                className={`topo-v2-node ${focus === n.name ? "focused" : ""} ${!isNodeFocused(n.name) ? "dim" : ""}`}
                onClick={() => { setFocus(focus === n.name ? null : n.name); setFocusedRoute(null); }}
                onDoubleClick={() => onOpenNode && onOpenNode(n)}
                title="Клик — фокус связей, двойной клик — открыть ноду"
              >
                <div className="topo-v2-node-main">
                  <span className={`status-dot ${healthTone(n)}`} />
                  <span className="flag">{nodeGeo(n.region).flag}</span>
                  <span className="topo-v2-node-name">{n.name}</span>
                  <span style={{ marginLeft: "auto", display: "inline-flex", gap: 4 }}>
                    {(usersByEntryId[n.id] || 0) > 0 && (
                      <span
                        className="pill accent"
                        title={`${usersByEntryId[n.id]} уникальных юзеров онлайн через эту entry`}
                        style={{ padding: "1px 6px", fontSize: 10, lineHeight: 1.4 }}
                      >
                        <Icon name="user" size={9} /> {usersByEntryId[n.id]}
                      </span>
                    )}
                    {(liveByEntryId[n.id] || 0) > 0 && (
                      <span
                        className="pill ok"
                        title={`${liveByEntryId[n.id]} активных коннектов через эту entry (sing-box clash-API)`}
                        style={{ padding: "1px 6px", fontSize: 10, lineHeight: 1.4 }}
                      >
                        <Icon name="activity" size={9} /> {liveByEntryId[n.id]}
                      </span>
                    )}
                    {n.role === "whitelist_entry" && (
                      <span
                        className="pill accent"
                        title="Whitelist entry"
                        style={{ padding: "1px 5px", fontSize: 9.5, letterSpacing: 0.3, lineHeight: 1.4 }}
                      >
                        WL
                      </span>
                    )}
                  </span>
                </div>
                <div className="topo-v2-node-meta">
                  {(() => {
                    const ld = nodeLoad(n, { cpuPct: n.cpu_pct, bandwidthPct: n.bandwidth_pct });
                    return (
                      <span className="mono" title={ld.tooltip} style={{ color: `var(--${ld.tone})` }}>
                        {ld.pct != null ? `${ld.pct}%` : ld.label}
                      </span>
                    );
                  })()}
                  <span className="topo-v2-node-routes">
                    {stats.total} <Icon name="route" size={10} />
                    {stats.problems > 0 && <span className="topo-v2-node-prob">{stats.problems}</span>}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        <div className="topo-v2-nodes topo-v2-nodes-right">
          {sortedBackends.map((n) => {
            const stats = nodeRouteStats[n.name] || { total: 0, problems: 0 };
            const userCount = userCountByBackendName[n.name] || 0;
            const liveCount = liveByBackendName[n.name] || 0;
            return (
              <div
                key={n.id}
                data-topo-id={n.name}
                className={`topo-v2-node ${focus === n.name ? "focused" : ""} ${!isNodeFocused(n.name) ? "dim" : ""}`}
                onClick={() => { setFocus(focus === n.name ? null : n.name); setFocusedRoute(null); }}
                onDoubleClick={() => onOpenNode && onOpenNode(n)}
                title="Клик — фокус связей, двойной клик — открыть ноду"
              >
                <div className="topo-v2-node-main">
                  <span className={`status-dot ${healthTone(n)}`} />
                  <span className="flag">{nodeGeo(n.region).flag}</span>
                  <span className="topo-v2-node-name">{n.name}</span>
                  <span style={{ marginLeft: "auto", display: "inline-flex", gap: 4 }}>
                    {liveCount > 0 && (
                      <span
                        className="pill ok"
                        title={`${liveCount} активных TCP-сессии (sing-box clash-API)`}
                        style={{ padding: "1px 6px", fontSize: 10, lineHeight: 1.4 }}
                      >
                        <Icon name="activity" size={9} /> {liveCount}
                      </span>
                    )}
                    {userCount > 0 && (
                      <span
                        className="pill accent"
                        title={`${userCount} ключ(ей) назначено на этот backend (effective_backend)`}
                        style={{ padding: "1px 6px", fontSize: 10, lineHeight: 1.4 }}
                      >
                        <Icon name="key" size={9} /> {userCount}
                      </span>
                    )}
                  </span>
                </div>
                <div className="topo-v2-node-meta">
                  {(() => {
                    const ld = nodeLoad(n, { cpuPct: n.cpu_pct, bandwidthPct: n.bandwidth_pct });
                    return (
                      <span className="mono" title={ld.tooltip} style={{ color: `var(--${ld.tone})` }}>
                        {ld.pct != null ? `${ld.pct}%` : ld.label}
                      </span>
                    );
                  })()}
                  <span className="topo-v2-node-routes">
                    {stats.total} <Icon name="route" size={10} />
                    {stats.problems > 0 && <span className="topo-v2-node-prob">{stats.problems}</span>}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        <svg className="topo-v2-svg">
          {edges.filter(isEdgeVisible).map((e) => (
            <path
              key={`hit-${e.id}`}
              d={e.d}
              className="topo-v2-edge-hit"
              onMouseEnter={() => setHoverEdge(e.id)}
              onMouseLeave={() => setHoverEdge(null)}
              onClick={() => setFocusedRoute(focusedRoute === e.id ? null : e.id)}
            />
          ))}
          {edges.filter(isEdgeVisible).map((e) => {
            const focused = isEdgeFocused(e);
            const hovered = hoverEdge === e.id || focusedRoute === e.id;
            const isHealthy = e.status === "healthy";
            return (
              <g key={e.id} className={`topo-v2-edge-group ${!focused ? "dim" : ""} ${hovered ? "hot" : ""}`}>
                <path
                  d={e.d}
                  className={`topo-v2-edge ${edgeStatusClass(e.status)}`}
                  style={{ strokeWidth: e.thickness + (hovered ? 1.5 : 0) }}
                />
                {isHealthy && focused && (
                  <circle r="3" className="topo-v2-flow-dot">
                    <animateMotion dur="3s" repeatCount="indefinite" path={e.d} rotate="auto" />
                  </circle>
                )}
                {hovered && (
                  <g transform={`translate(${e.midX}, ${e.midY})`}>
                    <rect x="-52" y="-18" width="104" height="36" rx="6" className="topo-v2-edge-label-bg" />
                    <text x="0" y="-3" className="topo-v2-edge-label-id">{String(e.id).slice(0, 8)}</text>
                    <text x="0" y="11" className="topo-v2-edge-label-lat">
                      {e.latency != null ? `${e.latency}ms · w${e.weight}` : `w${e.weight}`}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
        </svg>
      </div>
      </div>
    </div>
  );
}
