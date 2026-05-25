import { state, refs, $ } from '../state.js';
import { esc, uuidCell, shortId, fmtDate, relTime } from '../utils.js';
import { req } from '../api.js';
import { notify, confirmAction, openModal } from '../ui.js';

/* ── Callback setters (injected from app.js) ───────── */
let _refreshAll = () => {};
export function setCallbacks(refreshAll) { _refreshAll = refreshAll; }

/* ── Label helpers ──────────────────────────────────── */
export const verdictLabel = (v) => ({ ok: "Норма", lag: "Задержка", silent: "Молчит", dead: "Нет связи" }[v] || "Нет связи");
export const eventTypeLabel = (t) => ({ snapshot_request: "Snapshot", placement_result: "Результат", placement_command: "Команда" }[t] || t);
export const outboxStatusLabel = (s) => ({ pending: "В очереди", failed: "Ошибка", publishing: "Отправка", published: "Доставлено" }[s] || s);
export const snapshotReasonLabel = (r) => ({ full_resync: "Полная пересинхронизация", redelivery_gap: "Разрыв доставки", admin_requested: "Запрос оператора", initial: "Первичная синхронизация" }[r] || r || "-");
export const fmtLag = (s) => { if (s == null) return "-"; if (s < 60) return Math.round(s) + " сек"; if (s < 3600) return Math.round(s / 60) + " мин"; return Math.round(s / 3600) + " ч"; };
export const fmtUptime = (s) => { if (s == null) return "-"; const h = Math.floor(s / 3600); const m = Math.floor((s % 3600) / 60); return h > 0 ? `${h}ч ${m}м` : `${m}м`; };

/* ── Load transport data ────────────────────────────── */
export async function loadTransportData() {
  const [overview, nodesList] = await Promise.all([req("/api/v1/admin/transport/overview"), req("/api/v1/admin/transport/nodes")]);
  state.transportOverview = overview; state.transportNodes = nodesList.items || [];
  if (overview && overview.nats_connected) state.natsLastOnlineAt = Date.now();
  renderTransportKpi(); renderTransportNodes(); populateTransportNodeFilters();
}

/* ── KPI cards ──────────────────────────────────────── */
export function renderTransportKpi() {
  const o = state.transportOverview; if (!o) return;
  const ob = o.outbox || {}; const ev = o.events || {};
  const tasks = o.consumer_tasks || []; const running = tasks.filter((t) => t.running).length; const failedTasks = tasks.filter((t) => !t.running && t.error);
  const pill = $("t-nats-pill");
  if (pill) { pill.className = `t-status-pill ${o.nats_connected ? "online" : "offline"}`; pill.innerHTML = `<span class="t-pulse ${o.nats_connected ? "on" : "off"}"></span> ${o.nats_connected ? "Подключен" : "Не подключен"}`; }
  const queueCount = ob.pending + ob.publishing;
  $("transport-kpi").innerHTML = [
    `<div class="t-kpi-card"><div class="t-kpi-label">В очереди</div><div class="t-kpi-value">${queueCount}</div><div class="t-kpi-sub">${queueCount === 0 ? "Очередь пуста" : "ожидают отправки"}</div></div>`,
    `<div class="t-kpi-card"><div class="t-kpi-label">Ошибки доставки</div><div class="t-kpi-value" style="color:${ob.failed > 0 ? "var(--bad)" : "var(--ok)"}">${ob.failed}</div><div class="t-kpi-sub">${ob.failed > 0 ? "требуют внимания" : "ошибок нет"}</div></div>`,
    `<div class="t-kpi-card"><div class="t-kpi-label">Обработано за 24ч</div><div class="t-kpi-value">${ev.total_24h || 0}</div><div class="t-kpi-sub">${Object.entries(ev.by_type || {}).map(([k, v]) => `${eventTypeLabel(k)}: ${v}`).join(", ") || "нет данных"}</div></div>`,
    `<div class="t-kpi-card"><div class="t-kpi-label">Доставлено за 24ч</div><div class="t-kpi-value">${ob.published_24h || 0}</div><div class="t-kpi-sub">команд агентам</div></div>`,
    `<div class="t-kpi-card"><div class="t-kpi-label">Обработчики</div><div class="t-kpi-value">${running}<span style="font-size:13px;color:var(--muted)"> / ${tasks.length}</span></div><div class="t-kpi-sub">${failedTasks.length > 0 ? `<span style="color:var(--bad)">${failedTasks.length} упал</span>` : "все работают"}${o.uptime_s ? ` &middot; uptime ${fmtUptime(o.uptime_s)}` : ""}</div></div>`,
  ].join("");
}

