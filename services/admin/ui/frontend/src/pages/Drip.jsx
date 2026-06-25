import { useState } from "react";

import { api } from "../api/client.js";
import { Empty } from "../components/Empty.jsx";
import { Icon } from "../components/Icon.jsx";
import { useQuery } from "../hooks/useQuery.js";
import { DripGraph } from "../components/drip/DripGraph.jsx";
import { DripInspector } from "../components/drip/DripInspector.jsx";
import "../components/drip/drip.css";
import {
  TRIGGERS, graphFromApi, graphToPayload, mockChain, emptyMessage, layoutLinear,
} from "../components/drip/dripModel.js";

/* ════════════════════════════════════════════════════════════
   Цепочки — drip campaign builder
   - List view: campaigns table with live stats
   - Builder view: branching graph (left) + step inspector & live
     Telegram preview (right). Selecting a node opens its editor.

   Backend today stores LINEAR steps; graphFromApi/graphToPayload bridge
   that. CONDITION/END nodes + multiple branches are an extension — see
   drip_module/README.md for the proposed contract. The builder degrades
   to a linear chain when the campaign has no branch metadata.
   ════════════════════════════════════════════════════════════ */

export function DripPage() {
  const q = useQuery(() => api.get("/support/drip/campaigns").catch(() => ({ items: [] })), { interval: 0 });
  const statsQ = useQuery(() => api.get("/support/drip/stats").catch(() => ({ items: [] })), { interval: 0 });

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
  const deleteNode = (id) => {
    setGraph((g) => {
      const msgs = g.nodes.filter((n) => n.type === "message" && n.id !== id).map(({ id: _i, ...r }) => r);
      const { nodes, edges } = layoutLinear(msgs, g.meta.trigger_event);
      return { ...g, nodes, edges };
    });
    setSelected(null);
  };
  const insertStep = (edge) => {
    const msgs = graph.nodes.filter((n) => n.type === "message");
    const fromIdx = msgs.findIndex((m) => m.id === edge.from);
    const insertAt = fromIdx >= 0 ? fromIdx + 1 : 0;
    const data = msgs.map(({ id: _i, ...r }) => r);
    data.splice(insertAt, 0, emptyMessage(""));
    const { nodes, edges } = layoutLinear(data, graph.meta.trigger_event);
    setGraph((g) => ({ ...g, nodes, edges }));
    setSelected(`m${insertAt + 1}`);
  };

  const save = async () => {
    const payload = graphToPayload(graph.meta, graph.nodes);
    if (!payload.key || !payload.name) { setErr("Заполни ключ и название"); return; }
    if (!payload.steps.length) { setErr("Добавь хотя бы один шаг"); return; }
    setBusy(true); setErr("");
    try {
      if (graph.meta.id) await api.put(`/support/drip/campaigns/${graph.meta.id}`, payload);
      else await api.post("/support/drip/campaigns", payload);
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
          <DripGraph
            nodes={graph.nodes}
            edges={graph.edges}
            selected={selected}
            onSelect={setSelected}
            onInsert={insertStep}
            edgeStyle={edgeStyle}
            showCounts={showCounts}
          />
          <DripInspector
            node={selectedNode}
            chainStats={m.stats}
            onPatch={patchNode}
            onClose={() => setSelected(null)}
            onDelete={deleteNode}
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
