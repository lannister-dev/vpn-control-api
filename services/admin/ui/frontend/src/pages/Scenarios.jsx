import { useState } from "react";

import { api } from "../api/client.js";
import { Empty } from "../components/Empty.jsx";
import { Icon } from "../components/Icon.jsx";
import { useQuery } from "../hooks/useQuery.js";
import { ScenarioGraph } from "../components/scenarios/ScenarioGraph.jsx";
import { ScenarioInspector } from "../components/scenarios/ScenarioInspector.jsx";
import "../components/scenarios/scenario.css";
import {
  TRIGGERS, graphFromApi, graphToPayload, mockChain, emptyMessage, layoutLinear,
  autoLayout, nextNodeId, LANE, NODE_W,
} from "../components/scenarios/scenarioModel.js";

export function ScenariosPage() {
  const q = useQuery(() => api.get("/scenarios/campaigns").catch(() => ({ items: [] })), { interval: 0 });
  const statsQ = useQuery(() => api.get("/scenarios/stats").catch(() => ({ items: [] })), { interval: 0 });

  const [graph, setGraph] = useState(null);   // { meta, nodes, edges } | null
  const [selected, setSelected] = useState(null);
  const [edgeStyle, setEdgeStyle] = useState("curved");
  const [showCounts, setShowCounts] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const campaigns = q.data?.items || [];
  const statsById = {};
  (statsQ.data?.items || []).forEach((s) => { statsById[s.campaign_id] = s; });

  const openCampaign = (c) => {
    const g = graphFromApi({ ...c, stats: statsById[c.id] });
    setGraph(g);
    setSelected(g.nodes.find((n) => n.type === "message")?.id || "trig");
    setErr("");
  };
  const openNew = () => {
    const { nodes, edges } = layoutLinear([emptyMessage("m1")], "trial_started");
    setGraph({ meta: { id: null, key: "", name: "", trigger_event: "trial_started", is_active: false, stats: { active: 0, completed: 0 } }, nodes, edges });
    setSelected("m1");
    setErr("");
  };
  const openDemo = () => { const g = mockChain(); setGraph(g); setSelected("m3"); setErr(""); };

  const selectedNode = graph?.nodes.find((n) => n.id === selected) || null;
  const patchMeta = (p) => setGraph((g) => ({ ...g, meta: { ...g.meta, ...p } }));
  const patchNode = (p) => setGraph((g) => ({ ...g, nodes: g.nodes.map((n) => (n.id === selected ? { ...n, ...p } : n)) }));
  const moveNode = (id, cx, top) => setGraph((g) => ({ ...g, nodes: g.nodes.map((n) => (n.id === id ? { ...n, cx, top } : n)) }));
  const deleteNode = (id) => {
    setGraph((g) => {
      const incoming = g.edges.filter((e) => e.to === id);
      const outgoing = g.edges.filter((e) => e.from === id);
      const nodes = g.nodes.filter((n) => n.id !== id);
      const edges = g.edges.filter((e) => e.from !== id && e.to !== id);
      const target = outgoing[0] ? outgoing[0].to : null;
      if (target) {
        incoming.forEach((inc) => {
          if (inc.from !== target && !edges.some((e) => e.from === inc.from && e.to === target)) {
            edges.push({ from: inc.from, to: target, branch: inc.branch || undefined, delayOf: nodes.some((n) => n.id === target && n.type === "message") ? target : undefined });
          }
        });
      }
      return { ...g, nodes: autoLayout(nodes, edges), edges };
    });
    setSelected(null);
  };
  const insertStep = (edge) => {
    setGraph((g) => {
      const nodes = g.nodes.map((n) => ({ ...n }));
      const edges = g.edges.map((e) => ({ ...e }));
      const mId = nextNodeId(nodes, "m");
      nodes.push({ ...emptyMessage(mId), id: mId });
      const idx = edges.findIndex((e) => e.from === edge.from && e.to === edge.to && e.branch === edge.branch);
      if (idx >= 0) {
        const old = edges[idx];
        const tailIsMsg = nodes.some((n) => n.id === old.to && n.type === "message");
        edges.splice(idx, 1,
          { from: old.from, to: mId, branch: old.branch || undefined, delayOf: mId },
          { from: mId, to: old.to, delayOf: tailIsMsg ? old.to : undefined },
        );
      } else {
        edges.push({ from: edge.from, to: mId, delayOf: mId });
      }
      setSelected(mId);
      return { ...g, nodes: autoLayout(nodes, edges), edges };
    });
  };
  const insertBranchAfter = (nodeKey) => {
    setGraph((g) => {
      const nodes = g.nodes.map((n) => ({ ...n }));
      const edges = g.edges.map((e) => ({ ...e }));
      const outIdx = edges.findIndex((e) => e.from === nodeKey && !e.branch);
      const oldTarget = outIdx >= 0 ? edges[outIdx].to : null;
      if (outIdx >= 0) edges.splice(outIdx, 1);
      const cId = nextNodeId(nodes, "c");
      const aId = nextNodeId(nodes, "m");
      const bId = nextNodeId([...nodes, { id: aId }], "m");
      nodes.push({ id: cId, type: "condition", cx: LANE.C, top: 0, w: NODE_W, h: 88, check: "connected", yes: "Да", no: "Нет" });
      nodes.push({ ...emptyMessage(aId), id: aId });
      nodes.push({ ...emptyMessage(bId), id: bId });
      edges.push({ from: nodeKey, to: cId });
      edges.push({ from: cId, to: aId, branch: "yes", delayOf: aId });
      edges.push({ from: cId, to: bId, branch: "no", delayOf: bId });
      if (oldTarget) {
        edges.push({ from: aId, to: oldTarget });
        edges.push({ from: bId, to: oldTarget });
      }
      setSelected(cId);
      return { ...g, nodes: autoLayout(nodes, edges), edges };
    });
  };

  const save = async () => {
    const payload = graphToPayload(graph.meta, graph.nodes, graph.edges);
    if (!payload.key || !payload.name) { setErr("Заполни ключ и название"); return; }
    if (!payload.nodes.length) { setErr("Добавь хотя бы один шаг"); return; }
    setBusy(true); setErr("");
    try {
      if (graph.meta.id) await api.put(`/scenarios/campaigns/${graph.meta.id}`, payload);
      else await api.post("/scenarios/campaigns", payload);
      setGraph(null); q.refetch(); statsQ.refetch();
    } catch (e) { setErr(e.message || "Ошибка сохранения"); }
    finally { setBusy(false); }
  };

  /* ── Builder view ── */
  if (graph) {
    const m = graph.meta;
    return (
      <div className="db-wrap">
        <div className="db-bar">
          <button className="btn btn-ghost btn-icon db-bar-back" title="К списку" onClick={() => setGraph(null)} disabled={busy}><Icon name="chevron-left" size={17} /></button>
          <div className="db-bar-id">
            <input className="db-bar-name" value={m.name} placeholder="Название цепочки" onChange={(e) => patchMeta({ name: e.target.value })} />
            <input className="db-bar-key" value={m.key} placeholder="ключ_латиницей" disabled={!!m.id} onChange={(e) => patchMeta({ key: e.target.value })} style={{ border: 0, background: "transparent" }} />
          </div>
          <span className="db-trigger-chip">
            <span className="ic"><Icon name="zap" size={13} /></span>
            {TRIGGERS[m.trigger_event]?.label || m.trigger_event}
          </span>
          <div className="db-bar-spacer" />
          <div className="db-stat"><span className="db-stat-val">{(m.stats?.active || 0).toLocaleString("ru-RU")}</span><span className="db-stat-lbl">в работе</span></div>
          <div className="db-stat"><span className="db-stat-val">{(m.stats?.completed || 0).toLocaleString("ru-RU")}</span><span className="db-stat-lbl">завершено</span></div>
          <div className="db-toggle" style={{ paddingLeft: 14, borderLeft: "1px solid var(--border)" }}>
            <span>{m.is_active ? "Активна" : "Выключена"}</span>
            <button className="db-switch" data-on={m.is_active ? "true" : "false"} onClick={() => patchMeta({ is_active: !m.is_active })} />
          </div>
          <button className="btn btn-primary" onClick={save} disabled={busy}><Icon name="check" size={14} /> Сохранить</button>
        </div>

        {err && <div className="card card-bad" style={{ margin: "10px 16px 0" }}>{err}</div>}

        <div className="db-body">
          <ScenarioGraph
            nodes={graph.nodes}
            edges={graph.edges}
            selected={selected}
            onSelect={setSelected}
            onInsert={insertStep}
            onMoveNode={moveNode}
            edgeStyle={edgeStyle}
            showCounts={showCounts}
          />
          <ScenarioInspector
            node={selectedNode}
            chainStats={m.stats}
            onPatch={patchNode}
            onClose={() => setSelected(null)}
            onDelete={deleteNode}
            onAddBranch={insertBranchAfter}
          />
        </div>
      </div>
    );
  }

  /* ── List view ── */
  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-main">
          <h1 className="page-title">Цепочки</h1>
          <div className="page-subtitle">Автоматические сообщения по событиям: триал → подключение, конверсия, winback</div>
        </div>
        <div className="page-head-actions">
          <button className="btn" onClick={openDemo}><Icon name="eye" size={15} /> Демо-цепочка</button>
          <button className="btn btn-primary" onClick={openNew}><Icon name="plus" size={16} /> Кампания</button>
        </div>
      </div>

      {q.loading && !campaigns.length ? (
        <div className="card" style={{ padding: 16 }}><div className="muted">Загрузка…</div></div>
      ) : !campaigns.length ? (
        <Empty icon="git-branch" title="Цепочек нет"
          hint="Создай кампанию: выбери событие-триггер, собери шаги и ветки на схеме. Движок сам разошлёт их по юзерам. Можно открыть демо-цепочку, чтобы посмотреть редактор." />
      ) : (
        <div className="card">
          <table className="tbl">
            <thead>
              <tr><th>Название</th><th>Триггер</th><th>Шагов</th><th>В работе</th><th>Завершено</th><th>Статус</th></tr>
            </thead>
            <tbody>
              {campaigns.map((c) => {
                const st = statsById[c.id] || {};
                return (
                  <tr key={c.id} style={{ cursor: "pointer" }} onClick={() => openCampaign(c)}>
                    <td style={{ fontWeight: 500 }}>{c.name}<div className="mono muted" style={{ fontSize: 11 }}>{c.key}</div></td>
                    <td>{TRIGGERS[c.trigger_event]?.label || c.trigger_event || "—"}</td>
                    <td className="tbl-num">{(c.steps || []).length}</td>
                    <td className="tbl-num">{st.active || 0}</td>
                    <td className="tbl-num">{st.completed || 0}</td>
                    <td>{c.is_active ? <span className="pill ok">активна</span> : <span className="pill muted">выкл</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