/* ── Nodes table ────────────────────────────────────── */
export function renderTransportNodes() {
  const body = $("transport-nodes-body"); const nodes = state.transportNodes;
  if (!nodes.length) { body.innerHTML = `<tr><td colspan="10" class="empty">Серверы не найдены.</td></tr>`; return; }
  body.innerHTML = nodes.map((n) => {
    const v = n.health_verdict; const pending = n.outbox_pending || 0; const failed = n.outbox_failed || 0;
    const outboxCls = failed > 0 ? "fail" : (pending > 0 ? "warn" : "clean");
    const outboxLabel = failed > 0 ? `${pending} + ${failed} ош.` : (pending > 0 ? String(pending) : "0");
    const selected = state.transportNodeDetail && state.transportNodeDetail.node_id === n.node_id;
    return `<tr class="t-node-row${selected ? " selected" : ""}" data-nid="${esc(n.node_id)}">`
      + `<td><strong>${esc(n.name)}</strong><div>${uuidCell(n.node_id)}</div></td>`
      + `<td>${esc(n.region)}</td><td class="mono">${n.current_epoch}</td>`
      + `<td title="${esc(fmtDate(n.last_heartbeat_received_at))}">${relTime(n.last_heartbeat_received_at)}</td>`
      + `<td title="${esc(fmtDate(n.last_command_published_at))}">${relTime(n.last_command_published_at)}</td>`
      + `<td title="${esc(fmtDate(n.last_result_received_at))}">${relTime(n.last_result_received_at)}</td>`
      + `<td title="${esc(fmtDate(n.last_sync_report_received_at))}">${relTime(n.last_sync_report_received_at)}</td>`
      + `<td><span class="t-outbox-count ${outboxCls}">${outboxLabel}</span></td>`
      + `<td><div class="t-lag-bar"><span class="t-lag-indicator ${v}"></span><span class="mono" style="font-size:11px">${fmtLag(n.communication_lag_s)}</span></div></td>`
      + `<td><span class="t-verdict ${v}"><span class="t-verdict-dot"></span>${verdictLabel(v)}</span></td></tr>`;
  }).join("");
}

/* ── Populate node filter dropdowns ─────────────────── */
function populateTransportNodeFilters() {
  const nodes = state.transportNodes;
  const opts = `<option value="">Все серверы</option>` + nodes.map((n) => `<option value="${esc(n.node_id)}">${esc(n.name)}</option>`).join("");
  const of1 = $("outbox-node-filter"); if (of1) of1.innerHTML = opts;
  const ef1 = $("events-node-filter"); if (ef1) ef1.innerHTML = opts;
}

/* ── Node detail ────────────────────────────────────── */
async function loadTransportNodeDetail(nodeId) {
  const detail = await req(`/api/v1/admin/transport/nodes/${nodeId}`);
  state.transportNodeDetail = detail; renderTransportNodeDetail(); renderTransportNodes();
}

