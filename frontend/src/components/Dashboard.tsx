import { useEffect, useState } from "react";
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, Cell, PieChart, Pie,
} from "recharts";
import { api } from "../api";
import {
  Briefcase, CheckCircle2, Trophy, Sparkles,
  FileText, Clock, MapPin, TrendingUp, Zap, SkipForward,
} from "lucide-react";

// ── utils ─────────────────────────────────────────────────────────────────────

function timeAgo(iso: string) {
  if (!iso) return "";
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    if (d < 7)  return `${d}d ago`;
    return new Date(iso).toLocaleDateString("en-US",{month:"short",day:"numeric"});
  } catch { return ""; }
}

const PALETTE = [
  "#8b5cf6","#22d3ee","#10b981","#f59e0b",
  "#ec4899","#6366f1","#06b6d4","#f97316","#84cc16","#ef4444",
];

const TT = ({ active, payload, label }: any) =>
  active && payload?.length ? (
    <div style={{background:"var(--bg-elevated)",border:"1px solid var(--border-default)",borderRadius:10,padding:"10px 14px",boxShadow:"var(--card-shadow)",fontSize:12}}>
      <p style={{color:"var(--text-muted)",marginBottom:6,fontWeight:600}}>{label}</p>
      {payload.map((p: any) => (
        <p key={p.name} className="flex items-center gap-2 mb-0.5" style={{color:p.color}}>
          <span className="w-1.5 h-1.5 rounded-full inline-block" style={{background:p.color}}/>
          {p.name}: <span className="font-mono font-bold ml-auto pl-3">{p.value}</span>
        </p>
      ))}
    </div>
  ) : null;

// ── Stat Card ─────────────────────────────────────────────────────────────────

function Stat({ label, value, icon, gradient, delta }: {
  label: string; value: number; icon: React.ReactNode;
  gradient: string; delta?: string;
}) {
  return (
    <div className={`relative overflow-hidden rounded-2xl p-5 ${gradient} border border-white/5`}>
      {/* background glow */}
      <div className="absolute -right-4 -top-4 w-24 h-24 rounded-full bg-white/5 blur-xl"/>
      <div className="relative">
        <div className="flex items-start justify-between">
          <div className="w-10 h-10 rounded-xl bg-white/10 backdrop-blur flex items-center justify-center">
            {icon}
          </div>
          {delta && (
            <span className="text-[10px] font-semibold text-white/60 bg-white/10 px-2 py-0.5 rounded-full">
              {delta}
            </span>
          )}
        </div>
        <p className="text-3xl font-black text-white mt-3 tabular-nums tracking-tight">{value}</p>
        <p className="text-[11px] text-white/60 mt-0.5 font-medium">{label}</p>
      </div>
    </div>
  );
}

// ── History Card ──────────────────────────────────────────────────────────────

