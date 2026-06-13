import type { Job, Settings, TailorResult, ProfileData, QualifyResult, Company } from "./types";

// Railway backend URL — always used in production
const RAILWAY = "https://job-hunter-production-927d.up.railway.app";
// In dev (npm run dev): Vite proxy handles /api/* → localhost:8000, so BASE=""
// In prod (Vercel build): always point to Railway
const BASE: string = (import.meta.env.MODE === "development")
  ? (import.meta.env.VITE_API_URL || "")
  : (import.meta.env.VITE_API_URL || RAILWAY);


async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem("jh_token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { "Authorization": `Bearer ${token}` } : {}),
  };

  const res = await fetch(`${BASE}${path}`, {
    headers,
    ...options,
    // Merge headers properly if options also has headers
    ...(options?.headers ? { headers: { ...headers, ...(options.headers as Record<string, string>) } } : {}),
  });

  // 401 on auth endpoints = wrong password — show the error, don't logout
  const isAuthEndpoint = path.startsWith("/api/auth/");

  if (res.status === 401 && !isAuthEndpoint) {
    localStorage.removeItem("jh_token");
    localStorage.removeItem("jh_user");
    window.location.reload();
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json() as Promise<T>;
}

// Authenticated file download — fetch with Bearer token, save blob via anchor.
// Plain <a href> can't send Authorization headers → backend returns 401.
export async function downloadFile(url: string, fallbackName: string): Promise<void> {
  const token = localStorage.getItem("jh_token");
  const res = await fetch(url, {
    headers: token ? { "Authorization": `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Download failed");
  }
  // Prefer filename from Content-Disposition
  const cd = res.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  const filename = m ? decodeURIComponent(m[1]) : fallbackName;
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

let _profileCache: ProfileData | null = null;

export const api = {
  // ── Auth ──────────────────────────────────────────────────────────────────
  auth: {
    register: (email: string, password: string, name: string) =>
      req<{ token: string; user: { id: string; email: string; name: string } }>("/api/auth/register", {
        method: "POST", body: JSON.stringify({ email, password, name })
      }),
    login: (email: string, password: string) =>
      req<{ token: string; user: { id: string; email: string; name: string } }>("/api/auth/login", {
        method: "POST", body: JSON.stringify({ email, password })
      }),
    me: () => req<{ id: string; email: string; name: string }>("/api/auth/me"),
    changePassword: (current_password: string, new_password: string) =>
      req<{ ok: boolean; message: string }>("/api/auth/change-password", {
        method: "POST", body: JSON.stringify({ current_password, new_password })
      }),
    forgotPassword: (email: string) =>
      req<{ ok: boolean; message: string }>("/api/auth/forgot-password", {
        method: "POST", body: JSON.stringify({ email })
      }),
    resetPassword: (token: string, new_password: string) =>
      req<{ ok: boolean; message: string; email: string }>("/api/auth/reset-password", {
        method: "POST", body: JSON.stringify({ token, new_password })
      }),
  },

  deleteAccount: () => req<{ message: string }>("/api/account", { method: "DELETE" }),

  // ── Companies ────────────────────────────────────────────────────────────
  companies: {
    list: () => req<Company[]>("/api/companies"),
    detect: (url: string) => req<{ ats: string; slug: string; name: string }>("/api/companies/detect", {
      method: "POST", body: JSON.stringify({ url })
    }),
    add: (data: { name: string; ats: string; slug: string; careers_url?: string }) =>
      req<Company>("/api/companies", { method: "POST", body: JSON.stringify(data) }),
    remove: (id: string) => req<{ ok: boolean }>(`/api/companies/${id}`, { method: "DELETE" }),
    toggle: (id: string) => req<{ id: string; active: boolean }>(`/api/companies/${id}/toggle`, { method: "PUT" }),
  },

  // ── Jobs ─────────────────────────────────────────────────────────────────
  getJobs: (params?: { status?: string; remote?: boolean; country?: string; source?: string; time_range?: string }) => {
    const q = new URLSearchParams();
    if (params?.status)               q.set("status",      params.status);
    if (params?.remote !== undefined)  q.set("remote",      String(params.remote));
    if (params?.country)              q.set("country",     params.country);
    if (params?.source)               q.set("source",      params.source);
    if (params?.time_range)           q.set("time_range",  params.time_range);
    return req<Job[]>(`/api/jobs?${q}`);
  },

  getJob: (id: string) => req<Job>(`/api/jobs/${id}`),

  scrape: () => req<{ message: string }>(
    `/api/jobs/scrape`, { method: "POST" }
  ),

  setStatus: (id: string, status: string) =>
    req(`/api/jobs/${id}/status`, { method: "PUT", body: JSON.stringify({ status }) }),

  fetchJd: (id: string) => req<{ description: string; date?: string }>(`/api/jobs/${id}/fetch-jd`, { method: "POST" }),

  saveDescription: (id: string, description: string) =>
    req(`/api/jobs/${id}/description`, { method: "PUT", body: JSON.stringify({ description }) }),

  tailor: (id: string) => req<TailorResult>(`/api/jobs/${id}/tailor`, { method: "POST" }),

  generateCoverLetter: (id: string) =>
    req<{ cover_letter: string }>(`/api/jobs/${id}/cover-letter`, { method: "POST" }),

  saveNotes: (id: string, notes: string) =>
    req(`/api/jobs/${id}/notes`, { method: "PUT", body: JSON.stringify({ notes }) }),

  pdfUrl: (id: string) => `${BASE}/api/jobs/${id}/resume/pdf`,
  docxUrl: (id: string) => `${BASE}/api/jobs/${id}/resume/docx`,

  clearAllJobs: () => req<{ deleted: number }>("/api/jobs/all", { method: "DELETE" }),

  revealTelegramToken: () => req<{ token: string }>("/api/settings/telegram-token"),

  // ── Admin: user approval ───────────────────────────────────────────────────
  adminUsers: () =>
    req<Array<{ id: string; email: string; name: string; status: string; is_admin: boolean; job_roles: string[]; created_at: string; last_seen_at: string }>>("/api/admin/users"),
  adminUpdateUser: (id: string, body: { status?: string; job_roles?: string[] }) =>
    req<{ ok: boolean }>(`/api/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  adminPendingCount: () => req<{ count: number }>("/api/admin/pending-count"),
  adminDeleteUser: (id: string) => req<{ ok: boolean }>(`/api/admin/users/${id}`, { method: "DELETE" }),

  qualifyHealth: () =>
    req<{ admin_settings_found: boolean; api_key_set: boolean; profile_set: boolean; qualify_model: string | null; scored_jobs: number; pending_jobs: number; running: boolean }>("/api/qualify/health"),

  fixDescriptions: () => req<{ message: string }>("/api/jobs/fix-descriptions", { method: "POST" }),
  fixDescriptionsStatus: () =>
    req<{ running: boolean; total: number; done: number; fixed: number; failed: number }>("/api/jobs/fix-descriptions/status"),

  quickTailor: (jd: string, company: string) =>
    req<{ tailored_resume: string }>("/api/quick-tailor", { method: "POST", body: JSON.stringify({ jd, company }) }),

  quickTailorPdfUrl: () => `${BASE}/api/quick-tailor/pdf`,
  quickTailorDocxUrl: () => `${BASE}/api/quick-tailor/docx`,

  savePackageUrl: (job_id: string) => `${BASE}/api/jobs/${job_id}/save-package`,

  quickSavePackage: (company: string, jd: string, tailored_resume: string) =>
    req<{ folder: string; company: string }>("/api/quick-tailor/save-package", {
      method: "POST",
      body: JSON.stringify({ company, jd, tailored_resume }),
    }),

  verifyJob: (id: string) =>
    req<{ alive: boolean | null; status_code: number | null; error?: string }>(`/api/jobs/${id}/verify`),

  getAnalytics: () => req<any>("/api/analytics"),

  getSettings: () => req<Settings>("/api/settings"),

  saveSettings: (data: Partial<Settings>) =>
    req("/api/settings", { method: "PUT", body: JSON.stringify(data) }),

  updateSettings: (data: any) =>
    req("/api/settings", { method: "PUT", body: JSON.stringify(data) }),

  updateJobMeta: (id: string, meta: { deadline?: string; interview_date?: string; priority?: number }) =>
    req(`/api/jobs/${id}/meta`, { method: "PATCH", body: JSON.stringify(meta) }),

  search: (params: {
    q?: string; status?: string; remote?: boolean; country?: string; source?: string;
    min_ats?: number; has_deadline?: boolean; priority?: number;
    sort?: string; order?: string; page?: number; limit?: number;
  }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== "") q.set(k, String(v)); });
    return req<{ data: Job[]; total: number; page: number; pages: number }>(`/api/search?${q}`);
  },

  getReminders: () => req<(Job & { days_until_deadline: number | null; days_until_interview: number | null })[]>("/api/reminders"),

  getSchedulerStatus: () => req<{ running: boolean; jobs: { id: string; next_run: string }[] }>("/api/scheduler/status"),

  updateSchedulerCron: (cron: string) =>
    req("/api/scheduler/cron", { method: "PUT", body: JSON.stringify({ cron }) }),

  runScraperNow: () =>
    req("/api/scheduler/run-now", { method: "POST" }),

  cleanDescriptions: () =>
    req<{ cleaned: number }>("/api/jobs/clean-descriptions", { method: "POST" }),

  getProfile: async () => {
    if (_profileCache) return _profileCache;
    const data = await req<ProfileData>("/api/profile");
    _profileCache = data;
    return data;
  },
  saveProfile: async (data: ProfileData) => {
    _profileCache = data;
    return req("/api/profile", { method: "PUT", body: JSON.stringify(data) });
  },

  parseResume: async (file: File): Promise<ProfileData> => {
    const token = localStorage.getItem("jh_token");
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/api/profile/parse-resume`, {
      method: "POST",
      body: form,
      headers: token ? { "Authorization": `Bearer ${token}` } : {},
    });
    if (res.status === 401) {
      localStorage.removeItem("jh_token");
      localStorage.removeItem("jh_user");
      window.location.reload();
      throw new Error("Unauthorized");
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Failed to parse resume");
    }
    return res.json();
  },

  qualifyJob: (id: string) => req<QualifyResult>(`/api/jobs/${id}/qualify`, { method: "POST" }),
  qualifyAll: () => req("/api/jobs/qualify-all", { method: "POST" }),

  testTelegram: (token: string, chat_id: string) =>
    req<{ ok: boolean; message: string }>("/api/telegram/test", {
      method: "POST",
      body: JSON.stringify({ token, chat_id }),
    }),
};