function renderTransportNodeDetail() {
  const d = state.transportNodeDetail; const panel = $("transport-node-detail");
  if (!d) { panel.style.display = "none"; return; }
  panel.style.display = "block";
  $("tnd-title").textContent = d.name;
  $("tnd-subtitle").textContent = `Эпоха ${d.current_epoch} \u00B7 ${verdictLabel(d.health_verdict)}`;
  $("tnd-snapshot-bar").innerHTML = [
    { label: "Snapshot ID", value: d.last_snapshot_id ? `<span title="${esc(d.last_snapshot_id)}">${esc(d.last_snapshot_id.length > 12 ? d.last_snapshot_id.slice(0, 12) + "\u2026" : d.last_snapshot_id)}</span>` : "-" },
    { label: "Причина", value: snapshotReasonLabel(d.last_snapshot_reason) },
    { label: "Запрошен", value: relTime(d.last_snapshot_requested_at) },
    { label: "Сгенерирован", value: relTime(d.last_snapshot_generated_at) },
  ].map((item) => `<div class="t-snap-item"><div class="t-snap-label">${item.label}</div><div class="t-snap-value">${item.value}</div></div>`).join("");
  const typeFilter = ($("tnd-event-filter") || {}).value || "";
  const events = (d.recent_events || []).filter((e) => !typeFilter || e.event_type === typeFilter).slice(0, 20);
  $("tnd-events").innerHTML = events.length
    ? events.map((e) => {
      const typeCls = e.event_type.replace(/[^a-z_]/g, "");
      return `<div class="t-event-card"><div style="display:flex;justify-content:space-between;align-items:center"><span class="t-event-type ${typeCls}">${esc(eventTypeLabel(e.event_type))}</span><span class="muted" style="font-size:10px" title="${esc(fmtDate(e.processed_at))}">${relTime(e.processed_at)}</span></div><div class="mono muted" style="font-size:10px;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(e.event_id)}">${esc(e.event_id)}</div><button class="btn-mini show-payload" style="margin-top:4px;font-size:10px" data-payload='${esc(JSON.stringify(e.payload))}'>Просмотр</button></div>`;
    }).join("")
    : `<div class="empty">Событий не найдено.</div>`;
  const outbox = d.outbox_items || []; const hasFailed = outbox.some((o) => o.status === "failed");
  $("tnd-retry-all").style.display = hasFailed ? "inline-block" : "none";
  $("tnd-outbox").innerHTML = outbox.length
    ? outbox.map((o) => `<div class="t-event-card"><div style="display:flex;justify-content:space-between;align-items:center"><span class="t-outbox-status ${o.status}">${esc(outboxStatusLabel(o.status))}</span><span class="mono muted" style="font-size:10px">попытка ${o.attempts}</span></div><div class="mono muted" style="font-size:10px;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(o.message_id)}">${esc(o.message_id)}</div>${o.last_error ? `<div class="muted" style="font-size:10px;margin-top:2px;color:var(--bad)">${esc(o.last_error.slice(0, 100))}</div>` : ""}${o.status === "failed" ? `<button class="btn-mini outbox-retry" style="margin-top:4px;font-size:10px" data-oid="${esc(o.id)}">Перезапустить</button>` : ""}</div>`).join("")
    : `<div class="empty">Очередь пуста.</div>`;
}

/* ── Outbox page ────────────────────────────────────── */
async function loadOutboxPage() {
  const nodeId = ($("outbox-node-filter") || {}).value || ""; const statusF = ($("outbox-status-filter") || {}).value || "";
  const params = new URLSearchParams({ limit: "50", offset: String(state.outboxOffset) });
  if (nodeId) params.set("node_id", nodeId); if (statusF) params.set("status", statusF);
  const data = await req(`/api/v1/admin/transport/outbox?${params}`);
  state.outboxItems = data.items || []; state.outboxTotal = data.total || 0; renderOutboxTable();
}

function renderOutboxTable() {
  const body = $("outbox-body"); const items = state.outboxItems;
  body.innerHTML = items.length
    ? items.map((o) => `<tr><td>${esc(o.node_name || "?")}<div>${uuidCell(o.node_id)}</div></td><td>${esc(eventTypeLabel(o.event_type))}</td><td class="mono" style="font-size:11px" title="${esc(o.message_id)}">${esc(o.message_id.length > 30 ? o.message_id.slice(0, 30) + "\u2026" : o.message_id)}</td><td><span class="t-outbox-status ${o.status}">${esc(outboxStatusLabel(o.status))}</span></td><td class="mono">${o.attempts}</td><td class="muted" style="font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis" title="${esc(o.last_error || "")}">${esc(o.last_error ? o.last_error.slice(0, 60) : "-")}</td><td title="${esc(fmtDate(o.created_at))}">${relTime(o.created_at)}</td><td>${o.status === "failed" ? `<button class="btn-mini outbox-retry" data-oid="${esc(o.id)}">Повтор</button>` : "-"}</td></tr>`).join("")
    : `<tr><td colspan="8" class="empty">Очередь пуста.</td></tr>`;
  const pages = Math.ceil(state.outboxTotal / 50); const curPage = Math.floor(state.outboxOffset / 50) + 1;
  $("outbox-pagination").innerHTML = state.outboxTotal > 0 ? `${state.outboxTotal} записей \u00B7 стр. ${curPage}/${pages}` + (state.outboxTotal > state.outboxOffset + 50 ? ` \u00B7 <a href="#" class="outbox-page-next">Далее &rarr;</a>` : "") : "";
}

