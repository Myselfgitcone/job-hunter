import { useEffect, useRef, useState } from "react";

interface Company {
  name: string;
  domain: string;
  logo: string;
}

interface Props {
  value: string;
  onChange: (val: string) => void;
  className?: string;
}

export function CompanyAutocomplete({ value, onChange, className }: Props) {
  const [suggestions, setSuggestions] = useState<Company[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selectedLogo, setSelectedLogo] = useState<string>("");
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const userTypedRef = useRef(false);

  const handleChange = (val: string) => {
    userTypedRef.current = true;
    onChange(val);
    setSelectedLogo("");
  };

  useEffect(() => {
    if (!userTypedRef.current) return;
    const q = value.trim();
    if (q.length < 2) { setSuggestions([]); setOpen(false); return; }

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await fetch(
          `https://autocomplete.clearbit.com/v1/companies/suggest?query=${encodeURIComponent(q)}`
        );
        const data: Company[] = await res.json();
        setSuggestions(data.slice(0, 8));
        setOpen(data.length > 0);
      } catch {
        setSuggestions([]);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [value]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const logoUrl = (domain: string) =>
    `https://www.google.com/s2/favicons?domain=${domain}&sz=64`;

  const handleSelect = (company: Company) => {
    userTypedRef.current = false;
    onChange(company.name);
    setSelectedLogo(logoUrl(company.domain));
    setOpen(false);
    setSuggestions([]);
  };

  return (
    <div style={{ position: "relative" }} ref={containerRef}>
      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
        {selectedLogo && (
          <img
            src={selectedLogo}
            alt=""
            style={{ position: "absolute", left: 10, width: 16, height: 16, borderRadius: 3, objectFit: "contain", flexShrink: 0 }}
            onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        )}
        <input
          type="text"
          value={value}
          onChange={e => handleChange(e.target.value)}
          onFocus={() => { if (suggestions.length > 0) setOpen(true); }}
          placeholder="Company name (e.g. Google, Stripe, Apple…)"
          className={className}
          style={{ paddingLeft: selectedLogo ? 32 : undefined }}
        />
        {loading && (
          <div style={{ position: "absolute", right: 10 }}>
            <svg style={{ width: 13, height: 13, animation: "spin 1s linear infinite", opacity: 0.5 }} fill="none" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" style={{ opacity: 0.25 }} />
              <path fill="currentColor" d="M4 12a8 8 0 018-8v8z" style={{ opacity: 0.75 }} />
            </svg>
          </div>
        )}
      </div>

      {open && suggestions.length > 0 && (
        <ul style={{
          position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 9999,
          background: "#ffffff",
          border: "1px solid #e2e8f0",
          borderRadius: 8, overflow: "hidden",
          boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
          margin: 0, padding: 0, listStyle: "none",
        }}>
          {suggestions.map(company => (
            <li key={company.domain}>
              <button
                onMouseDown={e => e.preventDefault()}
                onClick={() => handleSelect(company)}
                style={{
                  width: "100%", padding: "8px 12px",
                  display: "flex", alignItems: "center", gap: 10,
                  background: "transparent", border: "none", cursor: "pointer",
                  transition: "background 0.12s", textAlign: "left",
                }}
                onMouseEnter={e => (e.currentTarget.style.background = "#f8fafc")}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
              >
                <img
                  src={logoUrl(company.domain)}
                  alt={company.name}
                  style={{ width: 20, height: 20, borderRadius: 4, objectFit: "contain", flexShrink: 0 }}
                  onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
                />
                <span style={{ fontSize: 12.5, color: "#0f172a", flex: 1, fontWeight: 500 }}>{company.name}</span>
                <span style={{ fontSize: 10, color: "#94a3b8" }}>{company.domain}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
