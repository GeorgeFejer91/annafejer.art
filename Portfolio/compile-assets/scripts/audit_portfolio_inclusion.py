from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image


Image.MAX_IMAGE_PIXELS = None

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
TEX_FILES = ["portfolio_from_ppt_images_a4.tex"]
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

    folders = sorted(metadata_root.glob("Work *"), key=work_number)
    content_page = 1
    for folder in folders:
        number = work_number(folder)
        work_json = json_load(folder / "work.json", {})
        meta_txt = parse_meta_txt(folder / "Meta.txt")
        base = {**catalog_by_number.get(number, {}), **work_json, **meta_txt}
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
            "title": base.get("title") or f"Work {number}",
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
    write_filename_maps(metadata_root, normalized)
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


def write_filename_maps(metadata_root: Path, catalog: list[dict[str, Any]]) -> None:
    existing = json_load(metadata_root / "filename_map.json", [])
    by_new_path = {row.get("new_path"): row for row in existing}
    rows = []
    for work in catalog:
        for image in work["images"]:
            old = by_new_path.get(image["relative_path"], {})
            rows.append(
                {
                    "work": work["work_label"],
                    "old_path": old.get("old_path", image["relative_path"]),
                    "new_path": image["relative_path"],
                    "renamed": bool(old.get("renamed", False)),
                }
            )
    write_json(metadata_root / "filename_map.json", rows)
    with (metadata_root / "filename_map.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["work", "old_path", "new_path", "renamed"])
        writer.writeheader()
        writer.writerows(rows)


def parse_tex_references(root: Path) -> dict[str, list[str]]:
    pattern = re.compile(
        r"\{(portfolio_compiled_works_metadata/[^{}]+?\.(?:png|jpg|jpeg|tif|tiff))\}",
        re.IGNORECASE,
    )
    refs: dict[str, list[str]] = {}
    for tex_name in TEX_FILES:
        refs[tex_name] = sorted(set(pattern.findall((root / tex_name).read_text(encoding="utf-8"))))
    return refs


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
    for tex_name in TEX_FILES:
        path = root / tex_name
        text = path.read_text(encoding="utf-8")
        updated, count = pattern.subn(lambda _match: inventory, text, count=1)
        if count != 1:
            raise RuntimeError(f"Could not locate inventory block in {tex_name}")
        path.write_text(updated, encoding="utf-8")


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
        sync_tex_inventory(root, catalog)
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
