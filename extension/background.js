// Job Hunter Autofill — background service worker.
// Owns the API base + auth token and proxies all backend calls so content
// scripts never touch cross-origin fetch or the token directly.

const API_BASE = "https://job-hunter-production-927d.up.railway.app";

async function getToken() {
  const { jh_token } = await chrome.storage.local.get("jh_token");
  return jh_token || "";
}

async function api(path, { method = "GET", body } = {}) {
  const token = await getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

const handlers = {
  async login({ email, password }) {
    const r = await api("/api/auth/login", { method: "POST", body: { email, password } });
    await chrome.storage.local.set({ jh_token: r.token, jh_user: r.user });
    return { user: r.user };
  },
  async logout() {
    await chrome.storage.local.remove(["jh_token", "jh_user"]);
    return { ok: true };
  },
  async me() {
    const { jh_user } = await chrome.storage.local.get("jh_user");
    if (!jh_user) return { user: null };
    try {
      const u = await api("/api/auth/me");
      return { user: u };
    } catch {
      await chrome.storage.local.remove(["jh_token", "jh_user"]);
      return { user: null };
    }
  },
  answer(payload) {
    return api("/api/extension/answer", { method: "POST", body: payload });
  },
};

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  const fn = handlers[msg?.type];
  if (!fn) { sendResponse({ error: "unknown message" }); return false; }
  Promise.resolve(fn(msg.payload || {}))
    .then((data) => sendResponse({ data }))
    .catch((e) => sendResponse({ error: e.message || String(e) }));
  return true; // async
});
