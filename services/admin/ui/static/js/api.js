import { state, refs, $ } from './state.js';
import { esc } from './utils.js';

let sessionAuth = false;
let csrfToken = null;

// Late-binding for notify/pushLog to avoid circular imports with ui.js
let _notify = () => {};
let _pushLog = () => {};

export function setNotify(fn) { _notify = fn; }
export function setPushLog(fn) { _pushLog = fn; }

export function isAuthenticated() { return sessionAuth; }

// Fetch interceptor for global loading bar
let fetchCount = 0;
const loadingBar = document.getElementById("global-loading-bar");
const originalFetch = window.fetch;
window.fetch = function(...args) {
  fetchCount++;
  if (loadingBar) loadingBar.classList.add("active");
  return originalFetch.apply(this, args).finally(() => {
    fetchCount--;
    if (fetchCount === 0 && loadingBar) loadingBar.classList.remove("active");
  });
};

export async function req(path, options) {
  const opt = options || {};
  const headers = { Accept: "application/json" };
  if (opt.body != null) headers["Content-Type"] = "application/json";
  if (csrfToken && opt.method && opt.method !== "GET") headers["x-csrf-token"] = csrfToken;
  const fetchOpts = { method: opt.method || "GET", headers, body: opt.body != null ? JSON.stringify(opt.body) : undefined, credentials: "same-origin" };
  const r = await fetch(path, fetchOpts);
  if (r.status === 401 && sessionAuth) { sessionAuth = false; window.location.href = "/api/v1/auth/admin/login"; throw new Error("Session expired"); }
  if (!r.ok) {
    const raw = await r.text();
    let detail = raw;
    try { const parsed = JSON.parse(raw); if (parsed && parsed.detail) detail = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail); } catch (_) {}
    throw new Error(`${r.status} ${detail}`);
  }
  return r.status === 204 ? null : await r.json();
}

export async function runAction(title, fn) {
  if (!sessionAuth) { window.location.href = "/api/v1/auth/admin/login"; return null; }
  try { const out = await fn(); _pushLog(title, out, false); _notify(`${title}: выполнено`, false); return out; }
  catch (e) { _pushLog(title, e.message, true); _notify(`${title}: ${e.message}`, true); throw e; }
}

export async function copyToClipboard(value) {
  const text = String(value || "").trim();
  if (!text) return;
  try { await navigator.clipboard.writeText(text); _notify("Скопировано в буфер обмена", false); }
  catch (_) { _notify("Не удалось скопировать", true); }
}

export async function checkSession() {
  try {
    const res = await fetch("/api/v1/auth/admin/session", { credentials: "same-origin" });
    if (!res.ok) return false;
    const data = await res.json();
    if (data.authenticated) {
      sessionAuth = true; csrfToken = data.csrf_token || null;
      refs.sessionUserInfo.style.display = ""; refs.sessionUsername.textContent = data.username; refs.sessionRole.textContent = data.role;
      return true;
    }
  } catch (_) {}
  return false;
}

export function setupLogout() {
  if (refs.btnLogout) {
    refs.btnLogout.addEventListener("click", async () => {
      try { await fetch("/api/v1/auth/admin/logout", { method: "POST", credentials: "same-origin" }); } catch (_) {}
      sessionAuth = false; csrfToken = null; window.location.href = "/api/v1/auth/admin/login";
    });
  }
}
