"""Convert a PDF into a PowerPoint where each slide is a full-bleed render of the
corresponding PDF page. Preserves every visual element by rasterizing pages at
high DPI rather than trying to translate vector content into PPTX shapes.

Usage:
    python pdf_to_pptx.py INPUT_PDF [INPUT_PDF ...] [--out-dir DIR] [--dpi 300]

Dependencies (install in your active Python environment):
    pip install pymupdf python-pptx Pillow
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image
from pptx import Presentation
from pptx.util import Emu


PT_PER_INCH = 72.0
EMU_PER_INCH = 914400


def convert(pdf_path: Path, pptx_path: Path, dpi: int) -> None:
    doc = fitz.open(str(pdf_path))
    if doc.page_count == 0:
        raise ValueError(f"{pdf_path} has no pages")

    prs = Presentation()
    blank_layout = prs.slide_layouts[6]

    # Use the first page's size to define slide dimensions; fall back to per-slide
    # sizing only if pages differ. PowerPoint has a single slide size per deck, so
    # if pages differ we use the largest page and letterbox the rest.
    widths_pt = [page.rect.width for page in doc]
    heights_pt = [page.rect.height for page in doc]
    deck_w_pt = max(widths_pt)
    deck_h_pt = max(heights_pt)

    prs.slide_width = Emu(int(round(deck_w_pt / PT_PER_INCH * EMU_PER_INCH)))
    prs.slide_height = Emu(int(round(deck_h_pt / PT_PER_INCH * EMU_PER_INCH)))

    zoom = dpi / PT_PER_INCH
    matrix = fitz.Matrix(zoom, zoom)

    for index, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)

        slide = prs.slides.add_slide(blank_layout)

        page_w_emu = int(round(page.rect.width / PT_PER_INCH * EMU_PER_INCH))
        page_h_emu = int(round(page.rect.height / PT_PER_INCH * EMU_PER_INCH))
        left = (prs.slide_width - page_w_emu) // 2
        top = (prs.slide_height - page_h_emu) // 2

        slide.shapes.add_picture(
            buffer,
            left=Emu(left),
            top=Emu(top),
            width=Emu(page_w_emu),
            height=Emu(page_h_emu),
        )

        print(f"  page {index}/{doc.page_count} rendered", file=sys.stderr)

    pptx_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(pptx_path))
    doc.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="+", help="One or more input PDF paths")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for the .pptx files (defaults to each PDF's own folder)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Render DPI; raise for sharper output, lower for smaller files (default 300)",
    )
    args = parser.parse_args()

    for raw in args.inputs:
        pdf_path = Path(raw)
        if not pdf_path.is_file():
            print(f"skip: {pdf_path} not found", file=sys.stderr)
            continue
        out_dir = args.out_dir if args.out_dir is not None else pdf_path.parent
        pptx_path = out_dir / (pdf_path.stem + ".pptx")
        print(f"converting {pdf_path.name} -> {pptx_path}", file=sys.stderr)
        convert(pdf_path, pptx_path, args.dpi)
        print(f"wrote {pptx_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
