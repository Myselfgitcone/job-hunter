from zoneinfo import ZoneInfo
EST = ZoneInfo('America/New_York')
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timedelta, timezone
import re

RELEVANT_TITLE_TERMS = []  # empty = accept all titles

CUTOFF_HOURS = 168  # 7 days

# Country detection keywords → country name
# ORDER MATTERS — more specific first, USA last (has aggressive state abbreviations)
_COUNTRY_KEYWORDS = [
    (["india", "bangalore", "bengaluru", "mumbai", "hyderabad", "chennai",
      "pune", "delhi", "noida", "gurgaon", "gurugram", "kolkata", "ahmedabad",
      "jaipur", "kochi", "coimbatore", "remote - india"], "India"),
    (["germany", "deutschland", "berlin", "munich", "münchen", "hamburg",
      "frankfurt", "cologne", "köln", "düsseldorf", "stuttgart", "nuremberg",
      "nürnberg", "leipzig", "dresden", "hannover"], "Germany"),
    (["united kingdom", "england", "scotland", "wales", " uk,", " uk)", "(uk)", ", uk",
      "london", "manchester", "birmingham", "bristol", "edinburgh", "leeds",
      "glasgow", "liverpool", "sheffield", "cambridge", "oxford"], "UK"),
    (["canada", "toronto", "vancouver", "montreal", "calgary", "ottawa",
      "edmonton", "winnipeg", "quebec", " qc,", ", qc", " on,", ", on",
      " bc,", ", bc", " ab,", ", ab"], "Canada"),
    (["ukraine", "kyiv", "kharkiv", "odessa", "lviv", "dnipro"], "Ukraine"),
    (["new zealand", "auckland", "wellington", "christchurch"], "NewZealand"),
    (["australia", "sydney", "melbourne", "brisbane", "perth", "adelaide",
      "canberra", "gold coast"], "Australia"),
    (["netherlands", "amsterdam", "rotterdam", "utrecht", "eindhoven",
      "the hague", "den haag", "tilburg", "groningen"], "Netherlands"),
    (["singapore"], "Singapore"),
    (["france", "paris", "lyon", "marseille", "toulouse", "bordeaux",
      "nantes", "strasbourg", "lille"], "France"),
    (["poland", "warsaw", "kraków", "krakow", "wroclaw", "wrocław",
      "gdańsk", "gdansk", "poznan", "łódź", "lodz"], "Poland"),
    (["switzerland", "zurich", "zürich", "geneva", "bern", "basel"], "Switzerland"),
    (["sweden", "stockholm", "gothenburg", "malmö", "malmo"], "Sweden"),
    (["spain", "madrid", "barcelona", "valencia", "seville"], "Spain"),
    (["italy", "milan", "milano", "rome", "roma", "turin"], "Italy"),
    (["ireland", "dublin", "cork", "galway"], "Ireland"),
    (["denmark", "copenhagen", "københavn"], "Denmark"),
    (["finland", "helsinki", "tampere"], "Finland"),
    (["norway", "oslo", "bergen"], "Norway"),
    # USA — states, cities, abbreviations (LAST — has broad patterns)
    (["united states", " usa", "usa,", "(usa)", "u.s.a", "u.s.",
      " al ", " ak ", " az ", " ar ", " ca ", " co ", " ct ", " de ", " fl ",
      " ga ", " hi ", " id ", " il ", " in ", " ia ", " ks ", " ky ", " la ",
      " me ", " md ", " ma ", " mi ", " mn ", " ms ", " mo ", " mt ", " ne ",
      " nv ", " nh ", " nj ", " nm ", " ny ", " nc ", " nd ", " oh ", " ok ",
      " or ", " pa ", " ri ", " sc ", " sd ", " tn ", " tx ", " ut ", " vt ",
      " va ", " wa ", " wv ", " wi ", " wy ",
      ", al", ", ak", ", az", ", ar", ", ca", ", co", ", ct", ", de", ", fl",
      ", ga", ", hi", ", id", ", il", ", in", ", ia", ", ks", ", ky", ", la",
      ", me", ", md", ", ma", ", mi", ", mn", ", ms", ", mo", ", mt", ", ne",
      ", nv", ", nh", ", nj", ", nm", ", ny", ", nc", ", nd", ", oh", ", ok",
      ", or", ", pa", ", ri", ", sc", ", sd", ", tn", ", tx", ", ut", ", vt",
      ", va", ", wa", ", wv", ", wi", ", wy",
      "new york", "california", "texas", "chicago", "seattle", "boston",
      "austin", "denver", "atlanta", "miami", "minneapolis", "san francisco",
      "los angeles", "washington dc", "washington, d", "phoenix", "portland",
      "san diego", "dallas", "houston", "charlotte", "nashville", "detroit",
      "remote - us", "remote us", "remote (us"], "USA"),
]


