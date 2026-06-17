"""
pdf_gen.py — Resumevar-style formatting.
  Header:   Name — Title on ONE line, 14pt bold black, left-aligned
  Contact:  10pt gray, left-aligned
  Section:  11pt bold black + thin gray rule UNDERNEATH
  JobHdr:   10.5pt bold black left + bold gray date right (2-col table)
  Bullet:   9.5pt black, justified, hanging indent
  Tech:     9pt, "Technologies Used:" bold black + plain black (NOT italic)
  Skill:    9.5pt bold label + plain value
  Body:     9.5pt black justified
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
LGRAY = colors.HexColor("#AAAAAA")   # thin rule color
FONT  = "Helvetica"


def generate_pdf(resume_text: str, job_title: str = "", company: str = "") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=0.7*inch, rightMargin=0.7*inch,
        topMargin=0.6*inch,  bottomMargin=0.6*inch,
    )
    doc.build(_build_story(resume_text))
    return buffer.getvalue()


def _build_story(resume_text: str) -> list:
    # ── Styles ────────────────────────────────────────────────────────────────
    name_style = ParagraphStyle("Name",
        fontName=FONT+"-Bold", fontSize=13.5, textColor=BLACK,
        alignment=TA_LEFT, leading=17, spaceAfter=1)
    contact_style = ParagraphStyle("Contact",
        fontName=FONT, fontSize=9.5, textColor=GRAY,
        alignment=TA_LEFT, leading=13, spaceAfter=8)
    section_style = ParagraphStyle("Section",
        fontName=FONT+"-Bold", fontSize=11, textColor=BLACK,
        alignment=TA_LEFT, spaceBefore=9, spaceAfter=2)
    job_left_style = ParagraphStyle("JobL",
        fontName=FONT+"-Bold", fontSize=10, textColor=BLACK,
        alignment=TA_LEFT, spaceBefore=6, spaceAfter=0, leading=13)
    job_right_style = ParagraphStyle("JobR",
        fontName=FONT+"-Bold", fontSize=10, textColor=GRAY,
        alignment=TA_RIGHT, spaceBefore=6, spaceAfter=0, leading=13)
    bullet_style = ParagraphStyle("Bullet",
        fontName=FONT, fontSize=9.5, textColor=BLACK,
        alignment=TA_JUSTIFY, leading=13, spaceAfter=2.5,
        leftIndent=16, firstLineIndent=-12)
    tech_style = ParagraphStyle("Tech",
        fontName=FONT, fontSize=9, textColor=BLACK,
        alignment=TA_LEFT, spaceAfter=3, spaceBefore=2, leftIndent=10)
    body_style = ParagraphStyle("Body",
        fontName=FONT, fontSize=9.5, textColor=BLACK,
        alignment=TA_JUSTIFY, leading=13, spaceAfter=3)

    def e(t):
        return (t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                 .replace("—","&#8212;").replace("–","&#8211;"))

    story = []
    lines = resume_text.strip().split("\n")

    # ── Header: Name — Title on one line, contact on next ────────────────────
    name_line    = lines[0].strip() if lines else ""
    contact_line = lines[1].strip() if len(lines) > 1 else ""
    story.append(Paragraph(e(name_line), name_style))
    story.append(Paragraph(e(contact_line), contact_style))

    in_skills   = False
    in_education = False

    for line in lines[2:]:
        line = line.rstrip()
        if not line:
            continue

        # ── Section header ────────────────────────────────────────────────────
        if (line.strip() == line.strip().upper() and len(line.strip()) > 3
                and line.strip().endswith(":") and not line.strip().startswith("•")):
            section_name = line.strip().rstrip(":")
            in_skills    = "SKILL" in section_name or "TECHNICAL" in section_name
            in_education = "EDUC"  in section_name
            story.append(Paragraph(e(section_name), section_style))
            story.append(HRFlowable(width="100%", thickness=0.5,
                                    color=LGRAY, spaceAfter=4))
            continue

        # ── Education ─────────────────────────────────────────────────────────
        if in_education:
            sep = " — " if " — " in line else (" @ " if " @ " in line
                  else (" | " if " | " in line else None))
            if sep:
                parts = line.split(sep, 1)
                html = (f'<b>{e(parts[0].strip())}</b>'
                        f'<font color="#555555">{e(sep)}{e(parts[1].strip())}</font>')
            else:
                html = f'<b>{e(line.strip())}</b>'
            story.append(Paragraph(html, body_style))
            continue

        # ── Technologies Used ─────────────────────────────────────────────────
        if line.strip().startswith("Technologies Used:"):
            rest = line.strip()[len("Technologies Used:"):].strip()
            html = f'<b>Technologies Used:</b> {e(rest)}'
            story.append(Paragraph(html, tech_style))
            continue

        # ── Bullets ───────────────────────────────────────────────────────────
        if line.strip().startswith("•"):
            text = line.strip()[1:].strip()
            if in_skills and ":" in text:
                label, _, value = text.partition(":")
                html = f'<b>{e(label.strip())}:</b> {e(value.strip())}'
            else:
                html = e(text)
            story.append(Paragraph(f"&#8226;&nbsp;&nbsp;{html}", bullet_style))
            continue

        # ── Job header: 2-col table, left=title/co/loc, right=date ───────────
        if re.match(r"^.+? @ .+", line.strip()):
            before_at, after_at = line.strip().split(" @ ", 1)
            title_t = e(before_at.strip())
            date_t  = ""
            if " | " in after_at:
                company_t, loc_date = after_at.split(" | ", 1)
                date_m = re.search(
                    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
                    r"\s+\d{4}.*$)", loc_date)
                if date_m:
                    location = loc_date[:date_m.start()].strip()
                    date_t   = date_m.group(1).strip()
                    left_html = (f'<b>{title_t} @ {e(company_t.strip())}'
                                 f'</b>  <font color="#555555">| {e(location)}</font>')
                else:
                    left_html = f'<b>{title_t} @ {e(after_at)}</b>'
            else:
                left_html = f'<b>{title_t} @ {e(after_at)}</b>'

            left_p  = Paragraph(left_html, job_left_style)
            if date_t:
                right_p = Paragraph(f'<b>{e(date_t)}</b>', job_right_style)
                tbl = Table([[left_p, right_p]], colWidths=[4.8*inch, 2.6*inch])
                tbl.setStyle(TableStyle([
                    ("VALIGN",       (0,0),(-1,-1),"BOTTOM"),
                    ("LEFTPADDING",  (0,0),(-1,-1),0),
                    ("RIGHTPADDING", (0,0),(-1,-1),0),
                    ("TOPPADDING",   (0,0),(-1,-1),0),
                    ("BOTTOMPADDING",(0,0),(-1,-1),0),
                ]))
                story.append(tbl)
            else:
                story.append(left_p)
            continue

        # ── Default body ──────────────────────────────────────────────────────
        story.append(Paragraph(e(line.strip()), body_style))

    return story