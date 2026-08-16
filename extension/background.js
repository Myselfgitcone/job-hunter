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

// Per-tab map of frameIds that contain an application form, so the top frame
// can host the button and relay "fill" to whichever frame holds the form.
const formFrames = new Map(); // tabId -> Set(frameId)

// Tabs armed for one-shot auto-fill (opened via the app's "Fill & Apply").
// Keyed by tabId so it survives navigations within the tab (posting → form
// page), where the #jh=1 hash would otherwise be lost.
const armedTabs = new Map(); // tabId -> timestamp
const ARM_TTL = 10 * 60 * 1000;

const handlers = {
  // A content frame reports it has a form (or no longer does).
  registerForm({ has }, sender) {
    const tabId = sender?.tab?.id;
    const frameId = sender?.frameId ?? 0;
    if (tabId == null) return { ok: false };
    let set = formFrames.get(tabId);
    if (!set) { set = new Set(); formFrames.set(tabId, set); }
    if (has) set.add(frameId); else set.delete(frameId);
    // Tell the top frame to show/hide the button.
    chrome.tabs.sendMessage(tabId, { type: "showButton", show: set.size > 0 }, { frameId: 0 })
      .catch(() => {});
    return { ok: true };
  },
  armTab(p, sender) {
    if (sender?.tab?.id != null) armedTabs.set(sender.tab.id, { ts: Date.now(), jobId: p?.jobId || "" });
    return { ok: true };
  },
  isArmed(_p, sender) {
    const e = armedTabs.get(sender?.tab?.id);
    const armed = !!(e && Date.now() - e.ts < ARM_TTL);
    return { armed, jobId: armed ? (e.jobId || "") : "" };
  },
  disarmTab(_p, sender) {
    armedTabs.delete(sender?.tab?.id);
    return { ok: true };
  },
  // Top frame's button was clicked → relay a fill to the first form frame.
  async relayFill(_p, sender) {
    const tabId = sender?.tab?.id;
    const set = formFrames.get(tabId);
    const frameId = set && set.size ? [...set][0] : 0;
    try {
      return await chrome.tabs.sendMessage(tabId, { type: "fillPage" }, { frameId });
    } catch (e) {
      return { error: "Could not reach the form frame — reload the page and retry." };
    }
  },
  async login({ email, password }) {
    const r = await api("/api/auth/login", { method: "POST", body: { email, password } });
    await chrome.storage.local.set({ jh_token: r.token, jh_user: r.user });
    return { user: r.user };
  },
  // Auto-pair: the app-bridge content script on thejobhunter.app hands us the
  // web app's own auth token, so Google (OAuth) users — who have no password —
  // are signed into the extension just by being logged into the web app.
  async syncAuth({ token, user }) {
    const { jh_token: cur } = await chrome.storage.local.get("jh_token");
    if (token) {
      if (token !== cur) await chrome.storage.local.set({ jh_token: token, jh_user: user || null });
    } else if (cur) {
      await chrome.storage.local.remove(["jh_token", "jh_user"]);   // app logged out → extension too
    }
    return { ok: true };
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
  learn(payload) {
    return api("/api/extension/learn", { method: "POST", body: payload });
  },
  resumeFile(payload) {
    return api("/api/extension/resume-file", { method: "POST", body: payload });
  },
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const fn = handlers[msg?.type];
  if (!fn) { sendResponse({ error: "unknown message" }); return false; }
  Promise.resolve(fn(msg.payload || {}, sender))
    .then((data) => sendResponse({ data }))
    .catch((e) => sendResponse({ error: e.message || String(e) }));
  return true; // async
});

chrome.tabs.onRemoved.addListener((tabId) => { formFrames.delete(tabId); armedTabs.delete(tabId); });
