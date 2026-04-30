import argparse
import io
from pathlib import Path

import fitz
from PIL import Image


PROFILES = [
    (300, 92),
    (280, 92),
    (260, 91),
    (240, 91),
    (220, 90),
    (200, 90),
    (180, 90),
]


def render_page_to_jpeg(page: fitz.Page, dpi: int, quality: int) -> bytes:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buffer.getvalue()


def image_pdf(source: Path, destination: Path, dpi: int, quality: int) -> int:
    source_doc = fitz.open(source)
    output_doc = fitz.open()
    try:
        for source_page in source_doc:
            page = output_doc.new_page(width=source_page.rect.width, height=source_page.rect.height)
            jpeg = render_page_to_jpeg(source_page, dpi, quality)
            page.insert_image(page.rect, stream=jpeg)
        destination.parent.mkdir(parents=True, exist_ok=True)
        output_doc.save(destination, garbage=4, deflate=True)
    finally:
        output_doc.close()
        source_doc.close()
    return destination.stat().st_size


def compress_pdf(source: Path, destination: Path, max_bytes: int) -> tuple[int, int, int]:
    last_size = 0
    for dpi, quality in PROFILES:
        if destination.exists():
            destination.unlink()
        size = image_pdf(source, destination, dpi, quality)
        last_size = size
        if size <= max_bytes:
            return dpi, quality, size
    raise RuntimeError(
        f"Could not compress {source} below {max_bytes / 1024 / 1024:.1f} MiB; "
        f"last attempt was {last_size / 1024 / 1024:.1f} MiB"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-mb", required=True, type=float)
    args = parser.parse_args()

    max_bytes = int(args.max_mb * 1024 * 1024)
    dpi, quality, size = compress_pdf(args.input, args.output, max_bytes)
    print(
        f"Compressed {args.input.name} -> {args.output.name}: "
        f"{size / 1024 / 1024:.1f} MiB at {dpi} dpi / JPEG quality {quality}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
