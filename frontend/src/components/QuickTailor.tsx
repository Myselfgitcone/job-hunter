import { useState, useEffect, useRef } from "react";
import { api } from "../api";
import { Sparkles, Loader2, Download, X, FileText, FolderDown, Upload } from "lucide-react";
import { CompanyAutocomplete } from "./CompanyAutocomplete";
import type { GateScores } from "../types";

const QT_BANDS: { min: number; label: string }[] = [
  { min: 90, label: "Outstanding" }, { min: 85, label: "Excellent" },
  { min: 80, label: "Best" }, { min: 75, label: "Very Good" },
  { min: 70, label: "Good" }, { min: 60, label: "Fair" }, { min: 0, label: "Needs Work" },
];

interface Props { open?: boolean; onClose: () => void; tailorModel?: string; pageMode?: boolean; }

export function QuickTailor({ open = true, onClose, onToast, pageMode = false }: Props & { open?: boolean; onToast?: (m:string,t?:"success"|"error")=>void }) {
  const [jd, setJd]           = useState("");
  const [company, setCompany] = useState("");
  const [tailored, setTailored] = useState("");
  const [scores, setScores]     = useState<GateScores | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");
  const [downloading, setDownloading] = useState<"pdf" | "docx" | null>(null);
  const [saving, setSaving]           = useState(false);
  const [saveMsg, setSaveMsg]         = useState("");
  const [elapsed, setElapsed]         = useState(0);
  const [finalTime, setFinalTime]     = useState<number | null>(null);
  const timerRef                       = useRef<ReturnType<typeof setInterval> | null>(null);
  const [uploadingJd, setUploadingJd] = useState(false);
  const [jdUploadError, setJdUploadError] = useState("");
  const jdFileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (loading) {
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed(s => s + 1), 1000);
    } else {
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [loading]);

  const handleTailor = async () => {
    if (!jd.trim()) return;
    setLoading(true); setError(""); setTailored(""); setScores(null); setFinalTime(null);
    const startedAt = Date.now();
    try {
      const res = await api.quickTailor(jd, company || "Company");
      setTailored(res.tailored_resume);
      setScores(res.gate_scores ?? null);
      setFinalTime(Math.round((Date.now() - startedAt) / 1000));
    } catch (e: any) {
      setError(e.message || "Failed");
    } finally {
      setLoading(false);
    }
  };

  const handleUploadJdClick = () => jdFileRef.current?.click();

  const handleUploadJd = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    setUploadingJd(true); setJdUploadError("");
    try {
      const { text } = await api.extractJdFile(file);
      setJd(text);
    } catch (err: any) {
      setJdUploadError(err?.message || "Could not extract text from file");
    } finally {
      setUploadingJd(false);
    }
    e.target.value = "";
  };

  const handleSavePackage = async () => {
    if (!tailored || !jd.trim()) return;
    setSaving(true); setSaveMsg("");
    try {
      const res = await api.quickSavePackage(company || "Company", jd, tailored);
      setSaveMsg(`✓ Saved to: ${res.folder}`);
      setTimeout(() => setSaveMsg(""), 6000);
    } catch (e: any) { setSaveMsg(`✗ ${e.message}`); }
    finally { setSaving(false); }
  };

  const handleDownload = async (format: "pdf" | "docx") => {
    if (!jd.trim() || !tailored) return;
    setDownloading(format);
    try {
      const url   = format === "pdf" ? api.quickTailorPdfUrl() : api.quickTailorDocxUrl();
      const token = localStorage.getItem("jh_token");
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { "Authorization": `Bearer ${token}` } : {}),
        },
        // Pass the already-computed resume so backend skips AI and uses same content as UI
        body: JSON.stringify({ jd, company: company || "Company", tailored_resume: tailored }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const blob = await resp.blob();
      // Read filename from Content-Disposition header (matches job tailor behavior)
      const cd = resp.headers.get("Content-Disposition");
      const filename = cd?.match(/filename="([^"]+)"/)?.[1] || `Resume_${company || "Company"}.${format}`;
      const a    = document.createElement("a");
      a.href     = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e: any) {
      setError(e.message || "Download failed");
    } finally {
      setDownloading(null);
    }
  };

  if (!open && !pageMode) return null;

  const inner = (
    <>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-purple-400" />
            <h2 className="text-sm font-semibold text-slate-100">Quick Tailor — Paste Any JD</h2>
          </div>
          {!pageMode && (
            <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors">
              <X size={16} />
            </button>
          )}
        </div>

        <div className="flex flex-1 gap-0 overflow-hidden">
          {/* Left — input */}
          <div className="flex flex-col flex-1 p-4 border-r border-slate-700 overflow-hidden">
            <div className="mb-3">
              <CompanyAutocomplete
                value={company}
                onChange={setCompany}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-300 focus:outline-none focus:border-purple-500"
              />
            </div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[11px] text-slate-500">Paste full job description:</label>
              <button
                onClick={handleUploadJdClick}
                disabled={uploadingJd}
                className="flex items-center gap-1 px-2 py-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-700 text-slate-300 text-[11px] rounded-lg transition-colors"
              >
                {uploadingJd ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
                {uploadingJd ? "Reading…" : "Upload JD"}
              </button>
              <input
                ref={jdFileRef}
                type="file"
                accept=".pdf,.docx,.txt"
                style={{ display: "none" }}
                onChange={handleUploadJd}
              />
            </div>
            {jdUploadError && <p className="mb-1.5 text-[11px] text-red-400">{jdUploadError}</p>}
            <textarea
              value={jd}
              onChange={e => setJd(e.target.value)}
              rows={18}
              placeholder="Paste the full job description here…"
              className="flex-1 w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-300 font-sans focus:outline-none focus:border-purple-500 resize-none"
            />
            <button
              onClick={handleTailor}
              disabled={loading || !jd.trim()}
              className="mt-3 flex items-center justify-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-xs rounded-lg transition-colors font-medium"
            >
              {loading ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
              {loading ? `Tailoring… ${elapsed}s` : "Tailor Resume"}
            </button>
            {error && <p className="mt-2 text-[11px] text-red-400">{error}</p>}
          </div>

          {/* Right — output */}
          <div className="flex flex-col flex-1 p-4 overflow-hidden">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <label className="text-[11px] text-slate-500">Tailored resume preview:</label>
                {finalTime !== null && (
                  <span className="text-[11px] text-emerald-400">Tailored in {finalTime}s</span>
                )}
              </div>
              {tailored && (
                <div className="flex gap-2 flex-wrap">
                  <button
                    onClick={() => handleDownload("pdf")}
                    disabled={!!downloading}
                    className="flex items-center gap-1 px-2.5 py-1 bg-emerald-700/70 hover:bg-emerald-700 disabled:opacity-50 text-white text-[11px] rounded-lg transition-colors"
                  >
                    {downloading === "pdf" ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
                    PDF
                  </button>
                  <button
                    onClick={() => handleDownload("docx")}
                    disabled={!!downloading}
                    className="flex items-center gap-1 px-2.5 py-1 bg-blue-700/70 hover:bg-blue-700 disabled:opacity-50 text-white text-[11px] rounded-lg transition-colors"
                  >
                    {downloading === "docx" ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
                    DOCX
                  </button>
                  <button
                    onClick={handleSavePackage}
                    disabled={saving || !!downloading}
                    title="Save JD + PDF + DOCX into company folder on Desktop"
                    className="flex items-center gap-1 px-2.5 py-1 bg-amber-700/70 hover:bg-amber-700 disabled:opacity-50 text-white text-[11px] rounded-lg transition-colors"
                  >
                    {saving ? <Loader2 size={11} className="animate-spin" /> : <FolderDown size={11} />}
                    {saving ? "Saving…" : "Save to Folder"}
                  </button>
                </div>
              )}
            </div>
            {saveMsg && (
              <p className={`text-[11px] mb-2 ${saveMsg.startsWith("✓") ? "text-green-400" : "text-red-400"}`}>
                {saveMsg}
              </p>
            )}
            {scores && typeof scores.overall === "number" && (() => {
              const o = scores.overall!;
              const band = QT_BANDS.find(b => o >= b.min) ?? QT_BANDS[QT_BANDS.length - 1];
              const oc = o >= 80 ? "text-green-400" : o >= 70 ? "text-yellow-400" : o >= 60 ? "text-amber-400" : "text-red-400";
              const rec = o >= 70 ? { t: "✓ Submit — application-ready", c: "bg-green-500/15 text-green-400 border-green-500/40" }
                        : o >= 60 ? { t: "Borderline — your call",       c: "bg-amber-500/15 text-amber-400 border-amber-500/40" }
                        :          { t: "✕ Don’t submit yet — improve",  c: "bg-red-500/15 text-red-400 border-red-500/40" };
              const gate = (label: string, v?: { score?: number }) =>
                typeof v?.score === "number" ? <span className="text-slate-400">{label} <b className="text-slate-200">{v.score}</b></span> : null;
              return (
                <div className="mb-2 flex items-center flex-wrap gap-x-4 gap-y-1 rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-2 text-[11px]">
                  <span className={`text-lg font-bold ${oc}`}>{o}</span>
                  <span className={`font-semibold ${oc}`}>{band.label}</span>
                  <span className={`px-2 py-0.5 rounded border font-semibold ${rec.c}`}>{rec.t}</span>
                  <span className="ml-auto flex gap-3">
                    {gate("ATS", scores.ats)}{gate("Recruiter", scores.recruiter)}{gate("Hiring Mgr", scores.hiring_manager)}
                  </span>
                </div>
              );
            })()}
            {tailored ? (
              <textarea
                readOnly
                value={tailored}
                className="flex-1 w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-[11px] text-slate-300 font-mono resize-none focus:outline-none"
              />
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-600 gap-2">
                <FileText size={32} />
                <p className="text-xs">Tailored resume appears here</p>
              </div>
            )}
          </div>
        </div>
    </>
  );

  if (pageMode) {
    return (
      <div className="flex flex-col bg-slate-900 border border-slate-700 rounded-xl shadow-2xl" style={{ margin: 24, flex: 1, overflow: "hidden" }}>
        {inner}
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl">
        {inner}
      </div>
    </div>
  );
}
