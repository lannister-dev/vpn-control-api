import { state } from './state.js';

const numberFormatter = new Intl.NumberFormat("ru-RU");

export const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
export const fmtDate = (v) => { if (!v) return "-"; const d = new Date(v); return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString(); };
export const chip = (cls, txt) => `<span class="badge ${cls}">${esc(txt)}</span>`;
export const routeStatusLabel = (s) => ({ healthy: "Стабильный", degraded: "Деградация", suspected: "Подозрение", blocked: "Заблокирован", warming_up: "Прогрев" }[s] || s);
export const nodeRoleLabel = (s) => ({
  backend: "Backend",
  whitelist_entry: "Whitelist Entry",
  entry: "Entry Relay",
}[String(s || "").toLowerCase()] || String(s || "-"));
export const nodeRoleClass = (s) => ({
  backend: "ok",
  whitelist_entry: "info",
  entry: "warn",
}[String(s || "").toLowerCase()] || "info");
export const routingReasonLabel = (s) => ({
  node_role_excluded: "role excluded",
  node_inactive: "node inactive", node_disabled: "disabled", node_draining: "draining",
  agent_state_missing: "нет agent state", agent_unhealthy: "agent unhealthy",
  heartbeat_missing: "нет heartbeat", heartbeat_stale: "heartbeat stale",
}[s] || s || "");
export const routeReasonLabel = (s) => ({
  route_inactive: "route inactive", route_zero_weight: "zero weight", route_health_excluded: "health excluded",
  transport_inactive: "transport inactive", node_inactive: "node inactive", node_disabled: "disabled",
  node_draining: "draining", agent_state_missing: "нет agent state", agent_unhealthy: "agent unhealthy",
  heartbeat_missing: "нет heartbeat", heartbeat_stale: "heartbeat stale",
}[s] || s || "");

