/**
 * Experience level filter for 6-year Data Engineer.
 * Blocks: Principal, Staff, Manager, Director, VP, Head of, Fellow, Distinguished.
 * Keeps: Data Engineer, Senior, Lead, AI/ML Engineer, Analytics Engineer, etc.
 */

const OVERQUALIFIED_PATTERNS: RegExp[] = [
  /\bprincipal\b/i,
  /\bstaff\s+(data|software|ml|ai|analytics)\s+engineer/i,
  /\bstaff\s+engineer\b/i,
  /\bmanager\b/i,
  /\bdirector\b/i,
  /\bvp\b|\bvice\s+president\b/i,
  /\bhead\s+of\b/i,
  /\bfellow\b/i,
  /\bdistinguished\b/i,
  /\bchief\b/i,           // Chief Data Officer, etc.
  /\barchitect\b/i,       // Data Architect (typically 10+ years)
];

export function isLevelMatch(title: string): boolean {
  return !OVERQUALIFIED_PATTERNS.some(p => p.test(title));
}
