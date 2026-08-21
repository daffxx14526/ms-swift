#!/usr/bin/env python3
"""Convert Markdown annotation docs to Word (.docx)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import markdown
from bs4 import BeautifulSoup, NavigableString, Tag
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor


def set_run_font(run, *, bold=False, italic=False, code=False, size=11):
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    run.font.name = "Consolas" if code else "Microsoft YaHei"
    r = run._element
    rPr = r.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    if code:
        rFonts.set(qn("w:ascii"), "Consolas")
        rFonts.set(qn("w:hAnsi"), "Consolas")
        rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    else:
        rFonts.set(qn("w:ascii"), "Calibri")
        rFonts.set(qn("w:hAnsi"), "Calibri")
        rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")


def add_inline(paragraph, node):
    if isinstance(node, NavigableString):
        text = str(node)
        if text:
            run = paragraph.add_run(text)
            set_run_font(run)
        return
    if not isinstance(node, Tag):
        return
    name = node.name.lower()
    if name in ("strong", "b"):
        run = paragraph.add_run(node.get_text())
        set_run_font(run, bold=True)
    elif name in ("em", "i"):
        run = paragraph.add_run(node.get_text())
        set_run_font(run, italic=True)
    elif name == "code":
        run = paragraph.add_run(node.get_text())
        set_run_font(run, code=True, size=10)
        run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    elif name == "a":
        run = paragraph.add_run(node.get_text())
        set_run_font(run)
        run.font.color.rgb = RGBColor(0x05, 0x63, 0xC1)
    elif name == "br":
        paragraph.add_run().add_break()
    else:
        for child in node.children:
            add_inline(paragraph, child)


def add_paragraph_from_tag(doc, tag, style=None):
    p = doc.add_paragraph(style=style)
    for child in tag.children:
        add_inline(p, child)
    for run in p.runs:
        if run.font.size is None:
            set_run_font(run)
    return p


def add_code_block(doc, text):
    for line in text.splitlines() or [""]:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.left_indent = Pt(12)
        run = p.add_run(line if line else " ")
        set_run_font(run, code=True, size=9)
        run.font.color.rgb = RGBColor(0x22, 0x22, 0x22)


def add_table(doc, table_tag):
    rows = table_tag.find_all("tr")
    if not rows:
        return
    cols = max(len(r.find_all(["th", "td"])) for r in rows)
    table = doc.add_table(rows=len(rows), cols=cols)
    table.style = "Table Grid"
    for i, tr in enumerate(rows):
        cells = tr.find_all(["th", "td"])
        for j in range(cols):
            cell = table.cell(i, j)
            cell.text = ""
            p = cell.paragraphs[0]
            if j < len(cells):
                for child in cells[j].children:
                    add_inline(p, child)
                if cells[j].name == "th":
                    for run in p.runs:
                        run.bold = True


def convert_md_to_docx(md_path: Path, docx_path: Path):
    md_text = md_path.read_text(encoding="utf-8")
    # strip HTML comments-like blockquotes keep as-is
    html = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
    )
    soup = BeautifulSoup(html, "html.parser")
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Microsoft YaHei"
    style.font.size = Pt(11)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(md_path.stem)
    set_run_font(run, bold=True, size=18)

    for el in soup.children:
        if isinstance(el, NavigableString):
            continue
        if not isinstance(el, Tag):
            continue
        name = el.name.lower()
        if name == "h1":
            p = doc.add_heading(el.get_text().strip(), level=1)
        elif name == "h2":
            doc.add_heading(el.get_text().strip(), level=2)
        elif name == "h3":
            doc.add_heading(el.get_text().strip(), level=3)
        elif name == "h4":
            doc.add_heading(el.get_text().strip(), level=4)
        elif name == "p":
            add_paragraph_from_tag(doc, el)
        elif name in ("ul", "ol"):
            for li in el.find_all("li", recursive=False):
                style_name = "List Number" if name == "ol" else "List Bullet"
                try:
                    add_paragraph_from_tag(doc, li, style=style_name)
                except KeyError:
                    p = add_paragraph_from_tag(doc, li)
                    prefix = "- " if name == "ul" else "• "
                    if p.runs:
                        p.runs[0].text = prefix + p.runs[0].text
        elif name == "pre":
            code = el.get_text()
            add_code_block(doc, code.rstrip("\n"))
        elif name == "table":
            add_table(doc, el)
            doc.add_paragraph()
        elif name == "hr":
            p = doc.add_paragraph("—" * 20)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif name == "blockquote":
            p = add_paragraph_from_tag(doc, el)
            for run in p.runs:
                run.italic = True
                run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
        else:
            # fallback: flatten text
            text = el.get_text().strip()
            if text:
                p = doc.add_paragraph()
                run = p.add_run(text)
                set_run_font(run)

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(docx_path))
    print(f"Wrote {docx_path}")


def main():
    root = Path("/workspace")
    files = [
        "accident_annotation_spec_video.md",
        "accident_annotation_spec_image.md",
        "accident_annotation_spec_video_core.md",
        "accident_annotation_spec_image_core.md",
        "accident_annotation_criteria.md",
        "accident_detection_training_plan.md",
        "accident_model_pipeline_design.md",
    ]
    out_dir = root / "docs_word"
    for name in files:
        src = root / name
        if not src.exists():
            print(f"skip missing {src}", file=sys.stderr)
            continue
        convert_md_to_docx(src, out_dir / (src.stem + ".docx"))


if __name__ == "__main__":
    main()
