"""Turn a base resume (.docx) into the plain text the tailoring engine reads, EXACTLY the way the
app's own upload endpoint does it, so a regression run grades the engine on what the app would
really have been given.

    python tools/base_from_docx.py "<base.docx>" <out.txt>

The block walk below mirrors main.py's /resume upload handler: many resume templates keep job
titles and dates inside one-row TABLES, and reading only `doc.paragraphs` silently drops every
employer and date (the user's own base is such a file).
"""
import sys

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


def _iter_blocks(parent):
    for child in parent.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def docx_to_text(path: str) -> str:
    doc = Document(path)
    lines: list[str] = []
    for block in _iter_blocks(doc):
        if isinstance(block, Paragraph):
            t = block.text.strip()
            if t:
                lines.append(t)
        else:                                   # keep a row's cells together: date stays with its title
            for row in block.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                seen, uniq = set(), []
                for c in cells:
                    if c not in seen:
                        seen.add(c)
                        uniq.append(c)
                if uniq:
                    lines.append("   ".join(uniq))
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    text = docx_to_text(sys.argv[1])
    open(sys.argv[2], "w", encoding="utf-8").write(text + "\n")

    # report what the engine will be able to see in it
    sys.path.insert(0, __file__.rsplit("tools", 1)[0])
    from ai import tailor as t  # noqa: E402
    jobs = t._job_bodies(text)
    figs = sorted(f for f in t._num_tokens(text) if not f.endswith("y"))
    print(f"wrote {sys.argv[2]}: {len(text.split())} words")
    print(f"employers the engine can see: {[c for c, _ in jobs] or 'NONE — the headers did not survive'}")
    print(f"figures in the base ({len(figs)}): {figs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
