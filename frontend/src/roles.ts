// Shared role helpers.

// AI / Data-Science LEADERSHIP title match (Director/Head/VP/Chief/Principal of
// AI/DS/ML/Data Platform). Mirrors the matcher in App.tsx.
const _AIL_YES = /((director|head|\bvp\b|vice\s+president|chief|senior\s+director|sr\s+director|principal|staff)[\w\s,\-&/]*\b(ai|artificial\s+intelligence|data\s+scien\w*|data\s+platform|data\s+engineering|machine\s+learning|\bml\b|applied\s+ai|ml\s+platform|ai\s+platform|mlops|ai\s+governance|responsible\s+ai)\b)|(\b(ai\s+platform|artificial\s+intelligence|data\s+scien\w*|machine\s+learning|data\s+platform|data\s+engineering)\b[\w\s,\-&/]*\b(director|head|vice\s+president|\bvp\b|chief|principal)\b)|chief\s+ai\s+officer|chief\s+data\s+scientist|chief\s+data\s+officer/i;

export function isAILeadership(title: string): boolean {
  return _AIL_YES.test(title || "");
}

// AI/DS Leadership jobs show FantasticJobs' 4 coarse experience bands
// (0-2 / 2-5 / 5-10 / 10+) instead of our fine tray. Re-coarsen
// whatever tray a job carries into one of the four bands for display.
export function coarseExpBand(tray: string): string {
  const nums = (tray.match(/\d+/g) || []).map(Number);
  if (!nums.length) return tray;
  const mx = Math.max(...nums);
  const plus = /\+/.test(tray);
  if (plus && mx >= 10) return "10+";
  if (mx <= 2)  return "0-2";
  if (mx <= 5)  return "2-5";
  if (mx <= 10) return "5-10";
  return "10+";
}
