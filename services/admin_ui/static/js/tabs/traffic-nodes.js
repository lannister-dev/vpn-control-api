import { state, refs } from '../state.js';
import { esc, fmtBytes, fmtDate, uuidCell, chip } from '../utils.js';
import { req } from '../api.js';
import { notify, smoothUpdate, markRefreshing } from '../ui.js';

const ROLE_LABEL = {
  entry: "Entry",
  whitelist_entry: "Whitelist",
  backend: "Backend",
};

export async function loadNodesTraffic() {
  const period = state.trafficNodesPeriod;
  const role = state.trafficNodesRole;
  const params = new URLSearchParams({ period });
  if (role) params.set("role", role);

  const nodesBody = document.getElementById("traffic-nodes-body");
  const pairsBody = document.getElementById("traffic-pairs-body");
  markRefreshing("traffic-nodes-body");
  markRefreshing("traffic-pairs-body");

  try {
    const [summary, pairs] = await Promise.all([
      req(`/api/v1/admin/traffic/nodes?${params}`),
      req(`/api/v1/admin/traffic/nodes/pairs?period=${encodeURIComponent(period)}`),
    ]);

    state.trafficNodes = summary.items || [];
    state.trafficPairs = pairs.items || [];

    const totalBytes = state.trafficNodes.reduce((s, n) => s + (n.total_bytes || 0), 0);
    const activeSessions = state.trafficNodes.reduce((s, n) => s + (n.active_sessions || 0), 0);
    refs.trafficNodesMeta.innerHTML =
      `${chip("info", "серверов: " + state.trafficNodes.length)} ` +
      `${chip("ok", "сессий сейчас: " + activeSessions)} ` +
      `${chip("cyan", "трафика за период: " + fmtBytes(totalBytes))} ` +
      `<span class="muted" style="font-size:11px;margin-left:8px">${fmtDate(summary.from_ts)} — ${fmtDate(summary.to_ts)}</span>`;

    renderTrafficNodes();
    renderTrafficPairs();
  } finally {
    if (nodesBody) nodesBody.classList.remove("refreshing");
    if (pairsBody) pairsBody.classList.remove("refreshing");
  }
}

export function renderTrafficNodes() {
  const rows = state.trafficNodes;
  if (!rows.length) {
    const period = state.trafficNodesPeriod || "24h";
    const role = state.trafficNodesRole;
    const canExpand = period !== "30d";
    const roleFiltered = !!role;
    const title = roleFiltered
      ? `Нет серверов с ролью «${ROLE_LABEL[role] || role}»`
      : "Нет трафика за выбранный период";
    const hint = roleFiltered
      ? `Фильтр роли исключил все сервера. Снимите фильтр или поменяйте роль.`
      : `Данные появляются, когда entry-агенты отчитываются о сессиях.<br/>Попробуйте увеличить период или проверьте, что агенты онлайн в разделе Transport.`;
    const actions = roleFiltered
      ? `<button class="btn btn-primary btn-auto tn-clear-role">Снять фильтр роли</button>`
      : `${canExpand ? `<button class="btn btn-primary btn-auto tn-expand-period">Период: 7 дней</button>` : ""}<button class="btn btn-ghost btn-auto tn-goto-transport">Открыть Transport</button>`;
    smoothUpdate("traffic-nodes-body", `<tr><td colspan="10"><div class="empty-state">
      <div class="empty-state-icon">\uD83D\uDCE1</div>
      <div class="empty-state-title">${esc(title)}</div>
      <div class="empty-state-hint">${hint}</div>
      <div class="empty-state-action">${actions}</div>
    </div></td></tr>`);
    return;
  }
  const html = rows.map((n) => {
    const statusChip = n.is_draining
      ? chip("warn", "draining")
      : !n.is_enabled
        ? chip("bad", "disabled")
        : chip("ok", "active");
    const roleChip = chip("info", ROLE_LABEL[n.role] || n.role);
    return `<tr data-focusable tabindex="0">
      <td><div class="mono" style="font-weight:600">${esc(n.name)}</div><div>${uuidCell(n.node_id)}</div></td>
      <td>${roleChip}</td>
      <td class="mono">${esc(n.region || "—")}</td>
      <td class="mono">${fmtBytes(n.bytes_in)}</td>
      <td class="mono">${fmtBytes(n.bytes_out)}</td>
      <td class="mono" style="font-weight:600">${fmtBytes(n.total_bytes)}</td>
      <td class="mono">${n.active_sessions}</td>
      <td class="mono">${n.total_sessions}</td>
      <td>${statusChip}</td>
      <td><button class="btn-mini traffic-node-detail-btn"
            data-node-id="${esc(n.node_id)}"
            data-node-name="${esc(n.name)}"
            data-node-role="${esc(n.role)}">График</button></td>
    </tr>`;
  }).join("");
  smoothUpdate("traffic-nodes-body", html);
}

