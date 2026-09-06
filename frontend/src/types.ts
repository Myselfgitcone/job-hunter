export type JobStatus =
  | "new" | "applied" | "screening" | "assessment" | "interview" | "final" | "skipped";

// Single source of truth for statuses — order = pipeline order, used by the
// status dropdown, Kanban columns, and job-card pills. "interview" = interview
// rounds; screening/assessment/final are the surrounding interview stages.
export const JOB_STATUSES: { id: JobStatus; label: string; color: string }[] = [
  { id: "new",        label: "New",              color: "#3b82f6" },
  { id: "applied",    label: "Applied",          color: "#10b981" },
  { id: "screening",  label: "Screening",        color: "#0ea5e9" },
  { id: "assessment", label: "Assessment",       color: "#a855f7" },
  { id: "interview",  label: "Interview Rounds", color: "#f59e0b" },
  { id: "final",      label: "Final Interview",  color: "#ec4899" },
  { id: "skipped",    label: "Skipped",          color: "#5b6377" },
];
export const STATUS_LABELS: Record<string, string> = Object.fromEntries(JOB_STATUSES.map(s => [s.id, s.label]));
export const STATUS_COLORS: Record<string, string> = Object.fromEntries(JOB_STATUSES.map(s => [s.id, s.color]));
// Statuses that mean "this job has been applied to" (for applied-count logic).
export const APPLIED_STAGES: JobStatus[] = ["applied", "screening", "assessment", "interview", "final"];

export interface ProfileExperience {
  role: string;
  company: string;
  start_date: string;
  end_date: string;
  years: number;
  bullets: string[];
}
export interface ProfileEducation { degree: string; school: string; year: string; }
export interface ProfileProject { name: string; description: string; }
export interface ProfileData {
  name: string;
  email: string;
  phone: string;
  location: string;
  address: string;
  linkedin: string;
  github: string;
  website: string;
  visa_status: string;
  summary: string;
  experience: ProfileExperience[];
  education: ProfileEducation[];
  projects: ProfileProject[];
  skills: string[];
  certifications: string[];
}

export interface QualifyCriterion { pass: boolean; note: string; }
export interface QualifyResult {
  qualified: boolean;
  score: number;
  summary: string;
  criteria: {
    job_category?: QualifyCriterion;
    experience?: QualifyCriterion;
    skills_match?: QualifyCriterion;
    sponsorship?: QualifyCriterion;
    location?: QualifyCriterion;
    seniority?: QualifyCriterion;
  };
}

export interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  country: string;
  url: string;
  source: string;
  description: string;
  salary: string;
  remote: boolean;
  posted_at: string;
  scraped_at: string;
  indexed_at?: string;   // FantasticJobs index time — per-job freshness
  hc_original_date: string;  // HC's raw estimated_publish_date (only for HiringCafe jobs)
  status: JobStatus;
  tailored_resume: string | null;
  tailored_at: string;
  applied_at: string;
  ats_score_before: number | null;
  ats_score_after: number | null;
  ats_keywords_matched: string[];
  ats_keywords_missing: string[];
  fit_analysis: string | null;
  interview_tips: string[];
  cover_letter: string;
  notes: string;
  deadline: string;
  interview_date: string;
  priority: number;
  role_priority?: number;   // 1 = most-competitive role family (P1), 0 = unranked
  deferred?: boolean;       // soft "move to bottom of the day" (not a skip)
  qualify_result: QualifyResult | null;
  // Review gate: true = pipeline flagged issues, read before applying.
  // review_reasons = blocking only (shown in UI). review_notes = advisory/
  // cosmetic (JD echo, clone, metric density) — never blocking, not shown.
  needs_review?: boolean;
  review_reasons?: string[];
  review_notes?: string[];
  // Three-gate LLM score from the last tailoring run. null if scoring failed.
  gate_scores?: GateScores | null;
  tailor_context?: TailorContext | null;
  // Client-side only — how long the last tailor run took, in seconds.
  // Not persisted server-side; survives refreshJob() because that merge
  // only overwrites keys present in the server response.
  generation_seconds?: number;
  // Client-side only — readability signal from the last tailor run
  // (score_ats quality field). Same persistence model as generation_seconds.
  ats_quality?: AtsQuality;
  // FJ enrichment
  visa_sponsorship: boolean | null;
  experience_level: string;
  experience_level_inferred: boolean;
  employment_type: string;
  benefits: string[];
  job_expiry: string;
  logo_url: string;
  company_size: string;
  company_industry: string;
  company_hq: string;
  company_funding: number | null;
  ai_keywords: string[];
}

export interface Settings {
  resume: string;
  ai_provider: string;
  ai_api_key: string;
  ai_model: string;
  adzuna_app_id: string;
  adzuna_app_key: string;
  jobo_api_key: string;
}

export interface UserSettings {
  resume: string;
  job_roles: string[];
  active_job_roles?: string[];
  countries: string[];
  visa_filter: boolean;
  level_filter: boolean;
  apply_dry_run?: boolean;
  ai_provider: string;
  ai_api_key: string;
  ai_model: string;
  profile_name: string;
  profile_visa: string;
  auto_scrape_cron?: string;
  last_scraped_at?: string;
}

export interface Company {
  id: string;
  name: string;
  ats: string;
  slug: string;
  careers_url: string;
  active: boolean;
  source: string;
}

export interface AtsQuality { fragments: string[]; count: number }

/** One gate of the three-gate resume score. */
export interface GateScore { score: number; note: string }

/** Three-gate LLM score returned by the tailoring pipeline's final pass. */
export interface GateScores {
  ats?: GateScore;
  recruiter?: GateScore;
  hiring_manager?: GateScore;
  overall?: number;
  top_fixes?: string[];
  /** 100-point breakdown: tools 40, duties 15, title 5, orphans 10, numbers 10, readability 10, page_fit 10. */
  points?: Record<string, number>;
  /** 90% coverage target: how many ranked JD tools earned a bullet, and which are Skills-only by design. */
  coverage_target?: { need: number; have: number; met: boolean; skipped_by_design?: string[] };
  present?: string[];
  missing?: string[];
}

/** What the analyze pass detected about the JD, surfaced for transparency. */
export interface TailorContext {
  target_cloud?: string;
  company?: string;
  job_title?: string;
  industry?: string;
  role_domain?: string;
  target_tools?: string[];
  present?: string[];
  missing?: string[];
}

export interface TailorResult {
  ats_before: { score: number; matched: string[]; missing: string[]; total: number; quality?: AtsQuality };
  ats_after: { score: number; matched: string[]; missing: string[]; total: number; quality?: AtsQuality };
  tailored_resume: string;
  fit_analysis: string;
  interview_tips: string[];
  needs_review?: boolean;
  review_reasons?: string[];
  review_notes?: string[];
  gate_scores?: GateScores | null;
  tailor_context?: TailorContext | null;
}
