import { state, refs, $ } from '../state.js';
import { fmtBytes, trafficPct, trafficBar, trafficRemaining, fmtDate, relTime, uuidCell, esc, chip, sortTh, sortedBy } from '../utils.js';
import { req } from '../api.js';
import { notify, showSkeleton, hideSkeleton, smoothUpdate, markRefreshing, renderPagination } from '../ui.js';

export async function loadTrafficKeys() {
  const params = new URLSearchParams();
  const search = refs.trafficSearch.value.trim(); if (search) params.set("search", search);
  const userId = refs.trafficUserId.value.trim(); if (userId) params.set("user_id", userId);
  const revoked = refs.trafficRevoked.value; if (revoked !== "") params.set("is_revoked", revoked);
  params.set("limit", String(state.trafficLimit)); params.set("offset", String(state.trafficOffset));
  showSkeleton("traffic-body", 5);
  markRefreshing("traffic-body");
  try {
    const data = await req(`/api/v1/admin/traffic/keys?${params}`);
    state.trafficKeys = data.items || []; state.trafficTotal = data.total || 0;
    renderTraffic(); updateTrafficKpis();
  } catch (e) {
    hideSkeleton("traffic-body");
    throw e;
  }
}

export function updateTrafficKpis() {
  const keys = state.trafficKeys;
  refs.kpiTrafficKeys.textContent = String(state.trafficTotal);
  const revokedCount = keys.filter((k) => k.is_revoked).length;
  refs.kpiTrafficRevoked.textContent = String(revokedCount);
  const totalBytes = keys.reduce((sum, k) => sum + (k.used_traffic_bytes || 0), 0);
  refs.kpiTrafficTotal.textContent = fmtBytes(totalBytes);
}

export async function loadTrafficHistory() {
  if (!state.trafficHistoryKeyId) return;
  const params = new URLSearchParams();
  params.set("limit", String(state.trafficHistoryLimit)); params.set("offset", String(state.trafficHistoryOffset));
  const df = refs.trafficHistoryFrom.value; const dt = refs.trafficHistoryTo.value;
  if (df) params.set("date_from", new Date(df).toISOString());
  if (dt) params.set("date_to", new Date(dt + "T23:59:59").toISOString());
  const data = await req(`/api/v1/admin/traffic/keys/${encodeURIComponent(state.trafficHistoryKeyId)}/history?${params}`);
  state.trafficHistory = data.items || []; state.trafficHistoryTotal = data.total || 0;
  renderTrafficHistory(); renderTrafficChart();
}

const trafficComparators = {
  used: (a, b) => (a.used_traffic_bytes || 0) - (b.used_traffic_bytes || 0),
  limit: (a, b) => (a.traffic_limit_mb || 0) - (b.traffic_limit_mb || 0),
  pct: (a, b) => (trafficPct(a.used_traffic_bytes, a.traffic_limit_mb) || 0) - (trafficPct(b.used_traffic_bytes, b.traffic_limit_mb) || 0),
  status: (a, b) => (a.is_revoked === b.is_revoked ? 0 : a.is_revoked ? 1 : -1),
  expires: (a, b) => new Date(a.valid_until || 0).getTime() - new Date(b.valid_until || 0).getTime(),
};