export function renderTrafficPairs() {
  const rows = state.trafficPairs;
  if (!rows.length) {
    smoothUpdate("traffic-pairs-body", `<tr><td colspan="6" class="empty">Пока нет агрегатов по парам Entry × Backend.</td></tr>`);
    return;
  }
  const html = rows.map((p) => `
    <tr>
      <td><div class="mono" style="font-weight:600">${esc(p.entry_name)}</div><div>${uuidCell(p.entry_node_id)}</div></td>
      <td>${p.backend_node_id
        ? `<div class="mono" style="font-weight:600">${esc(p.backend_name || "—")}</div><div>${uuidCell(p.backend_node_id)}</div>`
        : `<span class="muted">пусто</span>`}</td>
      <td class="mono">${fmtBytes(p.bytes_in)}</td>
      <td class="mono">${fmtBytes(p.bytes_out)}</td>
      <td class="mono" style="font-weight:600">${fmtBytes(p.total_bytes)}</td>
      <td class="mono">${p.total_sessions}</td>
    </tr>
  `).join("");
  smoothUpdate("traffic-pairs-body", html);
}

export async function loadNodeTimeseries() {
  if (!state.trafficNodeSelectedId) return;
  const params = new URLSearchParams({
    period: state.trafficNodesPeriod,
    side: state.trafficNodeSelectedSide,
  });
  const data = await req(
    `/api/v1/admin/traffic/nodes/${encodeURIComponent(state.trafficNodeSelectedId)}/timeseries?${params}`
  );
  state.trafficNodeTimeseries = data;
  renderNodeTimeseries();
}

export function renderNodeTimeseries() {
  const data = state.trafficNodeTimeseries;
  if (!data) {
    refs.trafficNodeChartContainer.style.display = "none";
    refs.trafficNodeTimeseriesMeta.textContent = "";
    return;
  }
  refs.trafficNodeTimeseriesMeta.textContent =
    `${data.points.length} точек · bucket ${data.resolution_seconds}s · ${fmtDate(data.from_ts)} — ${fmtDate(data.to_ts)}`;
  refs.trafficNodeChartContainer.style.display = "block";
  drawStackedArea(refs.trafficNodeChart, data.points);
}

