import { state, refs, TABLE_LIMIT } from '../state.js';
import {
  esc, fmtDate, chip, uuidCell,
} from '../utils.js';
import { notify } from '../ui.js';

/* ── Late-binding callbacks (set by app.js) ────────── */
let _refreshAll = () => {};
let _render = () => {};
export function setCallbacks(refreshAll, render) { _refreshAll = refreshAll; _render = render; }

/* ── filteredPlacements ────────────────────────────── */
export function filteredPlacements() {
  const node = refs.placementsNode.value.trim().toLowerCase();
  const key = refs.placementsKey.value.trim().toLowerCase();
  const desired = refs.placementsDesired.value;
  const applied = refs.placementsApplied.value;
  return state.placements.filter((p) => {
    if (node && String(p.backend_node_id).toLowerCase() !== node) return false;
    if (key && String(p.key_id).toLowerCase() !== key) return false;
    if (desired && p.desired_state !== desired) return false;
    if (applied && p.applied_state !== applied) return false;
    return true;
  });
}

/* ── renderPlacementMeta ───────────────────────────── */
export function renderPlacementMeta() {
  const total = state.placements.length;
  if (!total) { refs.placementsMeta.innerHTML = "Плейсменты не загружены."; return; }
  const byKey = new Map();
  state.placements.forEach((placement) => { const keyId = String(placement.key_id || ""); if (!keyId) return; byKey.set(keyId, (byKey.get(keyId) || 0) + 1); });
  const keysTotal = byKey.size;
  const replicated = Array.from(byKey.values()).filter((count) => count > 1).length;
  const maxReplicas = keysTotal ? Math.max(...Array.from(byKey.values())) : 0;
  const avgReplicas = keysTotal ? (total / keysTotal).toFixed(2) : "0.00";
  refs.placementsMeta.innerHTML = `${chip("info", `placements: ${total}`)} ${chip("info", `keys: ${keysTotal}`)} ${chip(replicated > 0 ? "warn" : "ok", `keys >1 node: ${replicated}`)} ${chip("info", `avg replicas/key: ${avgReplicas}`)} ${chip("info", `max replicas/key: ${maxReplicas}`)}`;
}

/* ── renderPlacements ──────────────────────────────── */
export function renderPlacements() {
  const placements = filteredPlacements().slice(0, TABLE_LIMIT);
  renderPlacementMeta();
  refs.placementsBody.innerHTML = placements.length
    ? placements.map((p) => {
      const unsync = p.op_version !== p.applied_version;
      return `<tr><td>${uuidCell(p.id)}</td><td>${uuidCell(p.key_id)}</td><td>${uuidCell(p.backend_node_id)}</td><td class="mono">${esc(p.op_version)}/${esc(p.applied_version != null ? p.applied_version : "?")}${unsync ? " " + chip("warn", "unsync") : ""}</td><td>${p.desired_state === "active" ? chip("ok", "active") : chip("warn", "inactive")}</td><td>${p.applied_state === "applied" ? chip("ok", "applied") : (p.applied_state === "pending" ? chip("warn", "pending") : chip("bad", "error"))}</td><td>${esc(p.last_migration_reason || "-")}</td><td>${fmtDate(p.updated_at)}</td></tr>`;
    }).join("")
    : `<tr><td colspan="8" class="empty">Нет плейсментов по фильтрам.</td></tr>`;
}

/* ── bindPlacementEvents ───────────────────────────── */
export function bindPlacementEvents() {
  refs.placementsReload.addEventListener("click", () => _refreshAll(true).catch((e) => notify(`Ошибка: ${e.message}`, true)));
}