def detect_country(location: str, default: str = "Remote") -> str:
    if not location or not location.strip():
        return default
    loc = " " + location.lower() + " "   # pad so boundary checks work
    for keywords, country in _COUNTRY_KEYWORDS:
        if any(kw in loc for kw in keywords):
            return country
    if "remote" in loc:
        return "Remote"
    return default


MAX_YEARS_EXPERIENCE = 8  # skip jobs requiring more than this

SEARCH_TERMS = ["data engineer", "senior data engineer"]

# Patterns: "7+ years", "7-10 years", "minimum 7 years", "at least 7 years", "7 years of experience"
_EXP_RE = re.compile(
    r'(?:minimum|at\s+least|over|more\s+than)?\s*(\d+)\s*(?:\+|\s*(?:to|-)\s*\d+)?\s*(?:\+)?\s*years?'
    r'(?:\s+of(?:\s+\w+){0,3}\s+experience)?',
    re.IGNORECASE
)

def extract_min_years_required(text: str) -> Optional[int]:
    """Return the minimum years required mentioned in JD, or None if not found."""
    if not text:
        return None
    matches = _EXP_RE.findall(text)
    if not matches:
        return None
    years = [int(m) for m in matches if 1 <= int(m) <= 30]
    return min(years) if years else None


def exceeds_experience_limit(description: str) -> bool:
    """Return True if JD explicitly requires more than MAX_YEARS_EXPERIENCE years."""
    years = extract_min_years_required(description)
    if years is None:
        return False
    return years > MAX_YEARS_EXPERIENCE


# Broad list of knowledge-work title keywords — covers all tech, finance, product, design, etc.
_RELEVANT_KEYWORDS = [
    # Engineering / Tech
    "engineer", "developer", "programmer", "architect", "devops", "sre",
    "infrastructure", "platform", "backend", "frontend", "fullstack", "full-stack",
    "full stack", "cloud", "security", "embedded", "firmware",
    # Data / Analytics
    "data", "analytics", "analyst", "etl", "pipeline", "warehouse",
    "bi ", " bi", "business intelligence", "reporting",
    # AI / ML / Research
    "machine learning", "ml ", " ml", "artificial intelligence", "ai ", " ai",
    "scientist", "research", "nlp", "computer vision", "deep learning",
    "llm", "generative",
    # Product
    "product manager", "product owner", "program manager", "project manager",
    "product analyst", "product lead",
    # Design
    "designer", "ux", "ui ", " ui", "user experience", "user interface",
    "visual design", "interaction design",
    # Finance / Quant
    "quantitative", "quant", "financial", "finance", "trading", "investment",
    "risk", "portfolio", "actuarial", "credit analyst", "equity", "fixed income",
    # Operations / Strategy
    "operations", "strategy", "consultant", "business analyst",
    # Marketing / Growth
    "growth", "marketing analyst", "marketing engineer", "seo", "sem",
    # Management (tech/data)
    "engineering manager", "tech lead", "technical lead", "staff engineer",
    "principal engineer", "vp of engineering", "cto", "director of engineering",
    "head of data", "head of engineering",
]

_EXCLUDE_KEYWORDS = [
    "nurse", "physician", "doctor", "pharmacist", "therapist", "counselor",
    "teacher", "instructor", "professor", "principal",
    "chef", "cook", "barista", "server", "bartender",
    "driver", "delivery", "warehouse worker", "forklift",
    "cleaner", "janitor", "custodian",
    "electrician", "plumber", "carpenter", "mechanic",
    "sales representative", "account executive", "sales associate",
    "customer service representative", "call center",
]


def is_relevant_title(title: str) -> bool:
    t = title.lower()
    # First check hard exclusions
    for kw in _EXCLUDE_KEYWORDS:
        if kw in t:
            return False
    # Then check if any relevant keyword matches
    for kw in _RELEVANT_KEYWORDS:
        if kw in t:
            return True
    return False


def is_recent(posted_at_iso: str, hours: int = CUTOFF_HOURS) -> bool:
    if not posted_at_iso:
        return True  # assume recent if unknown
    try:
        dt = datetime.fromisoformat(posted_at_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= datetime.now(EST) - timedelta(hours=hours)
    except Exception:
        return True


@dataclass
class JobData:
    title: str
    company: str
    url: str
    source: str
    description: str = ""
    location: str = ""
    country: str = ""
    salary: str = ""
    remote: bool = False
    posted_at: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "company": self.company,
            "url": self.url,
            "source": self.source,
            "description": self.description,
            "location": self.location,
            "country": self.country,
            "salary": self.salary,
            "remote": self.remote,
            "posted_at": self.posted_at,
        }
