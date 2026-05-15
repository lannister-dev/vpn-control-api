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
  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
  const isBlob = typeof Blob !== "undefined" && body instanceof Blob;
  const isString = typeof body === "string";
  const rawBody = isFormData || isBlob || isString;
  const baseHeaders = rawBody ? {} : { "content-type": "application/json" };
  const res = await fetch(BASE + path, {
    method,
    credentials: "include",
    headers: { ...baseHeaders, ...extra },
    body: body == null ? undefined : (rawBody ? body : JSON.stringify(body)),
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

function uploadWithProgress(path, formData, { onProgress, signal, method = "POST" } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, BASE + path, true);
    xhr.withCredentials = true;
    const csrf = getCookie("admin_csrf");
    if (csrf) xhr.setRequestHeader("x-csrf-token", csrf);
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    });
    xhr.addEventListener("load", () => {
      const text = xhr.responseText || "";
      let payload = null;
      try { payload = text ? JSON.parse(text) : null; } catch { payload = text; }
      if (xhr.status >= 200 && xhr.status < 300) {
        if (onProgress) onProgress(1);
        resolve(payload);
      } else {
        const detail = payload && payload.detail ? payload.detail : `HTTP ${xhr.status}`;
        const err = new Error(detail);
        err.status = xhr.status;
        err.payload = payload;
        reject(err);
      }
    });
    xhr.addEventListener("error", () => reject(new Error("network error")));
    xhr.addEventListener("abort", () => {
      const err = new Error("aborted");
      err.name = "AbortError";
      reject(err);
    });
    if (signal) {
      if (signal.aborted) { xhr.abort(); return; }
      signal.addEventListener("abort", () => xhr.abort());
    }
    xhr.send(formData);
  });
}

export const api = {
  get: (p, opts) => request(p, { ...opts, method: "GET" }),
  post: (p, body, opts) => request(p, { ...opts, method: "POST", body }),
  patch: (p, body, opts) => request(p, { ...opts, method: "PATCH", body }),
  del: (p, opts) => request(p, { ...opts, method: "DELETE" }),
  raw: request,
  upload: uploadWithProgress,
};
