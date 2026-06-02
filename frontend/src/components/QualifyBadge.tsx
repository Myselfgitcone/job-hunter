import { useState } from "react";
import type { QualifyResult } from "../types";
import { CheckCircle2, XCircle, Loader2, ShieldCheck } from "lucide-react";
import { api } from "../api";

const CRITERIA_LABELS: Record<string, string> = {
  job_category: "Job Category",
  experience:   "Experience",
  skills_match: "Skills",
  sponsorship:  "Sponsorship",
  location:     "Location",
  seniority:    "Seniority",
};

interface Props {
  jobId: string;
  result: QualifyResult | null;
  onUpdated?: (r: QualifyResult) => void;
  compact?: boolean;
}

export function QualifyBadge({ jobId, result, onUpdated, compact = false }: Props) {
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const analyze = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setLoading(true);
    try {
      const r = await api.qualifyJob(jobId);
      onUpdated?.(r);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!result) {
    if (compact) return null;
    return (
      <button onClick={analyze} disabled={loading}
        className="flex items-center gap-1 text-[10px] px-2 py-0.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-full transition-colors disabled:opacity-50">
        {loading ? <Loader2 size={10} className="animate-spin" /> : <ShieldCheck size={10} />}
        {loading ? "Analyzing…" : "Qualify"}
      </button>
    );
  }

  const { qualified, score, summary, criteria } = result;
  const passed = Object.values(criteria || {}).filter(c => c.pass).length;
  const total  = Object.keys(criteria || {}).length;

  return (
    <div className="space-y-1">
      {/* Badge */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <button
          onClick={e => { e.stopPropagation(); setExpanded(x => !x); }}
          className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-semibold transition-colors ${
            qualified
              ? "bg-green-900/60 text-green-300 hover:bg-green-900/80"
              : "bg-red-900/40 text-red-400 hover:bg-red-900/60"
          }`}
        >
          {qualified ? <CheckCircle2 size={10} /> : <XCircle size={10} />}
          {qualified ? "Qualified" : "Not Qualified"}
          <span className="opacity-70 ml-1">{score}%</span>
        </button>

        {!compact && (
          <button onClick={analyze} disabled={loading}
            className="text-[9px] text-slate-600 hover:text-slate-400 transition-colors">
            {loading ? <Loader2 size={9} className="animate-spin inline" /> : "↺"}
          </button>
        )}
      </div>

      {/* Expanded criteria */}
      {expanded && !compact && (
        <div className="bg-slate-800/80 border border-slate-700 rounded-lg p-3 space-y-1.5 mt-1">
          <p className="text-[11px] text-slate-300 mb-2 italic">{summary}</p>
          {Object.entries(criteria || {}).map(([key, val]) => (
            <div key={key} className="flex items-start gap-2 text-[11px]">
              {val.pass
                ? <CheckCircle2 size={11} className="text-green-400 mt-0.5 flex-shrink-0" />
                : <XCircle     size={11} className="text-red-400 mt-0.5 flex-shrink-0" />}
              <span className={`font-medium w-20 flex-shrink-0 ${val.pass ? "text-green-300" : "text-red-300"}`}>
                {CRITERIA_LABELS[key] || key}
              </span>
              <span className="text-slate-400">{val.note}</span>
            </div>
          ))}
          <div className="mt-2 pt-2 border-t border-slate-700 text-[10px] text-slate-500">
            {passed}/{total} criteria passed
          </div>
        </div>
      )}
    </div>
  );
}