export function shortId(uuid, len) { return String(uuid || "").substring(0, len || 8); }
export function uuidCell(uuid) {
  const id = String(uuid || "");
  return `<span class="uuid" title="${esc(id)}" data-copy="${esc(id)}">${esc(shortId(id))}&hellip;</span>`;
}
export function nodeNameById(nodeId) {
  if (!state.status || !state.status.nodes) return null;
  const n = state.status.nodes.find((x) => x.id === nodeId);
  return n ? n.name : null;
}
export function latestProbeForNode(nodeId) {
  if (!nodeId) return null;
  return state.probes.find((p) => p.node_id === nodeId) || null;
}
export function probeChip(nodeId) {
  const p = latestProbeForNode(nodeId);
  if (!p) return `<span class="muted" style="font-size:11px">no probe</span>`;
  const label = p.is_reachable ? "probe ok" : "probe fail";
  const cls = p.is_reachable ? "ok" : "bad";
  const extra = p.latency_ms != null && p.is_reachable ? ` ${p.latency_ms}ms` : "";
  return chip(cls, label + extra);
}
export function latestProbeForRoute(routeId) {
  if (!routeId) return null;
  return state.probes.find((p) => p.route_id === routeId) || null;
}
export function relTime(v) {
  if (!v) return "-";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "-";
  const diff = Date.now() - d.getTime();
  const sec = Math.floor(Math.abs(diff) / 1000);
  const suffix = diff < 0 ? "" : " ago";
  const prefix = diff < 0 ? "in " : "";
  if (sec < 60) return prefix + sec + "s" + suffix;
  if (sec < 3600) return prefix + Math.floor(sec / 60) + "m" + suffix;
  if (sec < 86400) return prefix + Math.floor(sec / 3600) + "h" + suffix;
  return prefix + Math.floor(sec / 86400) + "d" + suffix;
}
export function capacityBar(used, total) {
  if (!total || total <= 0) return `<span class="mono">${used || 0}</span>`;
  const pct = Math.min(100, Math.round((used / total) * 100));
  const cls = pct < 60 ? "low" : pct < 85 ? "mid" : "high";
  return `<div><span class="mono" style="font-size:11px">${used}/${total}</span><div class="capacity-bar"><div class="capacity-fill ${cls}" style="width:${pct}%"></div></div></div>`;
}
export function transportLabel(transport) {
  return ({ reality: "Reality", ws: "WS", xhttp: "XHTTP", tcp: "TCP" }[String(transport || "").toLowerCase()]) || String(transport || "-").toUpperCase();
}
export function renderTransportBundle(device) {
  const keys = Array.isArray(device && device.transport_keys) ? device.transport_keys : [];
  if (!keys.length) return `<div class="empty">Bundle не загружен</div>`;
  const summary = keys.map((k) => chip(k.is_primary ? "info" : "ok", `${transportLabel(k.transport)}${k.is_primary ? " primary" : ""}`)).join("");
  const items = keys.map((k) => `<div class="bundle-item"><span>${chip(k.is_primary ? "info" : "ok", transportLabel(k.transport))}</span><span class="mono">${uuidCell(k.vpn_key_id)}</span></div>`).join("");
  return `<div class="bundle-summary">${summary}</div><div class="bundle-list">${items}</div>`;
}
export function formatNumber(num) {
  return numberFormatter.format(num);
}
export function parseDateTimeLocal(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) return null;
  return dt.toISOString();
}
export function fmtBytes(bytes) {
  if (bytes == null || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0; let v = bytes;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return v.toFixed(i === 0 ? 0 : 2) + " " + units[i];
}
export function fmtTrafficLimit(bytes) {
  if (!bytes || bytes <= 0) return '<span class="badge ok">Безлимит</span>';
  if (bytes >= 1024 * 1024 * 1024) return (bytes / (1024 * 1024 * 1024)).toFixed(1) + " GB";
  return (bytes / (1024 * 1024)).toFixed(0) + " MB";
}
export function trafficPct(usedBytes, limitMb) { if (!limitMb || limitMb <= 0) return null; const limitBytes = limitMb * 1024 * 1024; return Math.min(100, Math.round((usedBytes / limitBytes) * 100)); }
export function trafficBar(usedBytes, limitMb) {
  const pct = trafficPct(usedBytes, limitMb);
  if (pct === null) return `<span class="muted">без лимита</span>`;
  const cls = pct < 60 ? "low" : pct < 85 ? "mid" : "high";
  return `<div><span class="mono" style="font-size:11px">${pct}%</span><div class="capacity-bar"><div class="capacity-fill ${cls}" style="width:${pct}%"></div></div></div>`;
}
export function trafficRemaining(usedBytes, limitMb) {
  if (!limitMb || limitMb <= 0) return `<span class="muted">\u221E</span>`;
  const limitBytes = limitMb * 1024 * 1024; const rem = Math.max(0, limitBytes - (usedBytes || 0));
  const pct = trafficPct(usedBytes, limitMb); const cls = pct >= 90 ? "bad" : (pct >= 75 ? "warn" : "");
  return `<span class="mono ${cls}">${fmtBytes(rem)}</span>`;
}

/* Sorting */
export const sortState = {};
export function toggleSort(tableId, key) {
  if (sortState[tableId] && sortState[tableId].key === key) { sortState[tableId].asc = !sortState[tableId].asc; }
  else { sortState[tableId] = { key: key, asc: true }; }
}
export function sortTh(tableId, key, label) {
  const s = sortState[tableId];
  const arrow = s && s.key === key ? (s.asc ? " \u25B2" : " \u25BC") : "";
  return `<th class="sortable" data-sort-key="${key}" data-sort-table="${tableId}">${label}${arrow}</th>`;
}
export function sortedBy(arr, tableId, comparators) {
  const s = sortState[tableId];
  if (!s || !comparators[s.key]) return arr;
  const sorted = [...arr].sort(comparators[s.key]);
  return s.asc ? sorted : sorted.reverse();
}

/* Geo */
export const UNKNOWN_FLAG = "\uD83C\uDF10";
export const REGION_TO_COUNTRY_CODE = {
  fi: "FI", hel: "FI", de: "DE", fra: "DE", nl: "NL", ams: "NL", pl: "PL", waw: "PL",
  gb: "GB", uk: "GB", lon: "GB", fr: "FR", par: "FR", es: "ES", mad: "ES", it: "IT",
  rom: "IT", mil: "IT", se: "SE", sto: "SE", no: "NO", osl: "NO", dk: "DK", cph: "DK",
  ch: "CH", zrh: "CH", at: "AT", vie: "AT", cz: "CZ", prg: "CZ", us: "US", nyc: "US",
  lax: "US", ca: "CA", tor: "CA", sg: "SG", jp: "JP", tok: "JP", kr: "KR", sel: "KR",
  hk: "HK", au: "AU", syd: "AU", in: "IN", tr: "TR", ua: "UA", ru: "RU", kz: "KZ",
  ae: "AE", dxb: "AE", br: "BR", mx: "MX", il: "IL", lv: "LV", rig: "LV",
};
export const COUNTRY_CODE_TO_NAME = {
  FI: "Finland", DE: "Germany", NL: "Netherlands", PL: "Poland", GB: "United Kingdom",
  FR: "France", ES: "Spain", IT: "Italy", SE: "Sweden", NO: "Norway", DK: "Denmark",
  CH: "Switzerland", AT: "Austria", CZ: "Czechia", US: "United States", CA: "Canada",
  SG: "Singapore", JP: "Japan", KR: "South Korea", HK: "Hong Kong", AU: "Australia",
  IN: "India", TR: "Turkey", UA: "Ukraine", RU: "Russia", KZ: "Kazakhstan",
  AE: "United Arab Emirates", BR: "Brazil", MX: "Mexico", IL: "Israel", LV: "Latvia",
};
export function extractRegionTokens(region) { return String(region || "").toLowerCase().split(/[^a-zA-Z]+/).filter(Boolean); }
export function countryCodeFromRegion(region) {
  if (region == null) return null;
  const regionClean = String(region).trim().toLowerCase();
  if (!regionClean) return null;
  const tokens = extractRegionTokens(regionClean);
  for (const token of tokens) { const mapped = REGION_TO_COUNTRY_CODE[token]; if (mapped) return mapped; }
  for (const token of tokens) { if (token.length === 2 && /^[a-z]+$/i.test(token)) return token.toUpperCase(); }
  return null;
}
export function flagEmojiFromCountryCode(countryCode) {
  if (!countryCode) return UNKNOWN_FLAG;
  const code = String(countryCode).trim().toUpperCase();
  if (code.length !== 2 || !/^[A-Z]+$/.test(code)) return UNKNOWN_FLAG;
  const base = "A".charCodeAt(0);
  return String.fromCodePoint(0x1f1e6 + code.charCodeAt(0) - base, 0x1f1e6 + code.charCodeAt(1) - base);
}
export function nodeGeo(region) {
  const code = countryCodeFromRegion(region);
  const country = code ? (COUNTRY_CODE_TO_NAME[code] || code) : "Unknown";
  const flag = flagEmojiFromCountryCode(code);
  const regionText = String(region || "unknown");
  const short = `${flag} ${country}`;
  return { code, country, flag, short, regionText, full: `${short} \u00B7 ${regionText}` };
}

/* Zones */
export const ZONE_VALUES = ["europe", "asia", "americas", "oceania", "africa", "unknown"];
export const ZONE_LABELS = {
  europe: "Europe",
  asia: "Asia",
  americas: "Americas",
  oceania: "Oceania",
  africa: "Africa",
  unknown: "Unknown",
};
export const COUNTRY_CODE_TO_ZONE = {
  FI: "europe", DE: "europe", NL: "europe", PL: "europe", GB: "europe",
  FR: "europe", ES: "europe", IT: "europe", SE: "europe", NO: "europe",
  DK: "europe", CH: "europe", AT: "europe", CZ: "europe", UA: "europe",
  RU: "europe", KZ: "europe", LV: "europe", TR: "europe",
  SG: "asia", JP: "asia", KR: "asia", HK: "asia", IN: "asia", AE: "asia", IL: "asia",
  US: "americas", CA: "americas", MX: "americas", BR: "americas",
  AU: "oceania",
};
export function inferZone(region) {
  const cc = countryCodeFromRegion(region);
  if (!cc) return null;
  return COUNTRY_CODE_TO_ZONE[cc] || null;
}
export function effectiveZone(node) {
  const explicit = String(node && node.zone || "").trim().toLowerCase();
  if (explicit && ZONE_VALUES.includes(explicit)) return explicit;
  return inferZone(node && node.region) || "unknown";
}

export function zoneSelectOptions(stateZones, currentCode) {
  const active = Array.isArray(stateZones) ? stateZones.filter((z) => z.is_active) : [];
  if (active.length === 0) {
    return ZONE_VALUES.filter((z) => z !== "unknown").map((z) => ({
      code: z, name: ZONE_LABELS[z] || z, emoji: "",
    }));
  }
  const sorted = active.slice().sort((a, b) => {
    if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
    return a.code.localeCompare(b.code);
  });
  if (currentCode && !sorted.some((z) => z.code === currentCode)) {
    sorted.unshift({ code: currentCode, name: currentCode, emoji: "", is_active: false });
  }
  return sorted;
}

/* Plan-specific */
export const resetLabels = { NO_RESET: "Без сброса", DAY: "Ежедневно", WEEK: "Еженедельно", MONTH: "Ежемесячно" };
export const resetColors = { NO_RESET: "muted", DAY: "warn", WEEK: "info", MONTH: "ok" };
