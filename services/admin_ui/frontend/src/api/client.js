const BASE = "/api/v1";

async function request(path, { method = "GET", body, headers } = {}) {
  const res = await fetch(BASE + path, {
    method,
    credentials: "include",
    headers: {
      "content-type": "application/json",
      ...(headers || {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    window.location.href = "/api/v1/auth/admin/login";
    throw new Error("unauthenticated");
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
