"""Links on the resume are real hyperlinks in both exports, and the contact line keeps
the city and the candidate's links (the uploaded base had them; the export used to
strip every link and the project title lines were plain body text)."""
import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import exporters_ss as x  # noqa: E402

RESUME = """JAGADISH BUTUKURI \u2014 Senior Data Engineer | AI Engineer
St. Louis, MO | (347) 695-1020 | jagadishbutukuri11@gmail.com | linkedin.com/in/jagadish33 | github.com/Myselfgitcone | jagadish-butukuri.vercel.app

PROFESSIONAL SUMMARY:
Senior Data Engineer with 5+ years on AWS and Databricks.

WORK EXPERIENCE:
Senior Data Engineer @ Cargill | Minneapolis, MN (remote) | Sep 2024 \u2013 Present
\u2022 Cut stale-data incidents 40% by building the AWS and Databricks ELT platform with Node.js services.

PROJECTS:
Footnote \u2014 RAG over SEC filings (personal, live)  \u00b7  myselfgitcone.github.io/footnote \u00b7 github.com/Myselfgitcone/footnote
\u2022 Raised answer grounding from 87% to 100% on a 29-question suite, e.g. at $0.002 per question.

EDUCATION:
M.S. Information Systems, Saint Louis University  May 2024
"""


def test_contact_keeps_links_and_drops_every_location():
    out = x._clean_contact("St. Louis, MO | (347) 695-1020 | jagadishbutukuri11@gmail.com | linkedin.com/in/jagadish33 | 12 Elm St, Apt 4")
    assert out == "(347) 695-1020 | jagadishbutukuri11@gmail.com | linkedin.com/in/jagadish33"


def test_link_regex_hits_urls_and_emails_only():
    hits = [c for c, h in x._link_spans("Node.js on St. Louis, e.g. github.com/Myselfgitcone/silo. mail a@b.co now") if h]
    assert hits == ["github.com/Myselfgitcone/silo", "a@b.co"]
    assert all(h for _, h in x._link_spans("silo-production-9efb.up.railway.app/") if h)


def test_three_line_header_with_an_all_caps_name_is_read_as_name_title_contact():
    three = RESUME.replace("JAGADISH BUTUKURI \u2014 Senior Data Engineer | AI Engineer",
                           "JAGADISH BUTUKURI\nSenior Data Engineer | AI Engineer", 1)
    name, contact, headline, _ = x._split_header(x._classify(three))
    assert name == "JAGADISH BUTUKURI"
    assert headline == "Senior Data Engineer | AI Engineer"
    assert contact.startswith("St. Louis, MO | (347)")


def test_plain_project_sentence_without_a_bullet_is_body_not_a_title():
    plain = RESUME.replace("\u2022 Raised answer grounding", "Raised answer grounding", 1)
    els = x._prune_empty(x._classify(plain))
    assert any(k == "projtitle" and t.startswith("Footnote") for k, t in els)
    assert any(k == "body" and t.startswith("Raised answer grounding") for k, t in els)


def test_project_title_is_bold_like_a_job_header():
    kinds = x._classify(RESUME)
    assert any(k == "projtitle" and t.startswith("Footnote") for k, t in kinds)
    assert any(k == "jobtitle" and t.startswith("Senior Data Engineer @ Cargill") for k, t in kinds)


def test_links_print_as_short_labels_but_keep_their_urls():
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(x.generate_pdf(RESUME)))
    text = reader.pages[0].extract_text()
    assert "(347) 695-1020 | jagadishbutukuri11@gmail.com | LinkedIn | GitHub | Portfolio" in text.replace("\n", " ")
    assert "linkedin.com/in/jagadish33" not in text and "vercel.app" not in text
    assert "Live" in text and "Code" in text and "myselfgitcone.github.io" not in text
    data = x.generate_docx(RESUME)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        doc = z.read("word/document.xml").decode("utf-8")
    assert ">LinkedIn<" in doc and ">Portfolio<" in doc and ">Code<" in doc and ">Live<" in doc


def test_pdf_has_clickable_links():
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(x.generate_pdf(RESUME)))
    uris = set()
    for page in reader.pages:
        for a in page.get("/Annots") or []:
            obj = a.get_object()
            if "/A" in obj and "/URI" in obj["/A"]:
                uris.add(str(obj["/A"]["/URI"]))
    assert "https://linkedin.com/in/jagadish33" in uris
    assert "https://jagadish-butukuri.vercel.app" in uris
    assert "https://github.com/Myselfgitcone/footnote" in uris
    assert "mailto:jagadishbutukuri11@gmail.com" in uris
    assert not any("Node.js" in u for u in uris)


def test_docx_has_real_hyperlinks():
    data = x.generate_docx(RESUME)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        doc = z.read("word/document.xml").decode("utf-8")
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
    assert doc.count("<w:hyperlink") >= 6
    assert "https://myselfgitcone.github.io/footnote" in rels
    assert "https://jagadish-butukuri.vercel.app" in rels
    assert "St. Louis, MO" not in doc
