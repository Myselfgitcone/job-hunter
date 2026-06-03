import type { Job, Settings, TailorResult, ProfileData, QualifyResult, Company } from "./types";

// In dev: VITE_API_URL is empty → Vite proxy forwards /api → localhost:8000
// In prod: VITE_API_URL = https://your-backend.up.railway.app
const BASE = (import.meta.env.VITE_API_URL || "");

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
  },

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

  scrape: () => req<{ new_jobs: number; total_scraped: number; deleted_old: number; scraped_at: string }>(
    `/api/jobs/scrape`, { method: "POST" }
  ),

  setStatus: (id: string, status: string) =>
    req(`/api/jobs/${id}/status`, { method: "PUT", body: JSON.stringify({ status }) }),

  fetchJd: (id: string) => req<{ description: string }>(`/api/jobs/${id}/fetch-jd`, { method: "POST" }),

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

  getProfile: () => req<ProfileData>("/api/profile"),
  saveProfile: (data: ProfileData) =>
    req("/api/profile", { method: "PUT", body: JSON.stringify(data) }),

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
};
