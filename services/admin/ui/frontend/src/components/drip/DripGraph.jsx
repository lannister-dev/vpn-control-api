// Drip / Цепочки — branching graph canvas.
import { useRef, useState } from "react";

import { Icon } from "../Icon.jsx";
import { TRIGGERS, CONDITIONS, fmtDelay, stripTags } from "./dripModel.js";

function messageNumbers(nodes) {
  const map = {}; let n = 0;
  nodes.forEach((nd) => { if (nd.type === "message") map[nd.id] = ++n; });
  return map;
}

export function DripNode({ node, selected, num, showCounts = true, onSelect, onBeginDrag, movedRef }) {
  const common = {
    "data-selected": selected ? "true" : "false",
    style: { left: node.cx - node.w / 2, top: node.top, width: node.w, height: node.h, cursor: onBeginDrag ? "grab" : "pointer" },
    onMouseDown: (e) => { if (onBeginDrag && e.button === 0) onBeginDrag(node, e); },
    onClick: (e) => {
      e.stopPropagation();
      if (movedRef && movedRef.current) { movedRef.current = false; return; }
      onSelect(node.id);
    },
  };

  if (node.type === "trigger") {
    const t = TRIGGERS[node.trigger_event] || {};
    return (
      <div className="dn dn-trigger" {...common}
        style={{ ...common.style, left: node.cx, width: "max-content", maxWidth: 460, transform: "translateX(-50%)" }}>
        <div className="dn-head">
          <span className="dn-ic"><Icon name={t.icon || "zap"} size={14} /></span>
          <span className="dn-type">Старт</span>
          <span className="dn-trig-name">{t.label}</span>
        </div>
      </div>
    );
  }

  if (node.type === "condition") {
    const q = CONDITIONS[node.check] || node.check;
    return (
      <div className="dn dn-condition" {...common}>
        <div className="dn-head">
          <span className="dn-ic"><Icon name="git-branch" size={14} /></span>
          <span className="dn-type">Условие</span>
        </div>
        <div className="dn-body"><div className="dn-title">{q}?</div></div>
        <div className="dn-ports">
          <span className="dn-port yes">↙ {node.yes}</span>
          <span className="dn-port no">{node.no} ↘</span>
        </div>
      </div>
    );
  }

  if (node.type === "end") {
    return (
      <div className={"dn dn-end" + (node.conversion ? " is-conv" : "")} {...common}>
        <div className="dn-head">
          <span className="dn-ic"><Icon name={node.conversion ? "check-circle" : "flag"} size={14} /></span>
          <span className="dn-type">{node.conversion ? "Конверсия" : "Финал"}</span>
        </div>
        <div className="dn-body"><div className="dn-title" style={{ WebkitLineClamp: 1 }}>{node.label}</div></div>
      </div>
    );
  }

  // message
  const firstBtn = (node.buttons || [])[0];
  const extraBtns = (node.buttons || []).length - 1;
  const cond = node.condition && node.condition !== "always";
  return (
    <div className="dn dn-message" {...common}>
      <div className="dn-head">
        <span className="dn-ic"><Icon name="message-square" size={13} /></span>
        <span className="dn-type">Сообщение</span>
        <span className="dn-num">#{num}</span>
      </div>
      <div className="dn-body"><div className="dn-title">{stripTags(node.text) || "Без текста"}</div></div>
      <div className="dn-foot">
        {node.media && <span className="dn-meta"><Icon name="image" size={12} /> медиа</span>}
        {node.repeat > 1 && <span className="dn-meta" title="Повторов"><Icon name="refresh" size={11} /> ×{node.repeat}</span>}
        {firstBtn && (
          <span className="dn-btnchip"><Icon name="link" size={11} />{firstBtn.text}{extraBtns > 0 ? ` +${extraBtns}` : ""}</span>
        )}
        {cond && <span className="dn-meta" title="Условие отправки"><Icon name="git-branch" size={11} /> усл.</span>}
        {showCounts && <span className="dn-meta" style={{ marginLeft: "auto" }}><Icon name="user" size={11} /> {node.stats?.active ?? 0}</span>}
      </div>
    </div>
  );
}

