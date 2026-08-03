/**
 * Visa eligibility checker for F1/STEM OPT holders.
 * Scans job description for citizenship, green card, or no-sponsorship requirements.
 */

const DISQUALIFY_PATTERNS: { pattern: RegExp; reason: string }[] = [
  // Citizenship required
  { pattern: /\bus\s*citizen(ship)?\s*(only|required|must|preferred)?\b/i,            reason: "US Citizenship required" },
  { pattern: /\bu\.s\.?\s*citizen(ship)?\s*(only|required|must)?\b/i,                reason: "US Citizenship required" },
  { pattern: /must\s+be\s+a?\s*u\.?s\.?\s*citizen/i,                                 reason: "US Citizenship required" },
  { pattern: /citizenship\s*:?\s*u\.?s\.?\s*citizen/i,                               reason: "US Citizenship required" },
  { pattern: /united\s+states\s+citizen(ship)?/i,                                     reason: "US Citizenship required" },
  { pattern: /requires?\s+u\.?s\.?\s*citizenship/i,                                   reason: "US Citizenship required" },

  // Permanent resident / Green Card
  { pattern: /\bgreen\s*card\s*(holder|required|only)?\b/i,                          reason: "Green Card / PR required" },
  { pattern: /permanent\s+residen(t|ce)\s*(only|required|status)?\b/i,               reason: "Permanent Residency required" },
  { pattern: /\bpr\s+status\s+required\b/i,                                           reason: "Permanent Residency required" },

  // No sponsorship
  { pattern: /no\s+(visa\s+)?sponsorship/i,                                           reason: "No visa sponsorship offered" },
  { pattern: /unable\s+to\s+(provide|offer|sponsor)\s+(visa\s+)?sponsorship/i,       reason: "No visa sponsorship offered" },
  { pattern: /cannot\s+(provide|offer|sponsor)\s+(visa\s+)?sponsorship/i,            reason: "No visa sponsorship offered" },
  { pattern: /not\s+able\s+to\s+sponsor/i,                                            reason: "No visa sponsorship offered" },
  { pattern: /sponsorship\s+(is\s+)?(not\s+available|unavailable)/i,                 reason: "No visa sponsorship offered" },
  { pattern: /does\s+not\s+(provide|offer|sponsor)\s+(visa\s+)?sponsorship/i,        reason: "No visa sponsorship offered" },
  { pattern: /will\s+not\s+sponsor/i,                                                  reason: "No visa sponsorship offered" },
  { pattern: /visa\s+sponsorship\s+(is\s+)?not\s+(available|provided|offered)/i,    reason: "No visa sponsorship offered" },
  { pattern: /not\s+eligible\s+for\s+(?:immigration\s+|visa\s+|employment\s+)?sponsorship/i, reason: "No visa sponsorship offered" },
  { pattern: /(?:not|un)able\s+to\s+support\s+(?:immigration\s+|visa\s+)?sponsorship/i, reason: "No visa sponsorship offered" },
  { pattern: /do(?:es)?\s+not\s+support\s+(?:immigration\s+|visa\s+)?sponsorship/i,  reason: "No visa sponsorship offered" },

  // Security clearances (require US citizenship)
  { pattern: /\btop\s*secret\b/i,                                                     reason: "Top Secret clearance (requires citizenship)" },
  { pattern: /\bts\/sci\b/i,                                                          reason: "TS/SCI clearance (requires citizenship)" },
  { pattern: /\bpolygraph\b/i,                                                        reason: "Polygraph required (requires citizenship)" },
  { pattern: /security\s+clearance/i,                                                 reason: "Security clearance required (requires citizenship)" },
  { pattern: /\bclearance\s+required\b/i,                                             reason: "Clearance required (requires citizenship)" },
  { pattern: /with\s+(security\s+)?clearance/i,                                       reason: "Security clearance required (requires citizenship)" },
  { pattern: /active\s+(dod|security)\s+clearance/i,                                 reason: "Active clearance required (requires citizenship)" },
  { pattern: /must\s+hold\s+(an?\s+)?(active\s+)?(secret|top\s*secret)\s+clearance/i, reason: "Security clearance required (requires citizenship)" },
  { pattern: /\bsecret\s+clearance\b/i,                                               reason: "Secret clearance required (requires citizenship)" },
  { pattern: /\bdod\s+clearance\b/i,                                                  reason: "DoD clearance required (requires citizenship)" },

  // Public trust (US government — typically requires citizenship or LPR)
  { pattern: /position\s+of\s+public\s+trust/i,                                       reason: "Public Trust position (US government — citizenship/LPR typically required)" },
  { pattern: /\bpublic\s+trust\s+(clearance|required|eligibility)/i,                  reason: "Public Trust clearance (requires citizenship)" },
  { pattern: /hold\s+(a\s+)?public\s+trust/i,                                         reason: "Public Trust required (US government)" },
  { pattern: /obtain\s+(a\s+)?public\s+trust/i,                                       reason: "Public Trust required (US government)" },

  // Explicit work authorization restricting OPT
  { pattern: /\bauthorized\s+to\s+work\s+without\s+(any\s+)?sponsorship\b/i,        reason: "Must work without sponsorship" },
  { pattern: /must\s+be\s+eligible\s+to\s+work\s+in\s+the\s+u\.?s\.?\s+without\s+sponsorship/i, reason: "No sponsorship offered" },
  { pattern: /without\s+(?:requiring\s+)?(?:visa\s+)?sponsorship\s+(?:now|in\s+the\s+future|at\s+any)/i, reason: "No sponsorship (now or in future)" },

  // Explicit short-form refusals — "no H1B", "no OPT", "no GC", "no STEM OPT".
  // Lookaheads avoid false positives: "no green card REQUIRED" (visa-friendly),
  // "no OPT-out", "no OPTion" are NOT flagged.
  { pattern: /\bno\s+(?:h-?1b1?|h-?4|stem\s*opt|opt|cpt|ead|gc|green\s*cards?)\b(?!\s*[-–]\s*out)(?!\s+(?:required|needed|necessary|expected|mentioned))/i, reason: "No H1B / OPT / GC (explicit)" },
  { pattern: /\b(?:h-?1b1?|stem\s*opt|opt|cpt|f-?1)\s+(?:candidates?\s+|holders?\s+|visas?\s+)?(?:are\s+|is\s+)?not\s+(?:accepted|eligible|considered|allowed|available)\b/i, reason: "H1B / OPT not accepted" },
  { pattern: /(?:do(?:es)?\s*n[o']?t|will\s+not|cannot|can'?t|unable\s+to)\s+(?:accept|consider|hire|sponsor)\s+(?:h-?1b1?|opt|cpt|f-?1|visa|international)/i, reason: "H1B / OPT / visa not accepted" },

  // "GC or Citizen only" style combos — require a trailing only/required (or a
  // leading "must be") so inclusive lists ("Citizens, GC holders, and H1B") pass.
  { pattern: /\b(?:must\s+be\s+(?:a\s+)?)?(?:gc|green\s*cards?|permanent\s+residents?)\s*(?:holders?\s*)?(?:or|\/|,|&|and)\s*(?:us\s*)?citizens?\s*(?:only|required|to\s+apply)/i, reason: "GC or US Citizen only" },
  { pattern: /\b(?:must\s+be\s+(?:a\s+)?)?(?:us\s*)?citizens?\s*(?:or|\/|,|&|and)\s*(?:gc|green\s*cards?|permanent\s+residents?)\s*(?:holders?\s*)?(?:only|required|to\s+apply)/i, reason: "US Citizen or GC only" },
];

export interface VisaCheckResult {
  eligible: boolean;   // true = likely ok for F1 OPT
  reasons: string[];   // list of disqualifying reasons found
}

export function checkVisa(description: string): VisaCheckResult {
  if (!description || description.length < 20) {
    return { eligible: true, reasons: [] };
  }

  const found = new Set<string>();
  for (const { pattern, reason } of DISQUALIFY_PATTERNS) {
    if (pattern.test(description)) {
      found.add(reason);
    }
  }

  return {
    eligible: found.size === 0,
    reasons: [...found],
  };
}
