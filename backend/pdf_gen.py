"""
PDF generator matching exact formatting of Jagadish_Resume_Resume.docx reference.
  Name:    18pt  bold  NAVY  CENTER
  Title:   12pt        GRAY  CENTER
  Contact: 9.5pt       GRAY  CENTER  + NAVY rule below
  Section: 11pt  bold  NAVY         + gray rule above
  JobHdr:  10.5pt bold BLACK        spaced right-align for date
  Bullet:  9.5pt       BLACK
  Tech:    9pt  italic GRAY
  Skill:   9.5pt       BLACK  bold label + plain value
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
import io
import re

NAVY  = colors.HexColor("#1F3864")
BLACK = colors.HexColor("#1A1A1A")
GRAY  = colors.HexColor("#555555")


def generate_pdf(resume_text: str, job_title: str = "", company: str = "") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=0.55*inch, rightMargin=0.55*inch,
        topMargin=0.55*inch, bottomMargin=0.55*inch,
    )
    story = _build_story(resume_text)
    doc.build(story)
    return buffer.getvalue()


def _build_story(resume_text: str) -> list:
    # Styles
    name_style = ParagraphStyle("Name", fontName="Helvetica-Bold", fontSize=17,
                                textColor=NAVY, alignment=TA_CENTER, leading=21, spaceAfter=2)
    title_style = ParagraphStyle("Title", fontName="Helvetica", fontSize=11,
                                 textColor=GRAY, alignment=TA_CENTER, leading=14, spaceAfter=2)
    contact_style = ParagraphStyle("Contact", fontName="Helvetica", fontSize=9,
                                   textColor=GRAY, alignment=TA_CENTER, leading=12, spaceAfter=4)
    section_style = ParagraphStyle("Section", fontName="Helvetica-Bold", fontSize=10.5,
                                   textColor=NAVY, spaceBefore=7, spaceAfter=2)
    job_style = ParagraphStyle("Job", fontName="Helvetica-Bold", fontSize=10,
                               textColor=BLACK, spaceBefore=5, spaceAfter=1.5)
    jobdate_style = ParagraphStyle("JobDate", fontName="Helvetica", fontSize=10,
                                   textColor=GRAY, alignment=TA_RIGHT, spaceBefore=5, spaceAfter=1.5)
    bullet_style = ParagraphStyle("Bullet", fontName="Helvetica", fontSize=9,
                                  textColor=BLACK, leading=12, spaceAfter=1,
                                  leftIndent=14, firstLineIndent=-10)
    tech_style = ParagraphStyle("Tech", fontName="Helvetica-Oblique", fontSize=8.5,
                                textColor=GRAY, spaceAfter=2, spaceBefore=1,
                                leftIndent=10)
    body_style = ParagraphStyle("Body", fontName="Helvetica", fontSize=9,
                                textColor=BLACK, leading=12, spaceAfter=2)

    def e(t):
        return (t.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;")
                 .replace("—", "&#8212;")
                 .replace("–", "&#8211;"))

    story = []
    lines = resume_text.strip().split("\n")

    # Header
    name_line    = lines[0].strip() if lines else ""
    contact_line = lines[1].strip() if len(lines) > 1 else ""

    name_parts = name_line.split(" — ", 1)
    story.append(Paragraph(e(name_parts[0]), name_style))
    if len(name_parts) > 1:
        story.append(Paragraph(e(name_parts[1]), title_style))
    story.append(Paragraph(e(contact_line), contact_style))
    story.append(HRFlowable(width="100%", thickness=2, color=NAVY, spaceAfter=4))

    in_skills = False
    in_education = False

    for line in lines[2:]:
        line = line.rstrip()
        if not line:
            continue  # spacing handled by style spaceAfter/spaceBefore

        # Section headers
        if (line == line.upper() and len(line) > 3
                and line.endswith(":") and not line.startswith("•")):
            section_name = line.rstrip(":")
            in_skills    = "SKILL" in section_name or "TECHNICAL" in section_name
            in_education = "EDUC" in section_name
            story.append(HRFlowable(width="100%", thickness=0.5,
                                    color=colors.HexColor("#CCCCCC"), spaceAfter=2))
            story.append(Paragraph(e(section_name), section_style))
            continue

        # Education
        if in_education:
            sep = " — " if " — " in line else (" @ " if " @ " in line else None)
            if sep:
                degree, uni = line.split(sep, 1)
                html = (f'<b><font color="#1A1A1A">{e(degree.strip())}</font></b>'
                        f'<font color="#555555">   &#8212;   {e(uni.strip())}</font>')
                story.append(Paragraph(html, body_style))
            else:
                story.append(Paragraph(f'<b>{e(line)}</b>', body_style))
            continue

        # Technologies Used
        if line.startswith("Technologies Used:"):
            rest = line[len("Technologies Used:"):].strip()
            html = (f'<b><i>Technologies Used: </i></b>'
                    f'<i>{e(rest)}</i>')
            story.append(Paragraph(html, tech_style))
            continue

        # Bullets
        if line.startswith("•"):
            text = line[1:].strip()
            if in_skills and ":" in text:
                label, _, value = text.partition(":")
                html = (f'<b>{e(label.strip())}:</b> {e(value.strip())}')
                story.append(Paragraph(f"&#8226;&nbsp;&nbsp;{html}", bullet_style))
            else:
                story.append(Paragraph(f"&#8226;&nbsp;&nbsp;{e(text)}", bullet_style))
            continue

        # Job header lines  -> 2-column table: left text, right-aligned date
        if re.match(r"^.+? @ .+", line):
            date_t = ""
            if " @ " in line:
                before_at, after_at = line.split(" @ ", 1)
                title_t = e(before_at.strip())
                if " | " in after_at:
                    company_t, loc_date = after_at.split(" | ", 1)
                    date_m = re.search(
                        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}.*$)",
                        loc_date
                    )
                    if date_m:
                        location = loc_date[:date_m.start()].strip()
                        date_t   = date_m.group(1).strip()
                        left_html = (f'<b>{title_t}</b>'
                                     f' @ {e(company_t.strip())}'
                                     f'<font color="#555555">  |  {e(location)}</font>')
                    else:
                        left_html = (f'<b>{title_t}</b>'
                                     f' @ {e(after_at)}')
                else:
                    left_html = f'<b>{title_t}</b> @ {e(after_at)}'
            else:
                left_html = f'<b>{e(line)}</b>'

            left_para = Paragraph(left_html, job_style)
            if date_t:
                right_para = Paragraph(e(date_t), jobdate_style)
                tbl = Table([[left_para, right_para]],
                            colWidths=[5.0*inch, 2.4*inch])
                tbl.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]))
                story.append(tbl)
            else:
                story.append(left_para)
            continue

        # Default
        story.append(Paragraph(e(line), body_style))

    return story