/* ── Events page ────────────────────────────────────── */
async function loadEventsPage() {
  const nodeId = ($("events-node-filter") || {}).value || ""; const typeF = ($("events-type-filter") || {}).value || "";
  const search = ($("events-search") || {}).value || "";
  const params = new URLSearchParams({ limit: "50", offset: String(state.eventsOffset) });
  if (nodeId) params.set("node_id", nodeId); if (typeF) params.set("event_type", typeF); if (search) params.set("search", search);
  const data = await req(`/api/v1/admin/transport/events?${params}`);
  state.eventsItems = data.items || []; state.eventsTotal = data.total || 0; renderEventsTable();
}

function renderEventsTable() {
  const body = $("events-body"); const items = state.eventsItems;
  body.innerHTML = items.length
    ? items.map((e) => {
      const typeCls = e.event_type.replace(/[^a-z_]/g, "");
      return `<tr><td>${esc(e.node_name || "?")}<div>${uuidCell(e.node_id)}</div></td><td><span class="t-event-type ${typeCls}">${esc(eventTypeLabel(e.event_type))}</span></td><td class="mono" style="font-size:11px" title="${esc(e.event_id)}">${esc(e.event_id.length > 45 ? e.event_id.slice(0, 45) + "\u2026" : e.event_id)}</td><td title="${esc(fmtDate(e.processed_at))}">${relTime(e.processed_at)}</td><td><button class="btn-mini show-payload" data-payload='${esc(JSON.stringify(e.payload))}'>Просмотр</button></td></tr>`;
    }).join("")
    : `<tr><td colspan="5" class="empty">Событий не найдено.</td></tr>`;
  const pages = Math.ceil(state.eventsTotal / 50); const curPage = Math.floor(state.eventsOffset / 50) + 1;
  $("events-pagination").innerHTML = state.eventsTotal > 0 ? `${state.eventsTotal} записей \u00B7 стр. ${curPage}/${pages}` + (state.eventsTotal > state.eventsOffset + 50 ? ` \u00B7 <a href="#" class="events-page-next">Далее &rarr;</a>` : "") : "";
}

/* ── Payload modal ──────────────────────────────────── */
function showPayloadModal(payloadJson) {
  let pretty;
  try { pretty = JSON.stringify(JSON.parse(payloadJson), null, 2); } catch { pretty = payloadJson; }
  openModal({
    title: "Содержимое события",
    bodyHtml: `<pre class="mono payload-pre">${esc(pretty)}</pre>`,
    footerHtml: `<button class="btn btn-ghost" data-act="copy">Копировать</button><button class="btn btn-ghost" data-act="close">Закрыть</button>`,
    wide: true,
    onMount: ({ root, close }) => {
      root.querySelector('[data-act="close"]').addEventListener("click", close);
      root.querySelector('[data-act="copy"]').addEventListener("click", () => {
        navigator.clipboard.writeText(pretty).then(() => notify("Скопировано"));
      });
    },
  });
}

/* ── Switch transport sub-tab ───────────────────────── */
export function switchTransportSub(sub) {
  state.transportSubTab = sub;
  document.querySelectorAll(".transport-sub").forEach((b) => b.classList.toggle("active", b.dataset.tsub === sub));
  document.querySelectorAll(".transport-section").forEach((s) => s.style.display = "none");
  const target = $(`tsub-${sub}`); if (target) target.style.display = "block";
  if (sub === "outbox" && state.outboxItems.length === 0) loadOutboxPage().catch((e) => notify("Ошибка: " + e.message, true));
  if (sub === "events" && state.eventsItems.length === 0) loadEventsPage().catch((e) => notify("Ошибка: " + e.message, true));
}