function drawStackedArea(canvas, points) {
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.parentElement.getBoundingClientRect();
  const w = rect.width - 20;
  const h = 180;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = w + "px";
  canvas.style.height = h + "px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  if (points.length === 0) {
    ctx.fillStyle = "rgba(159,179,207,0.6)";
    ctx.font = "12px 'JetBrains Mono', monospace";
    ctx.textAlign = "center";
    ctx.fillText("Нет данных", w / 2, h / 2);
    return;
  }

  const padT = 12, padB = 22, padL = 6, padR = 6;
  const chartW = w - padL - padR;
  const chartH = h - padT - padB;

  const maxV = Math.max(1, ...points.map((p) => Math.max(p.bytes_in, p.bytes_out)));

  ctx.strokeStyle = "rgba(255,255,255,0.06)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i++) {
    const y = padT + chartH * (1 - i / 3);
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(w - padR, y);
    ctx.stroke();
  }

  const plotSeries = (values, color, fillColor) => {
    ctx.beginPath();
    values.forEach((v, i) => {
      const x = padL + (i / Math.max(1, values.length - 1)) * chartW;
      const y = padT + chartH * (1 - v / maxV);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineTo(padL + chartW, padT + chartH);
    ctx.lineTo(padL, padT + chartH);
    ctx.closePath();
    ctx.fillStyle = fillColor;
    ctx.fill();

    ctx.beginPath();
    values.forEach((v, i) => {
      const x = padL + (i / Math.max(1, values.length - 1)) * chartW;
      const y = padT + chartH * (1 - v / maxV);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();
  };

  plotSeries(points.map((p) => p.bytes_in), "#2dd4bf", "rgba(45,212,191,0.18)");
  plotSeries(points.map((p) => p.bytes_out), "#f59e0b", "rgba(245,158,11,0.14)");

  ctx.fillStyle = "rgba(159,179,207,0.7)";
  ctx.font = "10px 'JetBrains Mono', monospace";
  ctx.textBaseline = "top";
  ctx.textAlign = "right";
  ctx.fillText(fmtBytes(maxV) + "/bucket", w - padR, padT - 2);

  const label = (dt) => {
    const d = new Date(dt);
    return (d.getMonth() + 1) + "/" + d.getDate() + " " + d.getHours() + ":" + String(d.getMinutes()).padStart(2, "0");
  };
  const labelY = h - padB + 4;
  ctx.textAlign = "left";
  ctx.fillText(label(points[0].ts), padL, labelY);
  ctx.textAlign = "right";
  ctx.fillText(label(points[points.length - 1].ts), w - padR, labelY);

  ctx.textAlign = "right";
  ctx.fillStyle = "#2dd4bf";
  ctx.fillText("in", w - padR - 40, padT);
  ctx.fillStyle = "#f59e0b";
  ctx.fillText("out", w - padR - 20, padT);
}

export function bindTrafficNodesEvents() {
  refs.trafficNodesPeriod.addEventListener("change", () => {
    state.trafficNodesPeriod = refs.trafficNodesPeriod.value;
    loadNodesTraffic().catch((e) => notify("Ошибка загрузки: " + e.message, true));
    if (state.trafficNodeSelectedId) {
      loadNodeTimeseries().catch(() => {});
    }
  });
  refs.trafficNodesRole.addEventListener("change", () => {
    state.trafficNodesRole = refs.trafficNodesRole.value;
    loadNodesTraffic().catch((e) => notify("Ошибка загрузки: " + e.message, true));
  });
  refs.trafficNodesReload.addEventListener("click", () => {
    loadNodesTraffic().catch((e) => notify("Ошибка загрузки: " + e.message, true));
  });

  refs.trafficNodesBody.addEventListener("click", (ev) => {
    const target = ev.target;
    if (!(target instanceof HTMLElement)) return;

    const expandBtn = target.closest(".tn-expand-period");
    if (expandBtn) {
      state.trafficNodesPeriod = "7d";
      refs.trafficNodesPeriod.value = "7d";
      loadNodesTraffic().catch((e) => notify("Ошибка загрузки: " + e.message, true));
      return;
    }
    const clearRole = target.closest(".tn-clear-role");
    if (clearRole) {
      state.trafficNodesRole = "";
      refs.trafficNodesRole.value = "";
      loadNodesTraffic().catch((e) => notify("Ошибка загрузки: " + e.message, true));
      return;
    }
    const gotoTransport = target.closest(".tn-goto-transport");
    if (gotoTransport) {
      const btn = document.querySelector('.nav button[data-tab="transport"]');
      if (btn) btn.click();
      return;
    }
    const btn = target.closest(".traffic-node-detail-btn");
    if (!btn) return;
    state.trafficNodeSelectedId = btn.dataset.nodeId;
    state.trafficNodeSelectedSide = "auto";
    refs.trafficNodeSide.value = "auto";
    refs.trafficNodeDetailLabel.textContent = btn.dataset.nodeName;
    refs.trafficNodeDetailSection.style.display = "block";
    refs.trafficNodeDetailSection.scrollIntoView({ behavior: "smooth", block: "start" });
    loadNodeTimeseries().catch((e) => notify("Ошибка загрузки графика: " + e.message, true));
  });

  refs.trafficNodeSide.addEventListener("change", () => {
    state.trafficNodeSelectedSide = refs.trafficNodeSide.value;
    if (state.trafficNodeSelectedId) {
      loadNodeTimeseries().catch((e) => notify("Ошибка загрузки графика: " + e.message, true));
    }
  });

  refs.trafficNodeDetailClose.addEventListener("click", () => {
    refs.trafficNodeDetailSection.style.display = "none";
    refs.trafficNodeChartContainer.style.display = "none";
    state.trafficNodeSelectedId = null;
    state.trafficNodeTimeseries = null;
  });
}
