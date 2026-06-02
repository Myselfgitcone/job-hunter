import type { Job, Settings, TailorResult, ProfileData, QualifyResult } from "./types";

// In dev: VITE_API_URL is empty → Vite proxy forwards /api → localhost:8000
// In prod: VITE_API_URL = https://your-backend.up.railway.app
const BASE = (import.meta.env.VITE_API_URL || "") + "/api";

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json() as Promise<T>;
}

export const api = {
  getJobs: (params?: { status?: string; remote?: boolean; country?: string; source?: string; time_range?: string }) => {
    const q = new URLSearchParams();
    if (params?.status)               q.set("status",      params.status);
    if (params?.remote !== undefined)  q.set("remote",      String(params.remote));
    if (params?.country)              q.set("country",     params.country);
    if (params?.source)               q.set("source",      params.source);
    if (params?.time_range)           q.set("time_range",  params.time_range);
    return req<Job[]>(`/jobs?${q}`);
  },

  getJob: (id: string) => req<Job>(`/jobs/${id}`),

  scrape: () => req<{ new_jobs: number; total_scraped: number; deleted_old: number; scraped_at: string }>(
    `/jobs/scrape`, { method: "POST" }
  ),

  setStatus: (id: string, status: string) =>
    req(`/jobs/${id}/status`, { method: "PUT", body: JSON.stringify({ status }) }),

  fetchJd: (id: string) => req<{ description: string }>(`/jobs/${id}/fetch-jd`, { method: "POST" }),

  saveDescription: (id: string, description: string) =>
    req(`/jobs/${id}/description`, { method: "PUT", body: JSON.stringify({ description }) }),

  tailor: (id: string) => req<TailorResult>(`/jobs/${id}/tailor`, { method: "POST" }),

  generateCoverLetter: (id: string) =>
    req<{ cover_letter: string }>(`/jobs/${id}/cover-letter`, { method: "POST" }),

  saveNotes: (id: string, notes: string) =>
    req(`/jobs/${id}/notes`, { method: "PUT", body: JSON.stringify({ notes }) }),

  pdfUrl: (id: string) => `${BASE}/jobs/${id}/resume/pdf`,
  docxUrl: (id: string) => `${BASE}/jobs/${id}/resume/docx`,

  clearAllJobs: () => req<{ deleted: number }>("/jobs/all", { method: "DELETE" }),

  quickTailor: (jd: string, company: string) =>
    req<{ tailored_resume: string }>("/quick-tailor", { method: "POST", body: JSON.stringify({ jd, company }) }),

  quickTailorPdfUrl: () => `${BASE}/quick-tailor/pdf`,
  quickTailorDocxUrl: () => `${BASE}/quick-tailor/docx`,

  savePackage: (job_id: string) =>
    req<{ folder: string; company: string }>(`/jobs/${job_id}/save-package`, { method: "POST" }),

  quickSavePackage: (company: string, jd: string, tailored_resume: string) =>
    req<{ folder: string; company: string }>("/quick-tailor/save-package", {
      method: "POST",
      body: JSON.stringify({ company, jd, tailored_resume }),
    }),

  verifyJob: (id: string) =>
    req<{ alive: boolean | null; status_code: number | null; error?: string }>(`/jobs/${id}/verify`),

  getAnalytics: () => req<any>("/analytics"),

  getSettings: () => req<Settings>("/settings"),

  saveSettings: (data: Partial<Settings>) =>
    req("/settings", { method: "PUT", body: JSON.stringify(data) }),

  updateJobMeta: (id: string, meta: { deadline?: string; interview_date?: string; priority?: number }) =>
    req(`/jobs/${id}/meta`, { method: "PATCH", body: JSON.stringify(meta) }),

  search: (params: {
    q?: string; status?: string; remote?: boolean; country?: string; source?: string;
    min_ats?: number; has_deadline?: boolean; priority?: number;
    sort?: string; order?: string; page?: number; limit?: number;
  }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== "") q.set(k, String(v)); });
    return req<{ data: Job[]; total: number; page: number; pages: number }>(`/search?${q}`);
  },

  getReminders: () => req<(Job & { days_until_deadline: number | null; days_until_interview: number | null })[]>("/reminders"),

  getSchedulerStatus: () => req<{ running: boolean; jobs: { id: string; next_run: string }[] }>("/scheduler/status"),

  updateSchedulerCron: (cron: string) =>
    req("/scheduler/cron", { method: "PUT", body: JSON.stringify({ cron }) }),

  runScraperNow: () =>
    req("/scheduler/run-now", { method: "POST" }),

  cleanDescriptions: () =>
    req<{ cleaned: number }>("/jobs/clean-descriptions", { method: "POST" }),

  getProfile: () => req<ProfileData>("/profile"),
  saveProfile: (data: ProfileData) =>
    req("/profile", { method: "PUT", body: JSON.stringify(data) }),

  parseResume: async (file: File): Promise<ProfileData> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/profile/parse-resume`, { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Failed to parse resume");
    }
    return res.json();
  },

  qualifyJob: (id: string) => req<QualifyResult>(`/jobs/${id}/qualify`, { method: "POST" }),
  qualifyAll: () => req("/jobs/qualify-all", { method: "POST" }),
};
