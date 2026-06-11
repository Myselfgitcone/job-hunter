export type JobStatus = "new" | "applied" | "skipped" | "interview";

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
  qualify_result: QualifyResult | null;
  // FJ enrichment
  visa_sponsorship: boolean | null;
  experience_level: string;
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
  countries: string[];
  visa_filter: boolean;
  level_filter: boolean;
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

export interface TailorResult {
  ats_before: { score: number; matched: string[]; missing: string[]; total: number };
  ats_after: { score: number; matched: string[]; missing: string[]; total: number };
  tailored_resume: string;
  fit_analysis: string;
  interview_tips: string[];
}
