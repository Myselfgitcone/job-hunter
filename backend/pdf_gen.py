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
LGRAY = colors.HexColor("#1A1A1A")
FONT  = "Helvetica"
# U+2022 in the core Helvetica encoding has no ToUnicode entry, so PDF text
# extractors read it as garbage ("(cid:127)" / 0x7f). The middle dot maps
# cleanly; rendered bold and 2pt larger it looks like a normal bullet.
BULLET = "·"

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

# Page usable width: 8.5" - 0.5" left - 0.5" right = 7.5"
_USABLE_W = 7.5 * inch
_DATE_COL  = 2.1 * inch
_LEFT_COL  = _USABLE_W - _DATE_COL   # 5.0"


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """Count pages in a PDF by counting /Type /Page entries."""
    import re as _re
    return len(_re.findall(rb'/Type\s*/Page\b', pdf_bytes))


def generate_pdf(resume_text: str, job_title: str = "", company: str = "") -> bytes:
    """
    Generate a 2-page PDF when the content allows it, rebuilding with
    progressively tighter spacing (normal → compact → tight). Content that
    cannot fit 2 pages even tight ships as 3 pages at the most readable
    spacing that achieves it — a readable 3rd page beats a cramped 2nd.
    """
    first_line = resume_text.strip().split("\n")[0].strip()
    candidate_name = first_line.split("—")[0].strip() if "—" in first_line else first_line
    meta = dict(
        title=f"{candidate_name} — Resume" + (f" | {company}" if company else ""),
        author=candidate_name,
        subject=job_title or "Resume",
        creator="Job Hunter",
    )

    # Spacing tiers: (margin_inch, font_size, leading, bullet_space_after, sec_space_before)
    TIERS = [
        (0.50, 10.0, 14.0, 2.5, 9),   # Tier 1 — normal
        (0.45,  9.5, 13.0, 2.0, 7),   # Tier 2 — compact
        (0.40,  9.0, 12.5, 1.5, 5),   # Tier 3 — tight
    ]

    best_three = None
    for tier_idx, (margin, font_sz, leading, sp_after, sec_before) in enumerate(TIERS):
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=letter,
            leftMargin=margin*inch, rightMargin=margin*inch,
            topMargin=margin*inch,  bottomMargin=margin*inch,
            **meta,
        )
        doc.build(_build_story(resume_text,
                               font_size=font_sz,
                               leading=leading,
                               bullet_space_after=sp_after,
                               section_space_before=sec_before))
        pdf = buf.getvalue()
        pages = _count_pdf_pages(pdf)

        if pages <= 2:
            if tier_idx > 0:
                print(f"[PDF] Tier {tier_idx+1} spacing applied — {pages} page(s)")
            return pdf
        if pages <= 3 and best_three is None:
            best_three = (tier_idx, pdf)

    if best_three is not None:
        tier_idx, pdf = best_three
        print(f"[PDF] 3 pages at tier {tier_idx+1} spacing — content needs the room")
        return pdf

    # Fallback: return tightest version even if still >3 pages
    print("[PDF] Warning: content still >3 pages after tightest spacing")
    return pdf


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
            # Strip trailing date + separators; keep company + location all bold black
            rest = after_at[:dm.start()].strip().rstrip("|").rstrip(",").strip()
        else:
            rest = after_at.strip()
        # Entire left side bold black — Resumevar-2 style (no gray on location)
        left_html = f"<b>{_e(title_t)} @ {_e(rest)}</b>" if rest else f"<b>{_e(title_t)}</b>"

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

def _build_story(resume_text: str,
                 font_size: float = 10.0,
                 leading: float = 14.0,
                 bullet_space_after: float = 2.5,
                 section_space_before: float = 9) -> list:
    name_sty = ParagraphStyle("Name",
        fontName=FONT+"-Bold", fontSize=14, textColor=BLACK,
        alignment=TA_LEFT, leading=18, spaceAfter=1)
    contact_sty = ParagraphStyle("Contact",
        fontName=FONT, fontSize=font_size, textColor=GRAY,
        alignment=TA_LEFT, leading=leading - 1, spaceAfter=6)
    section_sty = ParagraphStyle("Section",
        fontName=FONT+"-Bold", fontSize=font_size + 1, textColor=BLACK,
        alignment=TA_LEFT, spaceBefore=section_space_before, spaceAfter=2)
    job_l_sty = ParagraphStyle("JobL",
        fontName=FONT+"-Bold", fontSize=font_size + 0.5, textColor=BLACK,
        alignment=TA_LEFT, spaceBefore=3, spaceAfter=0, leading=leading)
    job_r_sty = ParagraphStyle("JobR",
        fontName=FONT+"-Bold", fontSize=font_size + 0.5, textColor=GRAY,
        alignment=TA_RIGHT, spaceBefore=3, spaceAfter=0, leading=leading)
    bullet_sty = ParagraphStyle("Bullet",
        fontName=FONT, fontSize=font_size, textColor=BLACK,
        alignment=TA_JUSTIFY, leading=leading, spaceAfter=bullet_space_after,
        leftIndent=14, bulletIndent=2,
        bulletFontName=FONT + "-Bold", bulletFontSize=font_size + 4)
    tech_sty = ParagraphStyle("Tech",
        fontName=FONT, fontSize=font_size - 0.5, textColor=BLACK,
        alignment=TA_LEFT, spaceAfter=2, spaceBefore=2, leftIndent=0)
    body_sty = ParagraphStyle("Body",
        fontName=FONT, fontSize=font_size, textColor=BLACK,
        alignment=TA_JUSTIFY, leading=leading, spaceAfter=3)

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
            story.append(HRFlowable(width="100%", thickness=1.0,
                                    color=LGRAY, spaceAfter=3))
            continue

        # ── Education lines — plain black text, no bold/gray (matches Resumevar-2)
        if in_education:
            story.append(Paragraph(_e(s), body_sty))
            continue

        # ── Technologies Used (also catches "Stack:", "Tools:" variants) ────────
        _TECH_PREFIXES = ("Technologies Used:", "Stack:", "Tools:", "Tech Stack:",
                          "Technologies:", "Tech:", "Platform:", "Platforms:",
                          "Tools Used:", "Tech Used:")
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
            story.append(Paragraph(html, bullet_sty, bulletText=BULLET))
            continue

        # ── Skills section: plain "Label: value" lines (no bullet prefix) ───────
        if in_skills and ":" in s and not s.startswith("•"):
            label, _, value = s.partition(":")
            html = f"<b>{_e(label.strip())}:</b> {_e(value.strip())}"
            story.append(Paragraph(html, bullet_sty, bulletText=BULLET))
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
                tbl.hAlign = "LEFT"
                story.append(tbl)
            else:
                story.append(left_p)
            continue

        # ── Default body ──────────────────────────────────────────────────────
        story.append(Paragraph(_e(s), body_sty))

    return story
