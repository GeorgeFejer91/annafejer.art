import argparse
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    import fitz
except Exception as exc:
    fitz = None
    FITZ_IMPORT_ERROR = exc
else:
    FITZ_IMPORT_ERROR = None

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


def render_page_to_jpeg(page, dpi: int, quality: int) -> bytes:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buffer.getvalue()


def save_multipage_pdf(image_paths: list[Path], destination: Path, dpi: int) -> int:
    images = []
    try:
        for image_path in image_paths:
            with Image.open(image_path) as image:
                images.append(image.convert("RGB"))
        if not images:
            raise RuntimeError("No rendered page images were produced")
        destination.parent.mkdir(parents=True, exist_ok=True)
        first, *rest = images
        first.save(destination, format="PDF", save_all=True, append_images=rest, resolution=dpi)
    finally:
        for image in images:
            image.close()
    return destination.stat().st_size


def image_pdf_via_pdftoppm(source: Path, destination: Path, dpi: int, quality: int) -> int:
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise RuntimeError(
            "PyMuPDF is unavailable and pdftoppm was not found on PATH"
            if FITZ_IMPORT_ERROR is None
            else f"PyMuPDF is unavailable ({FITZ_IMPORT_ERROR}) and pdftoppm was not found on PATH"
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        prefix = Path(temp_dir) / "page"
        command = [
            pdftoppm,
            "-jpeg",
            "-r",
            str(dpi),
            "-jpegopt",
            f"quality={quality},progressive=y,optimize=y",
            str(source),
            str(prefix),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "pdftoppm failed to render the PDF")

        image_paths = sorted(Path(temp_dir).glob("page-*.jpg"))
        if not image_paths:
            single_file = Path(temp_dir) / "page.jpg"
            if single_file.exists():
                image_paths = [single_file]
        return save_multipage_pdf(image_paths, destination, dpi)


def image_pdf(source: Path, destination: Path, dpi: int, quality: int) -> int:
    if fitz is None:
        return image_pdf_via_pdftoppm(source, destination, dpi, quality)

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
