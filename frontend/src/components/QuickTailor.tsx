import { useState } from "react";
import { api } from "../api";
import { Sparkles, Loader2, Download, X, FileText, FolderDown } from "lucide-react";

interface Props { open?: boolean;
  onClose: () => void;
}

export function QuickTailor({ open = true, onClose, onToast }: Props & { open?: boolean; onToast?: (m:string,t?:"success"|"error")=>void }) {
  const [jd, setJd]           = useState("");
  const [company, setCompany] = useState("");
  const [tailored, setTailored] = useState("");
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");
  const [downloading, setDownloading] = useState<"pdf" | "docx" | null>(null);
  const [saving, setSaving]           = useState(false);
  const [saveMsg, setSaveMsg]         = useState("");

  const handleTailor = async () => {
    if (!jd.trim()) return;
    setLoading(true); setError(""); setTailored("");
    try {
      const res = await api.quickTailor(jd, company || "Company");
      setTailored(res.tailored_resume);
    } catch (e: any) {
      setError(e.message || "Failed");
    } finally {
      setLoading(false);
    }
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
    if (!jd.trim()) return;
    setDownloading(format);
    try {
      const url  = format === "pdf" ? api.quickTailorPdfUrl() : api.quickTailorDocxUrl();
      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jd, company: company || "Company" }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const blob = await resp.blob();
      const a    = document.createElement("a");
      a.href     = URL.createObjectURL(blob);
      a.download = `Jagadish_Reddy_Butukuri_Senior_Data_Engineer.${format}`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e: any) {
      setError(e.message || "Download failed");
    } finally {
      setDownloading(null);
    }
  };

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-purple-400" />
            <h2 className="text-sm font-semibold text-slate-100">Quick Tailor — Paste Any JD</h2>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors">
            <X size={16} />
          </button>
        </div>

        <div className="flex flex-1 gap-0 overflow-hidden">
          {/* Left — input */}
          <div className="flex flex-col flex-1 p-4 border-r border-slate-700 overflow-hidden">
            <input
              type="text"
              placeholder="Company name (e.g. Catalight Foundation)"
              value={company}
              onChange={e => setCompany(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-300 mb-3 focus:outline-none focus:border-purple-500"
            />
            <label className="text-[11px] text-slate-500 mb-1.5">Paste full job description:</label>
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
              {loading ? "Tailoring…" : "Tailor Resume"}
            </button>
            {error && <p className="mt-2 text-[11px] text-red-400">{error}</p>}
          </div>

          {/* Right — output */}
          <div className="flex flex-col flex-1 p-4 overflow-hidden">
            <div className="flex items-center justify-between mb-3">
              <label className="text-[11px] text-slate-500">Tailored resume preview:</label>
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
      </div>
    </div>
  );
}