export function renderTraffic() {
  const keys = state.trafficKeys;
  const activeCount = keys.filter((k) => !k.is_revoked).length;
  const revokedCount = keys.filter((k) => k.is_revoked).length;
  const nearLimit = keys.filter((k) => { const p = trafficPct(k.used_traffic_bytes, k.traffic_limit_mb); return p !== null && p >= 90; }).length;
  let metaHtml = `${chip("info", "\u0432\u0441\u0435\u0433\u043E: " + state.trafficTotal)} ${chip("ok", "\u0430\u043A\u0442\u0438\u0432\u043D\u044B\u0445: " + activeCount)} ${chip("bad", "\u043E\u0442\u043E\u0437\u0432\u0430\u043D\u043D\u044B\u0445: " + revokedCount)}`;
  if (nearLimit > 0) metaHtml += ` ${chip("warn", "\u26A0 \u0431\u043B\u0438\u0437\u043A\u043E \u043A \u043B\u0438\u043C\u0438\u0442\u0443: " + nearLimit)}`;
  refs.trafficMeta.innerHTML = metaHtml;
  refs.trafficHead.innerHTML = `<tr>${sortTh("traffic", "client_id", "\u041A\u043B\u044E\u0447 / client_id")}<th>\u041F\u043E\u043B\u044C\u0437\u043E\u0432\u0430\u0442\u0435\u043B\u044C</th><th>\u041F\u0440\u043E\u0442\u043E\u043A\u043E\u043B</th>${sortTh("traffic", "used", "\u0418\u0441\u043F\u043E\u043B\u044C\u0437\u043E\u0432\u0430\u043D\u043E")}${sortTh("traffic", "limit", "\u041B\u0438\u043C\u0438\u0442")}<th>\u041E\u0441\u0442\u0430\u0442\u043E\u043A</th>${sortTh("traffic", "pct", "\u0418\u0441\u043F\u043E\u043B\u044C\u0437\u043E\u0432\u0430\u043D\u0438\u0435")}${sortTh("traffic", "status", "\u0421\u0442\u0430\u0442\u0443\u0441")}${sortTh("traffic", "expires", "\u0418\u0441\u0442\u0435\u043A\u0430\u0435\u0442")}<th>\u0414\u0435\u0439\u0441\u0442\u0432\u0438\u044F</th></tr>`;
  const sorted = sortedBy([...keys], "traffic", trafficComparators);
  const trafficHtml = sorted.length
    ? sorted.map((k) => {
      const pct = trafficPct(k.used_traffic_bytes, k.traffic_limit_mb);
      const isNearLimit = pct !== null && pct >= 90 && !k.is_revoked;
      const statusChip = k.is_revoked ? chip("bad", "\u043E\u0442\u043E\u0437\u0432\u0430\u043D") : (isNearLimit ? chip("warn", "\u26A0 \u043B\u0438\u043C\u0438\u0442") : chip("ok", "\u0430\u043A\u0442\u0438\u0432\u0435\u043D"));
      const rowStyle = isNearLimit ? ' style="background:rgba(245,198,107,0.06)"' : (k.is_revoked ? ' style="background:rgba(255,127,133,0.04)"' : "");
      return `<tr${rowStyle}><td><div>${uuidCell(k.id)}</div><div class="mono muted" style="font-size:11px">${esc(k.client_id)}</div></td><td>${uuidCell(k.user_id)}</td><td><span class="mono">${esc(k.protocol)}/${esc(k.transport)}</span></td><td class="mono">${fmtBytes(k.used_traffic_bytes)}</td><td class="mono">${k.traffic_limit_mb ? fmtBytes(k.traffic_limit_mb * 1024 * 1024) : "\u2014"}</td><td>${trafficRemaining(k.used_traffic_bytes, k.traffic_limit_mb)}</td><td>${trafficBar(k.used_traffic_bytes, k.traffic_limit_mb)}</td><td>${statusChip}</td><td>${relTime(k.valid_until)}</td><td><button class="btn-mini traffic-history-btn" data-key-idx="${esc(keys.indexOf(k))}" data-key-id="${esc(k.id)}" data-client-id="${esc(k.client_id)}">\u0418\u0441\u0442\u043E\u0440\u0438\u044F</button></td></tr>`;
    }).join("")
    : `<tr><td colspan="10" class="empty">\u041D\u0435\u0442 \u0434\u0430\u043D\u043D\u044B\u0445. \u041D\u0430\u0436\u043C\u0438\u0442\u0435 \u00AB\u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044C\u00BB.</td></tr>`;
  smoothUpdate("traffic-body", trafficHtml);
  renderPagination(refs.trafficPagination, state.trafficTotal, state.trafficLimit, state.trafficOffset, (page) => {
    state.trafficOffset = page * state.trafficLimit;
    loadTrafficKeys().catch((e) => notify("\u041E\u0448\u0438\u0431\u043A\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043A\u0438 \u0442\u0440\u0430\u0444\u0438\u043A\u0430: " + e.message, true));
  });
}

