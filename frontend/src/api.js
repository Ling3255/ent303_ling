// 前端只和后端通信；所有处理都在后端完成。
import { getLang, pickText } from "./i18n.jsx";

const BASE = import.meta.env.VITE_API_BASE || "";

const TOKEN_KEY = "citecheck_token";
export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY)),
};

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}) {
  const token = tokenStore.get();
  const headers = { ...(options.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  let body = null;
  try {
    body = await res.json();
  } catch {
    /* 非 JSON 响应 */
  }
  if (!res.ok) {
    const detail = body?.detail;
    // 后端的提示是 {zh, en}；校验错误是数组
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg).join("; ")
      : (detail && pickText(getLang(), detail)) ||
        (getLang() === "zh" ? `请求失败（${res.status}）` : `Request failed (${res.status})`);
    throw new ApiError(message, res.status);
  }
  return body;
}

const json = (method, data) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export const api = {
  health: () => request("/api/health"),
  requestCode: (email) => request("/api/auth/request-code", json("POST", { email, lang: getLang() })),
  verify: (email, code) => request("/api/auth/verify", json("POST", { email, code })),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  me: () => request("/api/me"),
  myChecks: () => request("/api/me/checks"),
  split: (text) => request("/api/split", json("POST", { text })),
  addIdentifier: (identifier) => request("/api/papers/identifier", json("POST", { identifier })),
  upload: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/api/papers/upload", { method: "POST", body: form });
  },
  paper: (id) => request(`/api/papers/${id}`),
  pdfUrl: (id) => `${BASE}/api/papers/${id}/pdf`,
  createCheck: (payload) => request("/api/checks", json("POST", payload)),
  check: (id) => request(`/api/checks/${id}`),
  feedback: (id, payload) => request(`/api/checks/${id}/feedback`, json("POST", payload)),
};