export function DripGraph({ nodes, edges, selected, onSelect, onInsert, onMoveNode, edgeStyle = "curved", showCounts = true }) {
  const [zoom, setZoom] = useState(1);
  const movedRef = useRef(false);
  const dragRef = useRef(null);

  const beginDrag = onMoveNode ? (node, e) => {
    e.stopPropagation();
    dragRef.current = { id: node.id, x: e.clientX, y: e.clientY, cx: node.cx, top: node.top };
    movedRef.current = false;
    const onMove = (ev) => {
      const d = dragRef.current;
      if (!d) return;
      const dx = (ev.clientX - d.x) / zoom;
      const dy = (ev.clientY - d.y) / zoom;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) movedRef.current = true;
      onMoveNode(d.id, Math.round(d.cx + dx), Math.max(0, Math.round(d.top + dy)));
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      dragRef.current = null;
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  } : undefined;

  const nums = messageNumbers(nodes);
  const byId = {};
  nodes.forEach((n) => (byId[n.id] = n));

  // world bounds from node extents
  let WORLD_W = 660, WORLD_H = 600;
  nodes.forEach((n) => {
    WORLD_W = Math.max(WORLD_W, n.cx + n.w / 2 + 40);
    WORLD_H = Math.max(WORLD_H, n.top + n.h + 60);
  });

  const srcAnchor = (n, branch) =>
    n.type === "condition" && branch
      ? { x: n.cx + (branch === "yes" ? -46 : 46), y: n.top + n.h }
      : { x: n.cx, y: n.top + n.h };
  const dstAnchor = (n) => ({ x: n.cx, y: n.top });

  const built = edges.filter((e) => byId[e.from] && byId[e.to]).map((e) => {
    const s = srcAnchor(byId[e.from], e.branch);
    const d = dstAnchor(byId[e.to]);
    const dy = d.y - s.y;
    let path;
    if (edgeStyle === "step") {
      const midY = s.y + dy / 2, r = 10;
      if (Math.abs(d.x - s.x) < 1) path = `M ${s.x} ${s.y} L ${d.x} ${d.y}`;
      else {
        const sgn = d.x > s.x ? 1 : -1;
        path = `M ${s.x} ${s.y} L ${s.x} ${midY - r} Q ${s.x} ${midY} ${s.x + sgn * r} ${midY} L ${d.x - sgn * r} ${midY} Q ${d.x} ${midY} ${d.x} ${midY + r} L ${d.x} ${d.y}`;
      }
    } else {
      path = `M ${s.x} ${s.y} C ${s.x} ${s.y + dy * 0.45} ${d.x} ${d.y - dy * 0.45} ${d.x} ${d.y}`;
    }
    const at = (t) => ({ x: s.x + (d.x - s.x) * t, y: s.y + dy * t });
    return { ...e, s, d, path, at };
  });

  return (
    <div className="dg-canvas" onClick={() => { if (movedRef.current) { movedRef.current = false; return; } onSelect(null); }}>
      <div className="dg-world" style={{ width: WORLD_W, height: WORLD_H, transform: `scale(${zoom})` }}>
        <svg className="dg-edges" width={WORLD_W} height={WORLD_H}>
          {built.map((e, i) => (
            <path key={i} className={"dg-edge-path" + (e.branch === "yes" ? " is-yes" : e.branch === "no" ? " is-no" : "")} d={e.path} />
          ))}
        </svg>

        {built.map((e, i) => {
          const out = [];
          if (e.branch) {
            const p = e.at(0.16);
            out.push(
              <div key={`b${i}`} className={"dg-branch " + e.branch} style={{ left: p.x, top: p.y }}>
                {e.branch === "yes" ? byId[e.from].yes : byId[e.from].no}
              </div>
            );
          }
          if (e.delayOf && byId[e.delayOf]) {
            const p = e.at(e.branch ? 0.42 : 0.5);
            out.push(
              <div key={`d${i}`} className="dg-chip" style={{ left: p.x, top: p.y }}>
                <Icon name="clock" size={11} /> через {fmtDelay(byId[e.delayOf].delay_seconds)}
              </div>
            );
          }
          if (onInsert && (byId[e.to].type === "message" || byId[e.to].type === "condition" || byId[e.to].type === "end")) {
            const p = e.at(e.delayOf ? 0.68 : 0.5);
            out.push(
              <div key={`i${i}`} className="dg-insert" style={{ left: p.x, top: p.y }} title="Вставить шаг"
                onClick={(ev) => { ev.stopPropagation(); onInsert(e); }}>
                <Icon name="plus" size={13} />
              </div>
            );
          }
          return out;
        })}

        {nodes.map((n) => (
          <DripNode key={n.id} node={n} num={nums[n.id]} selected={selected === n.id} showCounts={showCounts}
            onSelect={onSelect} onBeginDrag={beginDrag} movedRef={movedRef} />
        ))}
      </div>

      <div className="dg-toolbar" onClick={(e) => e.stopPropagation()}>
        <button className="btn btn-ghost btn-icon" title="Уменьшить" onClick={() => setZoom((z) => Math.max(0.5, +(z - 0.1).toFixed(2)))}><Icon name="minus" size={14} /></button>
        <span className="dg-tool-z">{Math.round(zoom * 100)}%</span>
        <button className="btn btn-ghost btn-icon" title="Увеличить" onClick={() => setZoom((z) => Math.min(1.6, +(z + 0.1).toFixed(2)))}><Icon name="plus" size={14} /></button>
        <span className="dg-tool-sep" />
        <button className="btn btn-ghost btn-icon" title="Сбросить" onClick={() => setZoom(1)}><Icon name="refresh" size={13} /></button>
      </div>
    </div>
  );
}