/* ── Bind all transport event listeners ─────────────── */
export function bindTransportEvents() {
  $("transport-reload").addEventListener("click", () => loadTransportData().catch((e) => notify("Transport reload error: " + e.message, true)));
  document.querySelectorAll(".transport-sub").forEach((b) => b.addEventListener("click", () => switchTransportSub(b.dataset.tsub)));

  document.addEventListener("click", (e) => {
    const row = e.target.closest(".t-node-row");
    if (row) { loadTransportNodeDetail(row.dataset.nid).catch((er) => notify("Detail error: " + er.message, true)); return; }
    const payloadBtn = e.target.closest(".show-payload");
    if (payloadBtn) { showPayloadModal(payloadBtn.dataset.payload); return; }
    const retryBtn = e.target.closest(".outbox-retry");
    if (retryBtn) {
      const oid = retryBtn.dataset.oid;
      req(`/api/v1/admin/transport/outbox/${oid}/retry`, { method: "POST" })
        .then(() => { notify("Retried"); if (state.transportNodeDetail) loadTransportNodeDetail(state.transportNodeDetail.node_id); loadOutboxPage(); })
        .catch((er) => notify("Retry error: " + er.message, true));
      return;
    }
    const nextOutbox = e.target.closest(".outbox-page-next");
    if (nextOutbox) { e.preventDefault(); state.outboxOffset += 50; loadOutboxPage().catch(() => {}); return; }
    const nextEvents = e.target.closest(".events-page-next");
    if (nextEvents) { e.preventDefault(); state.eventsOffset += 50; loadEventsPage().catch(() => {}); return; }
  });

  $("tnd-close").addEventListener("click", () => { $("transport-node-detail").style.display = "none"; state.transportNodeDetail = null; });
  $("tnd-event-filter").addEventListener("change", renderTransportNodeDetail);
  $("tnd-snapshot").addEventListener("click", async () => {
    const d = state.transportNodeDetail; if (!d) return;
    const ok = await confirmAction("Force Snapshot", `Generate snapshot for ${d.name}?`, "btn-danger"); if (!ok) return;
    try { const res = await req(`/api/v1/admin/transport/nodes/${d.node_id}/request-snapshot`, { method: "POST" }); notify(`Snapshot generated: epoch ${res.epoch}, id ${res.snapshot_id}`); loadTransportNodeDetail(d.node_id); loadTransportData(); }
    catch (er) { notify("Snapshot error: " + er.message, true); }
  });
  $("tnd-retry-all").addEventListener("click", async () => {
    const d = state.transportNodeDetail; if (!d) return;
    try { const res = await req(`/api/v1/admin/transport/outbox/retry-all-failed?node_id=${d.node_id}`, { method: "POST" }); notify(`Retried ${res.retried_count} items`); loadTransportNodeDetail(d.node_id); }
    catch (er) { notify("Retry error: " + er.message, true); }
  });
  $("outbox-node-filter").addEventListener("change", () => { state.outboxOffset = 0; loadOutboxPage().catch(() => {}); });
  $("outbox-status-filter").addEventListener("change", () => { state.outboxOffset = 0; loadOutboxPage().catch(() => {}); });
  $("outbox-retry-all-btn").addEventListener("click", async () => {
    const nodeId = ($("outbox-node-filter") || {}).value || null;
    const params = nodeId ? `?node_id=${nodeId}` : "";
    try { const res = await req(`/api/v1/admin/transport/outbox/retry-all-failed${params}`, { method: "POST" }); notify(`Retried ${res.retried_count} items`); loadOutboxPage(); }
    catch (er) { notify("Retry error: " + er.message, true); }
  });
  $("events-node-filter").addEventListener("change", () => { state.eventsOffset = 0; loadEventsPage().catch(() => {}); });
  $("events-type-filter").addEventListener("change", () => { state.eventsOffset = 0; loadEventsPage().catch(() => {}); });
  $("events-search").addEventListener("input", (() => { let t; return () => { clearTimeout(t); t = setTimeout(() => { state.eventsOffset = 0; loadEventsPage().catch(() => {}); }, 400); }; })());
}
