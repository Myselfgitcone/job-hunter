"""
pdf_gen.py — Resumevar-2 style formatting.
  Header:   "Name — Title" on ONE line, bold black, left-aligned
  Contact:  9.5pt gray, left-aligned
  Section:  11pt bold black + thin gray rule BELOW
  JobHdr:   left bold "Title @ Company | Location", right bold gray date (2-col)
  Bullet:   9.5pt black, justified, hanging indent
  Tech:     9pt, "Technologies Used:" bold + plain text
  Skill:    bullet with bold label + plain value
  Body:     9.5pt black justified

Job header formats handled:
  "Title @ Company | Location, ST  Date"   (Resumevar-2 native)
  "Title | Company | Date"                  (tailor.py output)
  "Title | Company | Location | Date"       (tailor.py with location)
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                HRFlowable, Table, TableStyle)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_JUSTIFY
import io, re

BLACK = colors.HexColor("#1A1A1A")
GRAY  = colors.HexColor("#555555")
LGRAY = colors.HexColor("#999999")
FONT  = "Helvetica"

# Matches date ranges like "Sep 2023 — Present", "Jan 2021 – Jul 2022", "Dec 2018 - Dec 2020"
_DATE_RE = re.compile(
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}"
    r"(?:\s*[—–\-]+\s*"
    r"(?:Present|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}))?)",
    re.IGNORECASE,
)

# Well-known section names accepted even without trailing colon
_KNOWN_SECTIONS = {
    "PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "TECHNICAL SKILLS",
    "EDUCATION", "SKILLS", "CERTIFICATIONS", "PROJECTS", "SUMMARY",
}

# Page usable width: 8.5" - 0.7" left - 0.7" right = 7.1"
_USABLE_W = 7.1 * inch
_DATE_COL  = 2.1 * inch
_LEFT_COL  = _USABLE_W - _DATE_COL   # 5.0"


def generate_pdf(resume_text: str, job_title: str = "", company: str = "") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.7*inch, rightMargin=0.7*inch,
        topMargin=0.6*inch,  bottomMargin=0.6*inch,
    )
    doc.build(_build_story(resume_text))
    return buf.getvalue()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _e(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace("—", "&#8212;").replace("–", "&#8211;"))


def _is_section_header(s: str) -> bool:
    s = s.strip()
    if not s or s.startswith("•"):
        return False
    clean = s.rstrip(":")
    return (clean == clean.upper() and len(clean) > 3
            and (s.endswith(":") or clean in _KNOWN_SECTIONS))


def _is_job_header(s: str) -> bool:
    s = s.strip()
    if not s or s.startswith("•"):
        return False
    # Format 1: "Title @ Company ..."
    if re.match(r"^.+? @ .+", s):
        return True
    # Format 2: "Title | Company | Date..." (pipe-separated, date in last segment)
    parts = [p.strip() for p in s.split(" | ")]
    if len(parts) >= 2 and _DATE_RE.search(parts[-1]):
        return True
    return False


def _parse_job_header(s: str):
    """Return (left_html, date_str). left_html uses bold markup."""
    s = s.strip()
    date_t = ""

    if " @ " in s:
        # "Title @ Company | Location, ST  Date" or "Title @ Company | Date"
        before_at, after_at = s.split(" @ ", 1)
        title_t = before_at.strip()
        dm = _DATE_RE.search(after_at)
        if dm:
            date_t = dm.group(1).strip()
            rest = after_at[:dm.start()].strip().rstrip("|").rstrip(",").strip()
        else:
            rest = after_at.strip()
        if rest:
            left_html = f"<b>{_e(title_t)} @ {_e(rest)}</b>"
        else:
            left_html = f"<b>{_e(title_t)}</b>"

    else:
        # "Title | Company | Date" or "Title | Company | Location | Date"
        parts = [p.strip() for p in s.split(" | ")]
        dm = _DATE_RE.search(parts[-1]) if parts else None
        if dm and len(parts) >= 2:
            date_t = dm.group(1).strip()
            # middle = everything between title and date
            if len(parts) >= 3:
                middle = " | ".join(parts[1:-1])
                left_html = f"<b>{_e(parts[0])} @ {_e(middle)}</b>"
            else:
                left_html = f"<b>{_e(parts[0])}</b>"
        else:
            left_html = f"<b>{_e(s)}</b>"

    return left_html, date_t


# ── Story builder ─────────────────────────────────────────────────────────────

def _build_story(resume_text: str) -> list:
    name_sty = ParagraphStyle("Name",
        fontName=FONT+"-Bold", fontSize=13.5, textColor=BLACK,
        alignment=TA_LEFT, leading=17, spaceAfter=1)
    contact_sty = ParagraphStyle("Contact",
        fontName=FONT, fontSize=9.5, textColor=GRAY,
        alignment=TA_LEFT, leading=13, spaceAfter=8)
    section_sty = ParagraphStyle("Section",
        fontName=FONT+"-Bold", fontSize=11, textColor=BLACK,
        alignment=TA_LEFT, spaceBefore=9, spaceAfter=2)
    job_l_sty = ParagraphStyle("JobL",
        fontName=FONT+"-Bold", fontSize=10, textColor=BLACK,
        alignment=TA_LEFT, spaceBefore=6, spaceAfter=0, leading=13)
    job_r_sty = ParagraphStyle("JobR",
        fontName=FONT+"-Bold", fontSize=10, textColor=GRAY,
        alignment=TA_RIGHT, spaceBefore=6, spaceAfter=0, leading=13)
    bullet_sty = ParagraphStyle("Bullet",
        fontName=FONT, fontSize=9.5, textColor=BLACK,
        alignment=TA_JUSTIFY, leading=13, spaceAfter=2.5,
        leftIndent=16, firstLineIndent=-12)
    tech_sty = ParagraphStyle("Tech",
        fontName=FONT, fontSize=9, textColor=BLACK,
        alignment=TA_LEFT, spaceAfter=3, spaceBefore=2, leftIndent=10)
    body_sty = ParagraphStyle("Body",
        fontName=FONT, fontSize=9.5, textColor=BLACK,
        alignment=TA_JUSTIFY, leading=13, spaceAfter=3)

    _tbl_style = TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ])

    story = []
    lines = resume_text.strip().split("\n")

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph(_e(lines[0].strip() if lines else ""), name_sty))
    story.append(Paragraph(_e(lines[1].strip() if len(lines) > 1 else ""), contact_sty))

    in_skills    = False
    in_education = False

    for raw in lines[2:]:
        line = raw.rstrip()
        s    = line.strip()
        if not s:
            continue

        # ── Section header ────────────────────────────────────────────────────
        if _is_section_header(s):
            clean        = s.rstrip(":")
            in_skills    = "SKILL" in clean or "TECHNICAL" in clean
            in_education = "EDUC" in clean
            # Keep colon in display to match Resumevar-2 style
            display = clean + ":"
            story.append(Paragraph(_e(display), section_sty))
            story.append(HRFlowable(width="100%", thickness=0.75,
                                    color=LGRAY, spaceAfter=4))
            continue

        # ── Education lines ───────────────────────────────────────────────────
        if in_education:
            # Don't treat as job header even if line has "@" or "|"
            sep = (" — " if " — " in s
                   else (" @ " if " @ " in s
                   else (" | " if " | " in s else None)))
            if sep:
                parts = s.split(sep, 1)
                html = (f'<b>{_e(parts[0].strip())}</b>'
                        f'<font color="#555555">{_e(sep)}{_e(parts[1].strip())}</font>')
            else:
                html = f"<b>{_e(s)}</b>"
            story.append(Paragraph(html, body_sty))
            continue

        # ── Technologies Used (also catches "Stack:", "Tools:" variants) ────────
        _TECH_PREFIXES = ("Technologies Used:", "Stack:", "Tools:", "Tech Stack:",
                          "Technologies:", "Tech:")
        _tech_match = next((p for p in _TECH_PREFIXES if s.startswith(p)), None)
        if _tech_match:
            rest = s[len(_tech_match):].strip()
            story.append(Paragraph(f"<b>Technologies Used:</b> {_e(rest)}", tech_sty))
            continue

        # ── Bullets ───────────────────────────────────────────────────────────
        if s.startswith("•"):
            text = s[1:].strip()
            if in_skills and ":" in text:
                label, _, value = text.partition(":")
                html = f"<b>{_e(label.strip())}:</b> {_e(value.strip())}"
            else:
                html = _e(text)
            story.append(Paragraph(f"&#8226;&nbsp;&nbsp;{html}", bullet_sty))
            continue

        # ── Skills section: plain "Label: value" lines (no bullet prefix) ───────
        if in_skills and ":" in s and not s.startswith("•"):
            label, _, value = s.partition(":")
            html = f"<b>{_e(label.strip())}:</b> {_e(value.strip())}"
            story.append(Paragraph(f"&#8226;&nbsp;&nbsp;{html}", bullet_sty))
            continue

        # ── Job header ────────────────────────────────────────────────────────
        if _is_job_header(s):
            left_html, date_t = _parse_job_header(s)
            left_p = Paragraph(left_html, job_l_sty)
            if date_t:
                right_p = Paragraph(f"<b>{_e(date_t)}</b>", job_r_sty)
                tbl = Table([[left_p, right_p]],
                            colWidths=[_LEFT_COL, _DATE_COL])
                tbl.setStyle(_tbl_style)
                story.append(tbl)
            else:
                story.append(left_p)
            continue

        # ── Default body ──────────────────────────────────────────────────────
        story.append(Paragraph(_e(s), body_sty))

    return story