function renderTrafficHistoryKeyInfo() {
  const k = state.trafficHistoryKeyData; if (!k) { refs.trafficHistoryKeyInfo.innerHTML = ""; return; }
  const pct = trafficPct(k.used_traffic_bytes, k.traffic_limit_mb);
  refs.trafficHistoryKeyInfo.innerHTML = `<div style="display:flex;gap:16px;flex-wrap:wrap;align-items:center"><div>${uuidCell(k.id)} <span class="mono muted" style="font-size:11px">${esc(k.client_id)}</span></div><div>${chip("info", esc(k.protocol) + "/" + esc(k.transport))}</div><div>${k.is_revoked ? chip("bad", "\u043E\u0442\u043E\u0437\u0432\u0430\u043D") : chip("ok", "\u0430\u043A\u0442\u0438\u0432\u0435\u043D")}</div><div class="mono" style="font-size:12px">${fmtBytes(k.used_traffic_bytes)} / ${k.traffic_limit_mb ? fmtBytes(k.traffic_limit_mb * 1024 * 1024) : "\u221E"}${pct !== null ? " (" + pct + "%)" : ""}</div><div>${trafficBar(k.used_traffic_bytes, k.traffic_limit_mb)}</div></div>`;
}

export function renderTrafficHistory() {
  renderTrafficHistoryKeyInfo();
  refs.trafficHistoryBody.innerHTML = state.trafficHistory.length
    ? state.trafficHistory.map((h) => `<tr><td>${fmtDate(h.created_at)}</td><td class="mono">${fmtBytes(h.delta_bytes)}</td><td class="mono">${fmtBytes(h.reported_total_bytes)}</td></tr>`).join("")
    : `<tr><td colspan="3" class="empty">\u041D\u0435\u0442 \u0437\u0430\u043F\u0438\u0441\u0435\u0439 \u0437\u0430 \u0432\u044B\u0431\u0440\u0430\u043D\u043D\u044B\u0439 \u043F\u0435\u0440\u0438\u043E\u0434.</td></tr>`;
  renderPagination(refs.trafficHistoryPagination, state.trafficHistoryTotal, state.trafficHistoryLimit, state.trafficHistoryOffset, (page) => {
    state.trafficHistoryOffset = page * state.trafficHistoryLimit;
    loadTrafficHistory().catch((e) => notify("\u041E\u0448\u0438\u0431\u043A\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043A\u0438 \u0438\u0441\u0442\u043E\u0440\u0438\u0438: " + e.message, true));
  });
}