function HistCard({ job, rank, kind }: { job: any; rank: number; kind: "applied"|"tailored" }) {
  const isApplied = kind === "applied";
  return (
    <div className="group flex items-start gap-3 p-3 rounded-xl bg-slate-800/40 border border-slate-700/30 hover:border-slate-600/60 hover:bg-slate-800/70 transition-all cursor-default">
      <div className="relative shrink-0">
        <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${
          isApplied ? "bg-blue-600/20 border border-blue-500/30" : "bg-violet-600/20 border border-violet-500/30"
        }`}>
          <FileText size={14} className={isApplied ? "text-blue-400" : "text-violet-400"}/>
        </div>
        <span className="absolute -top-1.5 -left-1.5 text-[9px] font-bold text-slate-500 bg-slate-900 rounded px-0.5">
          #{rank}
        </span>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <p className="text-xs font-semibold text-slate-100 leading-snug truncate">
            {job.company} — <span className="font-normal text-slate-300">{job.title}</span>
          </p>
          <span className={`shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded-full ${
            isApplied
              ? "bg-green-500/15 text-green-400 border border-green-500/25"
              : "bg-violet-500/15 text-violet-400 border border-violet-500/25"
          }`}>
            {isApplied ? "✓ Applied" : "⚡ Tailored"}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 mt-1 text-[10px] text-slate-500">
          {job.scraped_at && (
            <span className="flex items-center gap-1"><Clock size={8}/>{timeAgo(job.scraped_at)}</span>
          )}
          {job.location && (
            <span className="flex items-center gap-1 truncate max-w-[120px]">
              <MapPin size={8}/>{job.location}
            </span>
          )}
          {job.country && (
            <span className="text-slate-600">{job.country}</span>
          )}
          {job.salary && <span className="text-green-400 font-medium">{job.salary}</span>}
        </div>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export function Dashboard() {
  const [data, setData]         = useState<any>(null);
  const [loading, setLoading]   = useState(true);
  const [reminders, setReminders] = useState<any[]>([]);

  useEffect(() => {
    api.getAnalytics().then(setData).catch(console.error).finally(() => setLoading(false));
    api.getReminders().then(setReminders).catch(() => {});
  }, []);

  if (loading) return (
    <div className="flex items-center justify-center h-full">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"/>
        <p className="text-slate-500 text-sm">Loading dashboard…</p>
      </div>
    </div>
  );

  if (!data) return null;

  const st       = data.by_status   || {};
  const total    = data.total       || 0;
  const applied  = st["applied"]    || 0;
  const interview= st["interview"]  || 0;
  const skipped  = st["skipped"]    || 0;
  const tailored = (data.tailored_jobs || []).length;
  const newJobs  = st["new"]        || 0;

  const timeline    = data.timeline    || [];
  const monthly     = data.monthly     || [];
  const countryData = (data.by_country || []).map(([c,n]:[string,number]) => ({name:c,count:n}));
  const sourceData  = (data.by_source  || []).map(([s,n]:[string,number]) => ({name:s,count:n}));

  const hasTimeline = timeline.some((d:any) => d.scraped > 0 || d.applied > 0);
  const hasMonthly  = monthly.some((d:any)  => d.scraped > 0 || d.applied > 0);

  const appliedJobs  = data.applied_jobs  || [];
  const tailoredJobs = data.tailored_jobs || [];

  // Pie data for status
  const pieData = [
    { name:"New",       value:newJobs,   color:"#64748b" },
    { name:"Applied",   value:applied,   color:"#3b82f6" },
    { name:"Interview", value:interview, color:"#10b981" },
    { name:"Tailored",  value:tailored,  color:"#8b5cf6" },
    { name:"Skipped",   value:skipped,   color:"#374151" },
  ].filter(d => d.value > 0);

  return (
    <div style={{ flex: 1, overflow: "auto", background: "var(--bg-base)" }}>
      <div className="p-6 space-y-6 max-w-6xl">

        {/* ── Header ── */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-black text-white tracking-tight">Dashboard</h2>
            <p className="text-xs text-slate-500 mt-0.5">Jagadish Reddy Butukuri · Senior Data Engineer</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-500 bg-slate-800/60 border border-slate-700/50 rounded-xl px-4 py-2">
            <Zap size={12} className="text-yellow-400"/>
            Last updated: {new Date().toLocaleDateString("en-US",{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"})}
          </div>
        </div>

        {/* ── Stat cards ── */}
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
          <Stat label="Total Scraped" value={total}
            icon={<Briefcase size={16} className="text-white"/>}
            gradient="bg-gradient-to-br from-slate-700 to-slate-800"
            delta="All time"/>
          <Stat label="New Jobs" value={newJobs}
            icon={<FileText size={16} className="text-white"/>}
            gradient="bg-gradient-to-br from-indigo-600 to-indigo-800"
            delta="Pending"/>
          <Stat label="Applied" value={applied}
            icon={<CheckCircle2 size={16} className="text-white"/>}
            gradient="bg-gradient-to-br from-blue-600 to-blue-800"
            delta="All time"/>
          <Stat label="Interviews" value={interview}
            icon={<Trophy size={16} className="text-white"/>}
            gradient="bg-gradient-to-br from-green-600 to-green-800"
            delta="🎉"/>
          <Stat label="AI Tailored" value={tailored}
            icon={<Sparkles size={16} className="text-white"/>}
            gradient="bg-gradient-to-br from-violet-600 to-violet-800"
            delta="Resumes"/>
        </div>

        {/* ── Reminders ── */}
        {reminders.length > 0 && (
          <div className="bg-amber-950/30 border border-amber-700/40 rounded-2xl p-5">
            <div className="flex items-center gap-2 mb-3">
              <Clock size={15} className="text-amber-400"/>
              <span className="text-sm font-semibold text-amber-300">Upcoming Deadlines & Interviews</span>
              <span className="ml-auto text-xs text-amber-600 bg-amber-900/40 px-2 py-0.5 rounded-full">{reminders.length}</span>
            </div>
            <div className="space-y-2">
              {reminders.map((r: any) => (
                <div key={r.id} className="flex items-center gap-3 text-xs">
                  <div className="flex-1 min-w-0">
                    <span className="font-medium text-slate-200 truncate block">{r.title}</span>
                    <span className="text-slate-500">{r.company}</span>
                  </div>
                  {r.days_until_interview !== null && (
                    <span className={`px-2 py-0.5 rounded-full font-mono ${r.days_until_interview <= 1 ? "bg-red-900/60 text-red-300" : "bg-green-900/40 text-green-300"}`}>
                      Interview {r.days_until_interview === 0 ? "today" : r.days_until_interview === 1 ? "tomorrow" : `in ${r.days_until_interview}d`}
                    </span>
                  )}
                  {r.days_until_deadline !== null && (
                    <span className={`px-2 py-0.5 rounded-full font-mono ${r.days_until_deadline <= 1 ? "bg-red-900/60 text-red-300" : "bg-amber-900/40 text-amber-300"}`}>
                      Deadline {r.days_until_deadline === 0 ? "today" : r.days_until_deadline === 1 ? "tomorrow" : `in ${r.days_until_deadline}d`}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Charts row 1: Monthly + 30-day ── */}
        <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">

          {/* Monthly trends — takes 3/5 */}
          <div className="xl:col-span-3 rounded-2xl p-5" style={{background:"var(--bg-elevated)",border:"1px solid var(--line)"}}>

            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className="text-sm font-bold text-white">Monthly Trends</h3>
                <p className="text-[11px] text-slate-500 mt-0.5">Last 6 months activity</p>
              </div>
              <div className="flex items-center gap-3 text-[10px] text-slate-500">
                <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-indigo-500 inline-block"/>Scraped</span>
                <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-blue-500 inline-block"/>Applied</span>
                <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-violet-500 inline-block"/>Tailored</span>
              </div>
            </div>
            {hasMonthly ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={monthly} barGap={4} margin={{top:4,right:4,left:-20,bottom:0}}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false}/>
                  <XAxis dataKey="month" tick={{fill:"var(--tx-3)",fontSize:11,fontFamily:"var(--f-ui)"}} axisLine={false} tickLine={false}/>
                  <YAxis tick={{fill:"var(--tx-3)",fontSize:10,fontFamily:"var(--f-ui)"}} axisLine={false} tickLine={false} allowDecimals={false}/>
                  <Tooltip content={<TT/>} cursor={{fill:"rgba(255,255,255,0.03)"}}/>
                  <Bar dataKey="scraped"  name="Scraped"  fill="#6366f1" radius={[4,4,0,0]} maxBarSize={22}/>
                  <Bar dataKey="applied"  name="Applied"  fill="#3b82f6" radius={[4,4,0,0]} maxBarSize={22}/>
                  <Bar dataKey="tailored" name="Tailored" fill="#8b5cf6" radius={[4,4,0,0]} maxBarSize={22}/>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart h={200} msg="Scrape jobs to see monthly trends"/>
            )}
          </div>

          {/* Pie status — takes 2/5 */}
          <div className="xl:col-span-2 rounded-2xl p-5 bg-bg-elevated border border-line">
            <div className="mb-5">
              <h3 className="text-sm font-bold text-white">Status Breakdown</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">{total} total jobs</p>
            </div>
            {pieData.length > 0 ? (
              <div className="flex flex-col items-center">
                <ResponsiveContainer width="100%" height={150}>
                  <PieChart>
                    <Pie data={pieData} dataKey="value" cx="50%" cy="50%"
                         innerRadius={40} outerRadius={68}
                         paddingAngle={3} strokeWidth={0}>
                      {pieData.map((d,i) => <Cell key={i} fill={d.color}/>)}
                    </Pie>
                    <Tooltip content={<TT/>}/>
                  </PieChart>
                </ResponsiveContainer>
                <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 mt-2 w-full">
                  {pieData.map(d => (
                    <div key={d.name} className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full shrink-0" style={{background:d.color}}/>
                      <span className="text-[10px] text-slate-400">{d.name}</span>
                      <span className="text-[10px] font-mono text-white ml-auto">{d.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <EmptyChart h={150} msg="No data yet"/>
            )}
          </div>
        </div>

        {/* ── 30-day line chart ── */}
        <div className="rounded-2xl p-5 bg-bg-elevated border border-line">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="text-sm font-bold text-white">30-Day Activity</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">Daily scraping and application activity</p>
            </div>
          </div>
          {hasTimeline ? (
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={timeline} margin={{top:4,right:4,left:-20,bottom:0}}>
                <defs>
                  {[["gS","#6366f1"],["gA","#3b82f6"],["gT","#8b5cf6"]].map(([id,c]) => (
                    <linearGradient key={id} id={id} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={c} stopOpacity={0.25}/>
                      <stop offset="95%" stopColor={c} stopOpacity={0}/>
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false}/>
                <XAxis dataKey="label" tick={{fill:"var(--tx-3)",fontSize:9,fontFamily:"var(--f-ui)"}} axisLine={false} tickLine={false} interval={4}/>
                <YAxis tick={{fill:"var(--tx-3)",fontSize:9,fontFamily:"var(--f-ui)"}} axisLine={false} tickLine={false} allowDecimals={false}/>
                <Tooltip content={<TT/>}/>
                <Area type="monotone" dataKey="scraped"  name="Scraped"
                      stroke="#6366f1" strokeWidth={2} fill="url(#gS)"
                      dot={{r:2,fill:"#6366f1",strokeWidth:0}} activeDot={{r:4}}/>
                <Area type="monotone" dataKey="applied"  name="Applied"
                      stroke="#3b82f6" strokeWidth={2} fill="url(#gA)"
                      dot={{r:2,fill:"#3b82f6",strokeWidth:0}} activeDot={{r:4}}/>
                <Area type="monotone" dataKey="tailored" name="Tailored"
                      stroke="#8b5cf6" strokeWidth={2} fill="url(#gT)"
                      dot={{r:2,fill:"#8b5cf6",strokeWidth:0}} activeDot={{r:4}}/>
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart h={180} msg="No activity yet — start scraping!"/>
          )}
        </div>

        {/* ── Country + Source ── */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">

          <div className="rounded-2xl p-5 bg-bg-elevated border border-line">
            <h3 className="text-sm font-bold text-white mb-1">🌍 Jobs by Country</h3>
            <p className="text-[11px] text-slate-500 mb-4">Top markets</p>
            {countryData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={countryData} layout="vertical"
                          margin={{top:0,right:28,left:8,bottom:0}}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" horizontal={false}/>
                  <XAxis type="number" tick={{fill:"var(--tx-3)",fontSize:10,fontFamily:"var(--f-ui)"}} axisLine={false} tickLine={false} allowDecimals={false}/>
                  <YAxis type="category" dataKey="name" width={90}
                         tick={{fill:"var(--tx-2)",fontSize:11,fontFamily:"var(--f-ui)"}} axisLine={false} tickLine={false}/>
                  <Tooltip content={<TT/>} cursor={{fill:"rgba(255,255,255,0.03)"}}/>
                  <Bar dataKey="count" name="Jobs" radius={[0,6,6,0]}>
                    {countryData.map((_:any,i:number) => <Cell key={i} fill={PALETTE[i%PALETTE.length]}/>)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart h={220} msg="No country data yet"/>
            )}
          </div>

          <div className="rounded-2xl p-5 bg-bg-elevated border border-line">
            <h3 className="text-sm font-bold text-white mb-1">📡 Jobs by Source</h3>
            <p className="text-[11px] text-slate-500 mb-4">Scraper performance</p>
            {sourceData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={sourceData} margin={{top:0,right:8,left:-24,bottom:0}}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false}/>
                  <XAxis dataKey="name" tick={{fill:"var(--tx-3)",fontSize:10,fontFamily:"var(--f-ui)"}} axisLine={false} tickLine={false}/>
                  <YAxis tick={{fill:"var(--tx-3)",fontSize:10,fontFamily:"var(--f-ui)"}} axisLine={false} tickLine={false} allowDecimals={false}/>
                  <Tooltip content={<TT/>} cursor={{fill:"rgba(255,255,255,0.03)"}}/>
                  <Bar dataKey="count" name="Jobs" radius={[6,6,0,0]}>
                    {sourceData.map((_:any,i:number) => <Cell key={i} fill={PALETTE[i%PALETTE.length]}/>)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart h={220} msg="No source data yet"/>
            )}
          </div>
        </div>

        {/* ── Resume History ── */}
        <div className="rounded-2xl p-5" style={{background:"var(--bg-elevated)",border:"1px solid var(--line)"}}>
          <div className="flex items-center gap-2 mb-5">
            <FileText size={15} className="text-blue-400"/>
            <h3 className="text-sm font-bold text-white">Resume History</h3>
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">

            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-green-400"/>
                  <span className="text-xs font-bold text-green-400">Applied Resumes</span>
                </div>
                <span className="text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded-full">
                  {appliedJobs.length} total
                </span>
              </div>
              {appliedJobs.length === 0 ? (
                <div className="text-center py-8 text-slate-600 text-xs">
                  <CheckCircle2 size={24} className="mx-auto mb-2 opacity-30"/>
                  No applied jobs yet
                </div>
              ) : (
                <div className="space-y-2 max-h-80 overflow-y-auto pr-1 custom-scroll">
                  {appliedJobs.map((job:any, i:number) => (
                    <HistCard key={job.id} job={job} rank={i+1} kind="applied"/>
                  ))}
                </div>
              )}
            </div>

            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-violet-400"/>
                  <span className="text-xs font-bold text-violet-400">Tailored Resumes</span>
                </div>
                <span className="text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded-full">
                  {tailoredJobs.length} total
                </span>
              </div>
              {tailoredJobs.length === 0 ? (
                <div className="text-center py-8 text-slate-600 text-xs">
                  <Sparkles size={24} className="mx-auto mb-2 opacity-30"/>
                  No tailored resumes yet
                </div>
              ) : (
                <div className="space-y-2 max-h-80 overflow-y-auto pr-1 custom-scroll">
                  {tailoredJobs.map((job:any, i:number) => (
                    <HistCard key={job.id} job={job} rank={i+1} kind="tailored"/>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

function EmptyChart({ h, msg }: { h: number; msg: string }) {
  return (
    <div className="flex items-center justify-center text-slate-600 text-xs" style={{height:h}}>
      <div className="text-center">
        <div className="text-2xl mb-2 opacity-30">📊</div>
        {msg}
      </div>
    </div>
  );
}
