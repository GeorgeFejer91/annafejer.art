from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image


Image.MAX_IMAGE_PIXELS = None

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
CANONICAL_TEX_POINTER = "portfolio_current.tex"
DEFAULT_TEX_FILE = "portfolio_from_ppt_images_a4.tex"
TEX_FILES = [CANONICAL_TEX_POINTER]
CATALOGUE_POLICY = {
    "version": 1,
    "source_of_truth": {
        "work_order": "The numbered folders portfolio_compiled_works_metadata/Work 1, Work 2, ... define the permanent portfolio order.",
        "metadata": "Each Work N/Meta.txt file is the human-editable metadata source for that work.",
        "images": "Image files inside each Work N folder are the authoritative source images for that work.",
    },
    "ordering_rule": "Sort work folders by their numeric suffix in ascending order. Do not infer portfolio order from TeX order, file timestamps, or filenames outside the Work folders.",
    "image_naming_rule": "On every catalogue refresh, artwork images are renamed to work-XX-title-slug-YY.ext, where XX is the zero-padded Work folder number and YY is the image sequence within that folder.",
    "tex_rule": "The LaTeX inventory is generated from the Work folder catalogue and should not be treated as the source of truth.",
}
OUTPUTS = [
    {
        "key": "a4",
        "pdf": "Output/Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent.pdf",
        "pages_dir": "Output/pages/Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent",
        "page_prefix": "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent",
    },
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def json_load(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def work_number(folder: Path) -> int:
    match = re.search(r"\d+", folder.name)
    if not match:
        raise ValueError(f"Cannot parse work number from {folder}")
    return int(match.group())


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def slugify(value: str) -> str:
    text = value.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "work"


def clean_meta_value(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"(?<=\d)(cm|mm|m)\b", r" \1", value)
    value = re.sub(r"(?<=\d)\s*x\s*(?=\d)", " x ", value)
    value = re.sub(r"(?<=m)\s*x\s*(?=\d)", " x ", value)
    value = value.replace("Fishing-line", "Fishing line")
    value = value.replace("fishing-line", "fishing line")
    return value.strip()


def parse_meta_txt(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    key_map = {
        "title": "title",
        "year of creation": "year",
        "year": "year",
        "materials": "materials",
        "format": "format",
        "size": "size",
        "location": "location",
    }
    stop_prefixes = (
        "Portfolio content pages:",
        "Images used by LaTeX:",
        "Raw Meta.docx text:",
    )
    meta: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(line.startswith(prefix) for prefix in stop_prefixes):
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip().lower()
        field = key_map.get(normalized_key)
        if field:
            value = clean_meta_value(value)
            if value.lower() in {"(blank)", "blank", "none", "n/a"}:
                value = ""
            meta[field] = value
    return meta


def canonical_image_path(folder: Path, work_num: int, title: str, sequence: int, suffix: str) -> Path:
    slug = slugify(title or f"Work {work_num}")
    return folder / f"work-{work_num:02d}-{slug}-{sequence:02d}{suffix.lower()}"


def canonical_tex_filename(catalog: list[dict[str, Any]]) -> str:
    if not catalog:
        return DEFAULT_TEX_FILE
    first = min(int(work["work_number"]) for work in catalog)
    last = max(int(work["work_number"]) for work in catalog)
    count = len(catalog)
    signature = "-".join(
        f"{int(work['work_number']):02d}-{slugify(work['title'])}"
        for work in catalog
    )
    compact_signature = re.sub(r"[^a-z0-9]+", "-", signature).strip("-")
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:10]
    if len(compact_signature) > 120:
        compact_signature = compact_signature[:120].rstrip("-")
    return f"portfolio_a4_work-{first:02d}-to-{last:02d}_{count}-works_{digest}_{compact_signature}.tex"


def canonicalize_work_images(folder: Path, work_num: int, title: str, root: Path) -> list[dict[str, Any]]:
    image_paths = sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    rows: list[dict[str, Any]] = []
    for sequence, path in enumerate(image_paths, start=1):
        target = canonical_image_path(folder, work_num, title, sequence, path.suffix)
        old_rel = rel(path, root)
        if path.name != target.name:
            if target.exists():
                raise RuntimeError(f"Cannot rename {old_rel}: target already exists: {rel(target, root)}")
            path.rename(target)
            rows.append(
                {
                    "work": f"Work {work_num}",
                    "old_path": old_rel,
                    "new_path": rel(target, root),
                    "renamed": True,
                }
            )
        else:
            rows.append(
                {
                    "work": f"Work {work_num}",
                    "old_path": old_rel,
                    "new_path": old_rel,
                    "renamed": False,
                }
            )
    return rows


def rewrite_tex_image_paths(root: Path, rename_rows: list[dict[str, Any]]) -> None:
    replacements = {
        row["old_path"]: row["new_path"]
        for row in rename_rows
        if row.get("renamed") and row.get("old_path") and row.get("new_path")
    }
    if not replacements:
        return
    for path in root.glob("portfolio*.tex"):
        text = path.read_text(encoding="utf-8")
        updated = text
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        refs = re.findall(
            r"portfolio_compiled_works_metadata/Work (\d+)/[^{}]+?-(\d+)\.(png|jpg|jpeg|tif|tiff)",
            updated,
            re.IGNORECASE,
        )
        for work_num, sequence, ext in refs:
            old_match = re.search(
                rf"portfolio_compiled_works_metadata/Work {work_num}/[^{{}}]+-{sequence}\.{ext}",
                updated,
                re.IGNORECASE,
            )
            if not old_match:
                continue
            old_ref = old_match.group(0)
            if (root / old_ref).exists():
                continue
            candidates = sorted((root / f"portfolio_compiled_works_metadata/Work {work_num}").glob(f"*-{sequence}.{ext.lower()}"))
            if candidates:
                updated = updated.replace(old_ref, rel(candidates[0], root))
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def image_info(path: Path, root: Path, sequence: int, existing: dict[str, Any], total: int) -> dict[str, Any]:
    with Image.open(path) as image:
        dpi = image.info.get("dpi") or [None, None]
        width, height = image.width, image.height
        mode = image.mode

    work_page = existing.get("work_page")
    page_role = existing.get("page_role")
    if work_page is None:
        if total == 3 and sequence == 1:
            work_page = 1
            page_role = "hero image"
        elif total == 3:
            work_page = 2
            page_role = f"equal-height spread image {sequence - 1}"
        elif total == 2:
            work_page = 1
            page_role = f"equal-height spread image {sequence}"
        else:
            work_page = sequence
            page_role = "single image" if total == 1 else f"image {sequence}"
    if not page_role:
        page_role = "single image" if total == 1 else f"image {sequence}"

    return {
        "filename": path.name,
        "relative_path": rel(path, root),
        "width_px": width,
        "height_px": height,
        "aspect_ratio": round(width / height, 6),
        "mode": mode,
        "dpi": list(dpi),
        "file_size_bytes": path.stat().st_size,
        "sequence": sequence,
        "work_page": int(work_page),
        "page_role": page_role,
    }


def normalize_catalog(root: Path) -> list[dict[str, Any]]:
    metadata_root = root / "portfolio_compiled_works_metadata"
    catalog_path = metadata_root / "catalog.json"
    existing_catalog = json_load(catalog_path, [])
    catalog_by_number = {int(work["work_number"]): work for work in existing_catalog}
    normalized: list[dict[str, Any]] = []
    filename_rows: list[dict[str, Any]] = []

    folders = sorted(metadata_root.glob("Work *"), key=work_number)
    content_page = 1
    for folder in folders:
        number = work_number(folder)
        work_json = json_load(folder / "work.json", {})
        meta_txt = parse_meta_txt(folder / "Meta.txt")
        base = {**catalog_by_number.get(number, {}), **work_json, **meta_txt}
        title = base.get("title") or f"Work {number}"
        filename_rows.extend(canonicalize_work_images(folder, number, title, root))
        existing_images = {image.get("filename"): image for image in base.get("images", [])}
        image_paths = sorted(
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        images = [
            image_info(path, root, sequence, existing_images.get(path.name, {}), len(image_paths))
            for sequence, path in enumerate(image_paths, start=1)
        ]
        page_count = max((int(image["work_page"]) for image in images), default=0)
        source_meta_docx = rel(folder / "Meta.docx", root) if (folder / "Meta.docx").exists() else ""
        work = {
            "work_number": number,
            "work_label": f"Work {number}",
            "folder": folder.name,
            "title": title,
            "year": base.get("year", ""),
            "materials": base.get("materials", ""),
            "format": base.get("format", ""),
            "size": base.get("size", ""),
            "location": base.get("location", ""),
            "key": f"work{number:02d}",
            "page_count": page_count,
            "source_meta_docx": source_meta_docx,
            "images": images,
            "content_start_page": content_page if page_count else None,
            "content_end_page": content_page + page_count - 1 if page_count else None,
        }
        if page_count:
            content_page = int(work["content_end_page"]) + 1
        normalized.append(work)
        write_json(folder / "work.json", work)

    write_json(catalog_path, normalized)
    write_catalog_csv(metadata_root / "catalog.csv", normalized)
    write_filename_maps(metadata_root, filename_rows)
    write_policy(metadata_root, normalized)
    return normalized


def write_catalog_csv(path: Path, catalog: list[dict[str, Any]]) -> None:
    fields = [
        "work_number",
        "work_label",
        "folder",
        "title",
        "year",
        "format",
        "materials",
        "size",
        "location",
        "page_count",
        "content_start_page",
        "content_end_page",
        "image_count",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for work in catalog:
            writer.writerow(
                {
                    "work_number": work["work_number"],
                    "work_label": work["work_label"],
                    "folder": work["folder"],
                    "title": work["title"],
                    "year": work["year"],
                    "format": work["format"],
                    "materials": work["materials"],
                    "size": work["size"],
                    "location": work["location"],
                    "page_count": work["page_count"],
                    "content_start_page": work["content_start_page"],
                    "content_end_page": work["content_end_page"],
                    "image_count": len(work["images"]),
                }
            )


def write_filename_maps(metadata_root: Path, rows: list[dict[str, Any]]) -> None:
    write_json(metadata_root / "filename_map.json", rows)
    with (metadata_root / "filename_map.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["work", "old_path", "new_path", "renamed"])
        writer.writeheader()
        writer.writerows(rows)


def write_policy(metadata_root: Path, catalog: list[dict[str, Any]]) -> None:
    tex_filename = canonical_tex_filename(catalog)
    payload = {
        **CATALOGUE_POLICY,
        "canonical_tex": tex_filename,
        "compile_tex_pointer": CANONICAL_TEX_POINTER,
        "work_folder_order": [
            {
                "work_number": work["work_number"],
                "folder": work["folder"],
                "title": work["title"],
                "key": work["key"],
            }
            for work in catalog
        ],
    }
    write_json(metadata_root / "catalogue_policy.json", payload)


def parse_tex_references(root: Path) -> dict[str, list[str]]:
    pattern = re.compile(
        r"\{(portfolio_compiled_works_metadata/[^{}]+?\.(?:png|jpg|jpeg|tif|tiff))\}",
        re.IGNORECASE,
    )
    refs: dict[str, list[str]] = {}
    for tex_name in TEX_FILES:
        tex_path = root / tex_name
        text = tex_path.read_text(encoding="utf-8")
        input_matches = re.findall(r"\\input\{([^{}]+)\}", text)
        for input_name in input_matches:
            input_path = root / input_name
            if input_path.exists():
                text += "\n" + input_path.read_text(encoding="utf-8")
        refs[tex_name] = sorted(set(pattern.findall(text)))
    return refs


def sync_canonical_tex_filename(root: Path, catalog: list[dict[str, Any]]) -> Path:
    desired = root / canonical_tex_filename(catalog)
    pointer = root / CANONICAL_TEX_POINTER
    current = desired if desired.exists() else None

    if current is None:
        candidates = sorted(
            [
                path
                for path in root.glob("portfolio*.tex")
                if path.name not in {CANONICAL_TEX_POINTER}
            ],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        current = candidates[0] if candidates else root / DEFAULT_TEX_FILE

    if current.exists() and current.resolve() != desired.resolve():
        if desired.exists():
            desired.unlink()
        current.rename(desired)
    elif not desired.exists() and current.exists():
        desired.write_text(current.read_text(encoding="utf-8"), encoding="utf-8")

    pointer.write_text(
        "% This file is a stable compile pointer. The generated catalogue TeX is:\n"
        f"\\input{{{desired.name}}}\n",
        encoding="utf-8",
    )
    return desired


def tex_escape(value: Any) -> str:
    text = str(value or "")
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(char, char) for char in text)


def tex_join(parts: list[str]) -> str:
    return r"\artsep{}".join(parts)


def tex_meta(work: dict[str, Any]) -> str:
    parts = []
    if work.get("format"):
        parts.append(r"\textsc{" + tex_escape(work["format"]) + "}")
    if work.get("year"):
        parts.append(tex_escape(work["year"]))
    return tex_join(parts)


def tex_details(work: dict[str, Any]) -> str:
    parts = []
    if work.get("materials"):
        parts.append(tex_escape(work["materials"]))
    return tex_join(parts)


def tex_caption_details(work: dict[str, Any]) -> str:
    parts = []
    if work.get("materials"):
        parts.append(tex_escape(work["materials"]))
    if work.get("size"):
        parts.append(tex_escape(work["size"]))
    if work.get("location"):
        parts.append(tex_escape(work["location"]))
    return tex_join(parts)


def tex_toc_meta(work: dict[str, Any]) -> str:
    parts = []
    if work.get("format"):
        parts.append(r"\textsc{" + tex_escape(work["format"]) + "}")
    if work.get("year"):
        parts.append(tex_escape(work["year"]))
    if work.get("size"):
        parts.append(tex_escape(work["size"]))
    return tex_join(parts)


def sync_tex_inventory(root: Path, catalog: list[dict[str, Any]]) -> None:
    inventory_lines = [
        "% =====================================================================",
        "% INVENTORY - generated from the numbered Work folders.",
        "% =====================================================================",
        "",
    ]
    for work in catalog:
        key = work["key"]
        inventory_lines.extend(
            [
                rf"\definework{{{key}}}{{{work['work_number']}}}{{{work['page_count']}}}",
                rf"  {{{tex_escape(work['title'])}}}{{{tex_meta(work)}}}",
                rf"  {{{tex_caption_details(work)}}}{{}}",
                rf"\setworktocmeta{{{key}}}{{{tex_toc_meta(work)}}}",
                "",
            ]
        )
    inventory = "\n".join(inventory_lines)

    pattern = re.compile(
        r"% =====================================================================\n"
        r"% INVENTORY - generated from the numbered Work folders\.\n"
        r"% =====================================================================\n"
        r".*?"
        r"(?=\\newcommand\{\\computeworkranges\})",
        re.DOTALL,
    )
    canonical_tex = sync_canonical_tex_filename(root, catalog)
    rewrite_tex_image_paths(root, [])
    for path in [canonical_tex]:
        text = path.read_text(encoding="utf-8")
        updated, count = pattern.subn(lambda _match: inventory, text, count=1)
        if count != 1:
            raise RuntimeError(f"Could not locate inventory block in {path.name}")
        path.write_text(updated, encoding="utf-8")
    sync_tex_content_pages(canonical_tex, catalog)


ART_CENTER_X = 421.0
ART_CENTER_Y = 343.5
ART_FRAME_W = 758.0
ART_FRAME_H = 427.0
PAIR_GAP = 56.0


def image_aspect(image: dict[str, Any]) -> float:
    width = float(image.get("width_px") or 1)
    height = float(image.get("height_px") or 1)
    return width / height if height else 1.0


def grouped_work_pages(work: dict[str, Any]) -> list[list[dict[str, Any]]]:
    pages: dict[int, list[dict[str, Any]]] = {}
    for image in sorted(work["images"], key=lambda item: int(item["sequence"])):
        pages.setdefault(int(image["work_page"]), []).append(image)
    return [pages[number] for number in sorted(pages)]


def paired_image_lines(images: list[dict[str, Any]]) -> list[str]:
    if len(images) == 1:
        image = images[0]
        return [
            rf"\fitimagebox{{{ART_CENTER_X:.3f}}}{{{ART_CENTER_Y:.3f}}}{{{ART_FRAME_W:.3f}}}{{{ART_FRAME_H:.3f}}}{{{image['relative_path']}}}"
        ]

    aspects = [image_aspect(image) for image in images]
    available_width = ART_FRAME_W - PAIR_GAP * (len(images) - 1)
    height = min(ART_FRAME_H, available_width / sum(aspects))
    widths = [aspect * height for aspect in aspects]
    total_width = sum(widths) + PAIR_GAP * (len(images) - 1)
    cursor = ART_CENTER_X - total_width / 2
    lines = []
    for image, width in zip(images, widths):
        center_x = cursor + width / 2
        lines.append(
            rf"\fitimageheight{{{center_x:.3f}}}{{{ART_CENTER_Y:.3f}}}{{{height:.3f}}}{{{image['relative_path']}}}"
        )
        cursor += width + PAIR_GAP
    return lines


def content_pages_tex(catalog: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for work in catalog:
        chunks.extend(
            [
                "% ---------------------------------------------------------------------",
                f"% Work {work['work_number']} - {work['title']}",
                "% ---------------------------------------------------------------------",
            ]
        )
        for page_index, images in enumerate(grouped_work_pages(work), start=1):
            chunks.append(r"\begin{portfoliopage}")
            if page_index == 1:
                chunks.append(rf"\worktarget{{{work['key']}}}")
            chunks.extend(paired_image_lines(images))
            chunks.append(rf"\artworkcaption{{{work['key']}}}{{{page_index}}}")
            chunks.append(r"\end{portfoliopage}")
            chunks.append("")
    return "\n".join(chunks).rstrip()


def sync_tex_content_pages(tex_path: Path, catalog: list[dict[str, Any]]) -> None:
    text = tex_path.read_text(encoding="utf-8")
    start = text.find("% ---------------------------------------------------------------------\n% Work ")
    end = text.rfind(r"\end{document}")
    if start == -1 or end == -1 or start >= end:
        raise RuntimeError(f"Could not locate generated work page block in {tex_path.name}")
    updated = text[:start] + content_pages_tex(catalog) + "\n\n" + text[end:]
    tex_path.write_text(updated, encoding="utf-8")


def pdf_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": path.as_posix(), "exists": False}
    proc = subprocess.run(
        ["pdfinfo", str(path)],
        text=True,
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        return {
            "path": path.as_posix(),
            "exists": True,
            "readable": False,
            "error": (proc.stderr or proc.stdout).strip(),
            "file_size_bytes": path.stat().st_size,
        }
    info = proc.stdout
    pages = None
    media_box = ""
    for line in info.splitlines():
        if line.startswith("Pages:"):
            pages = int(line.split(":", 1)[1].strip())
        if line.startswith("Page size:"):
            media_box = line.split(":", 1)[1].strip()
    return {
        "path": path.as_posix(),
        "exists": True,
        "readable": True,
        "pages": pages,
        "page_size": media_box,
        "file_size_bytes": path.stat().st_size,
    }


def output_manifest(root: Path, expected_pdf_pages: int) -> dict[str, Any]:
    outputs = []
    for spec in OUTPUTS:
        pdf_path = root / spec["pdf"]
        pages_dir = root / spec["pages_dir"]
        page_files = sorted(pages_dir.glob(f"{spec['page_prefix']}-page-*.pdf")) if pages_dir.exists() else []
        outputs.append(
            {
                "key": spec["key"],
                "pdf": pdf_info(pdf_path),
                "split_pages_dir": spec["pages_dir"],
                "split_page_count": len(page_files),
                "expected_page_count": expected_pdf_pages,
                "split_pages": [
                    {
                        "path": rel(path, root),
                        "file_size_bytes": path.stat().st_size,
                    }
                    for path in page_files
                ],
            }
        )
    return {"expected_pdf_page_count": expected_pdf_pages, "outputs": outputs}


def build_manifest(root: Path, catalog: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    tex_refs = parse_tex_references(root)
    all_images = sorted(image["relative_path"] for work in catalog for image in work["images"])
    all_image_set = set(all_images)
    errors: list[str] = []

    tex_checks = {}
    for tex_name, refs in tex_refs.items():
        ref_set = set(refs)
        missing_from_tex = sorted(all_image_set - ref_set)
        missing_files = sorted(ref for ref in refs if not (root / ref).exists())
        extra_refs = sorted(ref_set - all_image_set)
        if missing_from_tex:
            errors.append(f"{tex_name} does not include {len(missing_from_tex)} library image(s)")
        if missing_files:
            errors.append(f"{tex_name} references {len(missing_files)} missing file(s)")
        if extra_refs:
            errors.append(f"{tex_name} references {len(extra_refs)} file(s) outside the catalogue")
        tex_checks[tex_name] = {
            "image_reference_count": len(refs),
            "missing_library_images": missing_from_tex,
            "missing_files": missing_files,
            "extra_references": extra_refs,
        }

    content_pages = sum(int(work["page_count"]) for work in catalog)
    expected_pdf_pages = content_pages + 2
    outputs = output_manifest(root, expected_pdf_pages)

    manifest = {
        "catalogue_source": "portfolio_compiled_works_metadata/Work */work.json",
        "aggregate_catalogue": "portfolio_compiled_works_metadata/catalog.json",
        "tex_sources": TEX_FILES,
        "work_count": len(catalog),
        "library_image_count": len(all_images),
        "content_page_count": content_pages,
        "expected_pdf_page_count": expected_pdf_pages,
        "works": [
            {
                "work_number": work["work_number"],
                "folder": work["folder"],
                "title": work["title"],
                "page_count": work["page_count"],
                "content_start_page": work["content_start_page"],
                "content_end_page": work["content_end_page"],
                "image_count": len(work["images"]),
                "images": [
                    {
                        "relative_path": image["relative_path"],
                        "work_page": image["work_page"],
                        "page_role": image["page_role"],
                        "width_px": image["width_px"],
                        "height_px": image["height_px"],
                        "file_size_bytes": image["file_size_bytes"],
                    }
                    for image in work["images"]
                ],
            }
            for work in catalog
        ],
        "tex_inclusion_checks": tex_checks,
        "outputs": outputs["outputs"],
        "status": "ok" if not errors else "error",
        "errors": errors,
    }
    return manifest, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write refreshed JSON/CSV manifests")
    parser.add_argument("--sync-tex", action="store_true", help="rewrite the TeX inventory from Meta.txt/catalogue data")
    parser.add_argument("--require-output", action="store_true", help="fail when compiled output PDFs are missing")
    args = parser.parse_args()

    root = repo_root()
    catalog = normalize_catalog(root) if args.write else json_load(root / "portfolio_compiled_works_metadata" / "catalog.json", [])
    if args.sync_tex:
        try:
            sync_tex_inventory(root, catalog)
        except Exception as exc:
            print(f"ERROR: {exc}")
            return 1
    manifest, errors = build_manifest(root, catalog)

    if args.require_output:
        for output in manifest["outputs"]:
            if not output["pdf"].get("exists"):
                errors.append(f"Missing compiled PDF: {output['pdf']['path']}")
            elif not output["pdf"].get("readable", True):
                errors.append(f"Unreadable compiled PDF: {output['pdf']['path']}")
            elif output["pdf"].get("pages") != manifest["expected_pdf_page_count"]:
                errors.append(
                    f"{output['pdf']['path']} has {output['pdf'].get('pages')} pages, "
                    f"expected {manifest['expected_pdf_page_count']}"
                )
            if output["split_page_count"] != manifest["expected_pdf_page_count"]:
                errors.append(
                    f"Missing split page PDFs in {output['split_pages_dir']}: "
                    f"{output['split_page_count']} of {manifest['expected_pdf_page_count']}"
                )
        manifest["status"] = "ok" if not errors else "error"
        manifest["errors"] = errors

    if args.write:
        write_json(root / "portfolio_compiled_works_metadata" / "inclusion_manifest.json", manifest)
        output_payload = {
            "expected_pdf_page_count": manifest["expected_pdf_page_count"],
            "outputs": manifest["outputs"],
            "status": manifest["status"],
            "errors": manifest["errors"],
        }
        write_json(root / "Output" / "output_manifest.json", output_payload)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        f"OK: {manifest['work_count']} works, {manifest['library_image_count']} images, "
        f"{manifest['expected_pdf_page_count']} PDF pages"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