/* Sparkline chart */
export function renderTrafficChart() {
  const items = state.trafficHistory;
  if (items.length < 2) { refs.trafficChartContainer.style.display = "none"; return; }
  refs.trafficChartContainer.style.display = "block";
  const canvas = refs.trafficChart; const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = (rect.width - 20) * dpr; canvas.height = 120 * dpr;
  canvas.style.width = (rect.width - 20) + "px"; canvas.style.height = "120px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = rect.width - 20; const h = 120; ctx.clearRect(0, 0, w, h);
  const pts = [...items].reverse(); const vals = pts.map((p) => p.delta_bytes); const maxV = Math.max(...vals, 1);
  const padTop = 10, padBot = 20, padLeft = 4, padRight = 4;
  const chartW = w - padLeft - padRight; const chartH = h - padTop - padBot;
  ctx.strokeStyle = "rgba(255,255,255,0.06)"; ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i++) { const y = padTop + chartH * (1 - i / 3); ctx.beginPath(); ctx.moveTo(padLeft, y); ctx.lineTo(w - padRight, y); ctx.stroke(); }
  ctx.beginPath();
  pts.forEach((p, i) => { const x = padLeft + (i / (pts.length - 1)) * chartW; const y = padTop + chartH * (1 - vals[i] / maxV); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
  ctx.lineTo(padLeft + chartW, padTop + chartH); ctx.lineTo(padLeft, padTop + chartH); ctx.closePath();
  const grad = ctx.createLinearGradient(0, padTop, 0, h); grad.addColorStop(0, "rgba(45,212,191,0.28)"); grad.addColorStop(1, "rgba(45,212,191,0.02)");
  ctx.fillStyle = grad; ctx.fill();
  ctx.beginPath();
  pts.forEach((p, i) => { const x = padLeft + (i / (pts.length - 1)) * chartW; const y = padTop + chartH * (1 - vals[i] / maxV); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
  ctx.strokeStyle = "#2dd4bf"; ctx.lineWidth = 2; ctx.stroke();
  pts.forEach((p, i) => { const x = padLeft + (i / (pts.length - 1)) * chartW; const y = padTop + chartH * (1 - vals[i] / maxV); ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fillStyle = "#2dd4bf"; ctx.fill(); });
  ctx.fillStyle = "rgba(159,179,207,0.7)"; ctx.font = "10px 'JetBrains Mono', monospace"; ctx.textBaseline = "top";
  const labelY = h - padBot + 4;
  if (pts.length >= 2) {
    const fmtShort = (dt) => { const d = new Date(dt); return (d.getMonth() + 1) + "/" + d.getDate() + " " + d.getHours() + ":" + String(d.getMinutes()).padStart(2, "0"); };
    ctx.textAlign = "left"; ctx.fillText(fmtShort(pts[0].created_at), padLeft, labelY);
    ctx.textAlign = "right"; ctx.fillText(fmtShort(pts[pts.length - 1].created_at), w - padRight, labelY);
    if (pts.length > 4) { const mid = Math.floor(pts.length / 2); ctx.textAlign = "center"; ctx.fillText(fmtShort(pts[mid].created_at), padLeft + (mid / (pts.length - 1)) * chartW, labelY); }
  }
  ctx.textAlign = "right"; ctx.fillText(fmtBytes(maxV), w - padRight, padTop - 2);
}

export function bindTrafficEvents() {
  refs.trafficReload.addEventListener("click", () => { state.trafficOffset = 0; loadTrafficKeys().catch((e) => notify("\u041E\u0448\u0438\u0431\u043A\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043A\u0438 \u0442\u0440\u0430\u0444\u0438\u043A\u0430: " + e.message, true)); });
  [refs.trafficSearch, refs.trafficUserId].forEach((el) => { el.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); refs.trafficReload.click(); } }); });

  refs.trafficBody.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".traffic-history-btn"); if (!btn) return;
    state.trafficHistoryKeyId = btn.dataset.keyId; state.trafficHistoryOffset = 0;
    const idx = Number(btn.dataset.keyIdx); state.trafficHistoryKeyData = state.trafficKeys[idx] || null;
    refs.trafficHistoryKeyLabel.textContent = btn.dataset.clientId || btn.dataset.keyId;
    refs.trafficHistorySection.style.display = "block";
    refs.trafficHistorySection.scrollIntoView({ behavior: "smooth", block: "start" });
    loadTrafficHistory().catch((e) => notify("\u041E\u0448\u0438\u0431\u043A\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043A\u0438 \u0438\u0441\u0442\u043E\u0440\u0438\u0438: " + e.message, true));
  });
  refs.trafficHistoryReload.addEventListener("click", () => { state.trafficHistoryOffset = 0; loadTrafficHistory().catch((e) => notify("\u041E\u0448\u0438\u0431\u043A\u0430: " + e.message, true)); });
  refs.trafficHistoryClose.addEventListener("click", () => {
    refs.trafficHistorySection.style.display = "none"; refs.trafficChartContainer.style.display = "none";
    state.trafficHistoryKeyId = null; state.trafficHistoryKeyData = null; state.trafficHistory = [];
  });
}
