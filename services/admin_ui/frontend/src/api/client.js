const BASE = "/api/v1";

function getCookie(name) {
  const prefix = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const s = part.trim();
    if (s.startsWith(prefix)) return decodeURIComponent(s.slice(prefix.length));
  }
  return null;
}

async function request(path, { method = "GET", body, headers } = {}) {
  const extra = { ...(headers || {}) };
  if (method !== "GET" && method !== "HEAD") {
    const csrf = getCookie("admin_csrf");
    if (csrf) extra["x-csrf-token"] = csrf;
  }
  const res = await fetch(BASE + path, {
    method,
    credentials: "include",
    headers: {
      "content-type": "application/json",
      ...extra,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    const err = new Error("unauthenticated");
    err.status = 401;
    throw err;
  }
  const text = await res.text();
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch { payload = text; }
  if (!res.ok) {
    const detail = payload && payload.detail ? payload.detail : `HTTP ${res.status}`;
    const err = new Error(detail);
    err.status = res.status;
    err.payload = payload;
    throw err;
  }
  return payload;
}

export const api = {
  get: (p, opts) => request(p, { ...opts, method: "GET" }),
  post: (p, body, opts) => request(p, { ...opts, method: "POST", body }),
  patch: (p, body, opts) => request(p, { ...opts, method: "PATCH", body }),
  del: (p, opts) => request(p, { ...opts, method: "DELETE" }),
  raw: request,
};
