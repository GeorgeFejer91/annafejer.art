from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image


Image.MAX_IMAGE_PIXELS = None

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
LEGACY_METADATA_FILENAMES = {"Meta.txt", "Meta.docx"}
CAPTION_METADATA_FIELDS = ["title", "year", "materials", "format", "size", "location"]
CANONICAL_TEX_POINTER = "portfolio_current.tex"
GERMAN_TEX_POINTER = "portfolio_current_de.tex"
DEFAULT_TEX_FILE = "portfolio_from_ppt_images_a4.tex"
TEX_FILES = [CANONICAL_TEX_POINTER, GERMAN_TEX_POINTER]
TOC_LEFT_X = 70
TOC_RIGHT_X = 448
TOC_Y_POSITIONS_8 = [472, 422, 372, 322, 272, 222, 172, 122]
TOC_Y_POSITIONS_9 = [472, 424, 376, 328, 280, 232, 184, 136, 88]
CATALOGUE_POLICY = {
    "version": 3,
    "source_of_truth": {
        "work_order": "The folder names directly under portfolio_compiled_works_metadata are the sole authority for portfolio ordering. Work 1 comes before Work 2, Work 2 before Work 3, and so on by numeric suffix.",
        "work_identity": "The numeric Work N folder is the stable identity and grouping boundary for each artwork throughout the repo.",
        "metadata": "work.json inside each Work N folder is the sole human-edited per-work metadata file. It contains only the caption fields displayed in the portfolio.",
        "images": "Image files inside each Work N folder are the authoritative source images for that work.",
        "generated_outputs": "TeX files, PDFs, CSVs, aggregate JSON files, manifests, and page-split outputs are generated from the Work folder order and must not override it.",
    },
    "ordering_rule": "Sort direct child folders matching Work <number> by numeric suffix in ascending order. Do not infer portfolio order from TeX order, PDF page order, CSV row order, file timestamps, image filenames, or metadata fields inside the Work folders.",
    "image_naming_rule": "On every catalogue refresh, artwork images are renamed to title-slug-YY.ext, where title-slug is a short lowercase slug for the artwork title and YY is the image sequence within that folder. Image filenames must not encode the Work folder number or cross-work order.",
    "metadata_scope_rule": "work.json may change only caption fields: title, year, materials, format, size, and location. It must not contain Work numbers, image lists, generated paths, page counts, or cross-work ordering.",
    "tex_rule": "The LaTeX inventory is generated from the Work folder catalogue and should not be treated as the source of truth.",
}

GERMAN_TRANSLATIONS = {
    "format": {
        "Canvas": "Leinwand",
        "Collage": "Collage",
        "Digital Photograph": "Digitale Fotografie",
        "Illustration": "Illustration",
        "Installation": "Installation",
        "Lino Print": "Linoldruck",
        "Sculpture": "Skulptur",
    },
    "materials": {
        "Balloons": "Luftballons",
        "Cardboard": "Karton",
        "Copper Pipes": "Kupferrohre",
        "Fishing line": "Angelschnur",
        "Fishing Line": "Angelschnur",
        "Glass": "Glas",
        "Ink": "Tusche",
        "Maps": "Karten",
        "Metal": "Metall",
        "Metal Can": "Metalldose",
        "Metal Grates": "Metallgitter",
        "Newspaper": "Zeitungspapier",
        "Oil": "Öl",
        "Paint": "Farbe",
        "Paper": "Papier",
        "Plastic": "Kunststoff",
        "Polystyrene": "Polystyrol",
        "Prints": "Drucke",
        "Sand": "Sand",
        "Tape": "Klebeband",
        "Tin foil": "Alufolie",
        "Umbrella": "Regenschirm",
        "Wire": "Draht",
        "Wood": "Holz",
    },
    "location": {
        "Exhibition view, Dudley College of Technology, England": "Ausstellungsansicht, Dudley College of Technology, England",
        "Exhibition at Dudley College of Technology": "Ausstellung am Dudley College of Technology",
        "Kings Heath Eid - England": "Kings Heath Eid, England",
    },
}

COVER_TEXT = {
    "en": {"portfolio": "Portfolio", "selected": "Selected works, 2024-2026", "contents": "Contents", "pages": "Pages", "work": "Work"},
    "de": {"portfolio": "Mappe", "selected": "Ausgewählte Arbeiten, 2024-2026", "contents": "Inhalt", "pages": "Seiten", "work": "Werk"},
}
OUTPUTS = [
    {
        "key": "a4",
        "pdf": "Output/Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_EN.pdf",
        "pages_dir": "Output/pages/Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_EN",
        "page_prefix": "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_EN",
    },
    {
        "key": "a4-de",
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
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


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


def caption_metadata(payload: dict[str, Any]) -> dict[str, str]:
    return {
        field: clean_meta_value(str(payload.get(field, "") or ""))
        for field in CAPTION_METADATA_FIELDS
    }


def valid_work_metadata(folder: Path, payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    recorded_folder = str(payload.get("folder", "") or "")
    if recorded_folder and recorded_folder != folder.name:
        return {}
    return caption_metadata(payload)


def image_page_suffix(path: Path) -> str:
    match = re.search(r"(?:[-_ ])([A-Z])$", path.stem)
    return f"-{match.group(1)}" if match else ""


def image_page_hint(path: Path) -> int | None:
    match = re.search(r"(?:[-_ ])([A-Z])$", path.stem)
    if not match:
        return None
    return ord(match.group(1)) - ord("A") + 1


def image_signature(paths: list[Path]) -> tuple[str, ...]:
    return tuple(sorted(path.name for path in paths))


def catalog_by_image_signature(catalog: list[dict[str, Any]]) -> dict[tuple[str, ...], dict[str, Any]]:
    rows: dict[tuple[str, ...], dict[str, Any]] = {}
    for work in catalog:
        signature = tuple(sorted(str(image.get("filename", "")) for image in work.get("images", [])))
        if signature and signature not in rows:
            rows[signature] = work
    return rows


def canonical_image_path(folder: Path, work_num: int, title: str, sequence: int, path: Path) -> Path:
    slug = slugify(title or "untitled")
    return folder / f"{slug}-{sequence:02d}{image_page_suffix(path)}{path.suffix.lower()}"


def canonical_tex_filename(catalog: list[dict[str, Any]]) -> str:
    return "portfolio_a4_catalogue.tex"


def language_tex_filename(catalog: list[dict[str, Any]], language: str) -> str:
    english_name = canonical_tex_filename(catalog)
    if language == "en":
        return english_name
    return english_name.replace("portfolio_a4_", f"portfolio_a4_{language}_", 1)


def canonicalize_work_images(folder: Path, work_num: int, title: str, root: Path) -> list[dict[str, Any]]:
    image_paths = sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    rows: list[dict[str, Any]] = []
    for sequence, path in enumerate(image_paths, start=1):
        target = canonical_image_path(folder, work_num, title, sequence, path)
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


def remove_legacy_metadata_files(folder: Path) -> None:
    for filename in LEGACY_METADATA_FILENAMES:
        path = folder / filename
        if path.exists():
            path.unlink()


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
    hinted_page = image_page_hint(path)
    if work_page is None and hinted_page is not None:
        work_page = hinted_page
        page_role = f"page {hinted_page} image"
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
    catalog_by_signature = catalog_by_image_signature(existing_catalog)
    normalized: list[dict[str, Any]] = []
    filename_rows: list[dict[str, Any]] = []

    folders = sorted(metadata_root.glob("Work *"), key=work_number)
    content_page = 1
    for folder in folders:
        number = work_number(folder)
        work_json = json_load(folder / "work.json", {})
        meta_txt = parse_meta_txt(folder / "Meta.txt")
        current_image_paths = sorted(
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        signature_match = catalog_by_signature.get(image_signature(current_image_paths), {})
        work_meta = valid_work_metadata(folder, work_json)
        base = {
            **caption_metadata(catalog_by_number.get(number, {})),
            **caption_metadata(signature_match),
            **meta_txt,
            **work_meta,
        }
        title = base.get("title") or f"Untitled {number}"
        rename_rows = canonicalize_work_images(folder, number, title, root)
        filename_rows.extend(rename_rows)
        existing_images: dict[str, Any] = {}
        for source in [catalog_by_number.get(number, {}), signature_match, work_json if work_meta else {}]:
            for image in source.get("images", []) if isinstance(source, dict) else []:
                if image.get("filename"):
                    existing_images[image["filename"]] = image
        for row in rename_rows:
            old_name = Path(row["old_path"]).name
            new_name = Path(row["new_path"]).name
            if old_name in existing_images:
                existing_images[new_name] = existing_images[old_name]
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
            "metadata_file": rel(folder / "work.json", root),
            "images": images,
            "content_start_page": content_page if page_count else None,
            "content_end_page": content_page + page_count - 1 if page_count else None,
        }
        if page_count:
            content_page = int(work["content_end_page"]) + 1
        normalized.append(work)
        write_json(folder / "work.json", caption_metadata(work))
        remove_legacy_metadata_files(folder)

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
    tex_filename = language_tex_filename(catalog, "en")
    german_tex_filename = language_tex_filename(catalog, "de")
    root = metadata_root.parent
    payload = {
        **CATALOGUE_POLICY,
        "contract_file": "portfolio_order_contract.json",
        "metadata_policy_file": "portfolio_compiled_works_metadata/catalogue_policy.json",
        "canonical_tex": tex_filename,
        "compile_tex_pointer": CANONICAL_TEX_POINTER,
        "german_tex": german_tex_filename,
        "german_compile_tex_pointer": GERMAN_TEX_POINTER,
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
    write_json(root / "portfolio_order_contract.json", payload)


def parse_tex_references(root: Path) -> dict[str, list[str]]:
    pattern = re.compile(
        r"\{(portfolio_compiled_works_metadata/[^{}]+?\.(?:png|jpg|jpeg|tif|tiff))\}",
        re.IGNORECASE,
    )
    refs: dict[str, list[str]] = {}
    for tex_name in TEX_FILES:
        tex_path = root / tex_name
        if not tex_path.exists():
            continue
        text = tex_path.read_text(encoding="utf-8")
        input_matches = re.findall(r"\\input\{([^{}]+)\}", text)
        for input_name in input_matches:
            input_path = root / input_name
            if input_path.exists():
                text += "\n" + input_path.read_text(encoding="utf-8")
        refs[tex_name] = sorted(set(pattern.findall(text)))
    return refs


def sync_canonical_tex_filename(root: Path, catalog: list[dict[str, Any]], language: str = "en") -> Path:
    desired = root / language_tex_filename(catalog, language)
    pointer = root / (GERMAN_TEX_POINTER if language == "de" else CANONICAL_TEX_POINTER)
    current = desired if desired.exists() else None

    if current is None:
        generated_names = {CANONICAL_TEX_POINTER, GERMAN_TEX_POINTER}
        candidates = sorted(
            [
                path
                for path in root.glob("portfolio*.tex")
                if path.name not in generated_names and ("_de_" in path.name) == (language == "de")
            ],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            current = candidates[0]
        elif language == "de":
            english_tex = root / language_tex_filename(catalog, "en")
            current = english_tex if english_tex.exists() else root / DEFAULT_TEX_FILE
        else:
            current = root / DEFAULT_TEX_FILE

    if current.exists() and current.resolve() != desired.resolve():
        if desired.exists():
            desired.unlink()
        if language == "de" and current.name == language_tex_filename(catalog, "en"):
            shutil.copyfile(current, desired)
        else:
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


def translate_term(value: str, language: str, category: str) -> str:
    if language != "de" or not value:
        return value
    return GERMAN_TRANSLATIONS.get(category, {}).get(value, value)


def translate_list(value: str, language: str, category: str) -> str:
    if language != "de" or not value:
        return value
    return ", ".join(translate_term(part.strip(), language, category) for part in value.split(","))


def localized_work(work: dict[str, Any], language: str) -> dict[str, Any]:
    if language == "en":
        return work
    localized = dict(work)
    localized["format"] = translate_term(str(work.get("format", "")), language, "format")
    localized["materials"] = translate_list(str(work.get("materials", "")), language, "materials")
    localized["location"] = translate_term(str(work.get("location", "")), language, "location")
    return localized


def tex_meta(work: dict[str, Any], language: str = "en") -> str:
    work = localized_work(work, language)
    parts = []
    if work.get("format"):
        parts.append(r"\textsc{" + tex_escape(work["format"]) + "}")
    if work.get("year"):
        parts.append(tex_escape(work["year"]))
    return tex_join(parts)


def tex_details(work: dict[str, Any], language: str = "en") -> str:
    work = localized_work(work, language)
    parts = []
    if work.get("materials"):
        parts.append(tex_escape(work["materials"]))
    return tex_join(parts)


def tex_caption_details(work: dict[str, Any], language: str = "en") -> str:
    work = localized_work(work, language)
    parts = []
    if work.get("materials"):
        parts.append(tex_escape(work["materials"]))
    if work.get("size"):
        parts.append(tex_escape(work["size"]))
    if work.get("location"):
        parts.append(tex_escape(work["location"]))
    return tex_join(parts)


def tex_toc_meta(work: dict[str, Any], language: str = "en") -> str:
    work = localized_work(work, language)
    parts = []
    if work.get("format"):
        parts.append(r"\textsc{" + tex_escape(work["format"]) + "}")
    if work.get("year"):
        parts.append(tex_escape(work["year"]))
    if work.get("size"):
        parts.append(tex_escape(work["size"]))
    return tex_join(parts)


def sync_tex_inventory(root: Path, catalog: list[dict[str, Any]]) -> None:
    for language in ["en", "de"]:
        sync_tex_language(root, catalog, language)


def sync_tex_language(root: Path, catalog: list[dict[str, Any]], language: str) -> None:
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
                rf"  {{{tex_escape(work['title'])}}}{{{tex_meta(work, language)}}}",
                rf"  {{{tex_caption_details(work, language)}}}{{}}",
                rf"\setworktocmeta{{{key}}}{{{tex_toc_meta(work, language)}}}",
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
    canonical_tex = sync_canonical_tex_filename(root, catalog, language)
    if language == "de":
        english_tex = root / language_tex_filename(catalog, "en")
        if not english_tex.exists():
            raise RuntimeError(f"Cannot build German TeX because {english_tex.name} does not exist")
        shutil.copyfile(english_tex, canonical_tex)
    rewrite_tex_image_paths(root, [])
    for path in [canonical_tex]:
        text = path.read_text(encoding="utf-8")
        text = localize_static_tex(text, language)
        updated, count = pattern.subn(lambda _match: inventory, text, count=1)
        if count != 1:
            raise RuntimeError(f"Could not locate inventory block in {path.name}")
        updated = sync_tex_toc(updated, catalog, language, path.name)
        path.write_text(updated, encoding="utf-8")
    sync_tex_content_pages(canonical_tex, catalog, language)


def sync_tex_toc(text: str, catalog: list[dict[str, Any]], language: str, tex_name: str) -> str:
    labels = COVER_TEXT[language]
    rows_per_column = (len(catalog) + 1) // 2
    if rows_per_column <= len(TOC_Y_POSITIONS_8):
        y_positions = TOC_Y_POSITIONS_8
    elif rows_per_column == len(TOC_Y_POSITIONS_9):
        y_positions = TOC_Y_POSITIONS_9
    else:
        raise RuntimeError(
            f"Table-of-contents layout in {tex_name} supports at most 18 works on one page; "
            f"found {len(catalog)} works"
        )

    left_column = catalog[:rows_per_column]
    right_column = catalog[rows_per_column:]
    rows = []
    for index, work in enumerate(left_column):
        rows.append(rf"  \tocentryrow{{{work['key']}}}{{{TOC_LEFT_X}}}{{{y_positions[index]}}}%")
    for index, work in enumerate(right_column):
        rows.append(rf"  \tocentryrow{{{work['key']}}}{{{TOC_RIGHT_X}}}{{{y_positions[index]}}}%")
    block = "\n".join(
        [
            r"\newcommand{\rendertoc}{%",
            rf"  \node[anchor=west,inner sep=0pt] at (70,520){{\fontsize{{34}}{{40}}\selectfont\bfseries\color{{PortfolioInk}} {labels['contents']}}};%",
            r"  \draw[PortfolioRule,line width=0.6pt] (70,492) -- (772,492);%",
            rf"  \node[anchor=east,inner sep=0pt] at (772,504){{\fontsize{{9.5}}{{11}}\selectfont\color{{PortfolioGraphite}}\textsc{{{labels['pages']}}}}};%",
            r"  \draw[PortfolioRule,line width=0.4pt] (421,484) -- (421,46);%",
            *rows,
            "}",
        ]
    )
    updated, count = re.subn(
        r"\\newcommand\{\\rendertoc\}\{%.*?\n\}\n\\begin\{document\}",
        lambda _match: block + "\n" + r"\begin{document}",
        text,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError(f"Could not locate table-of-contents block in {tex_name}")
    return updated


ART_CENTER_X = 421.0
ART_CENTER_Y = 343.5
ART_FRAME_W = 758.0
ART_FRAME_H = 427.0
PAIR_GAP = 56.0


def localize_static_tex(text: str, language: str) -> str:
    labels = COVER_TEXT[language]
    text = re.sub(
        r"\\newcommand\{\\worklabel\}\[1\]\{[^}]*\\csname w@#1@order\\endcsname\}",
        rf"\\newcommand{{\\worklabel}}[1]{{{labels['work']} \\csname w@#1@order\\endcsname}}",
        text,
    )
    replacements = {
        r"\fontsize{38}{44}\selectfont\color{PortfolioGraphite} Portfolio": rf"\fontsize{{38}}{{44}}\selectfont\color{{PortfolioGraphite}} {labels['portfolio']}",
        "Selected works, 2024-2026": labels["selected"],
        r"\fontsize{34}{40}\selectfont\bfseries\color{PortfolioInk} Contents": rf"\fontsize{{34}}{{40}}\selectfont\bfseries\color{{PortfolioInk}} {labels['contents']}",
        r"\textsc{Pages}": rf"\textsc{{{labels['pages']}}}",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


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


def content_pages_tex(catalog: list[dict[str, Any]], language: str = "en") -> str:
    chunks: list[str] = []
    work_label = COVER_TEXT[language]["work"]
    for work in catalog:
        chunks.extend(
            [
                "% ---------------------------------------------------------------------",
                f"% {work_label} {work['work_number']} - {work['title']}",
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


def sync_tex_content_pages(tex_path: Path, catalog: list[dict[str, Any]], language: str = "en") -> None:
    text = tex_path.read_text(encoding="utf-8")
    start = text.find("% ---------------------------------------------------------------------\n% Work ")
    if start == -1:
        start = text.find("% ---------------------------------------------------------------------\n% Werk ")
    end = text.rfind(r"\end{document}")
    if start == -1 or end == -1 or start >= end:
        raise RuntimeError(f"Could not locate generated work page block in {tex_path.name}")
    updated = text[:start] + content_pages_tex(catalog, language) + "\n\n" + text[end:]
    tex_path.write_text(updated, encoding="utf-8")


def pdf_info(path: Path, root: Path | None = None) -> dict[str, Any]:
    display_path = rel(path, root) if root is not None else path.as_posix()
    if not path.exists():
        return {"path": display_path, "exists": False}
    proc = subprocess.run(
        ["pdfinfo", str(path)],
        text=True,
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        return {
            "path": display_path,
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
        "path": display_path,
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
                "pdf": pdf_info(pdf_path, root),
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
    metadata_root = root / "portfolio_compiled_works_metadata"
    folder_numbers = [work_number(path) for path in sorted(metadata_root.glob("Work *"), key=work_number)]
    catalog_numbers = [int(work["work_number"]) for work in catalog]
    expected_numbers = list(range(1, len(folder_numbers) + 1))
    if folder_numbers != expected_numbers:
        errors.append(
            "Work folders are not a contiguous numeric ordering authority: "
            f"found {folder_numbers}, expected {expected_numbers}"
        )
    if catalog_numbers != folder_numbers:
        errors.append(
            "Aggregate catalogue order does not match numeric Work folder order: "
            f"catalogue {catalog_numbers}, folders {folder_numbers}"
        )

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
        "catalogue_source": "portfolio_compiled_works_metadata/Work */work.json caption fields plus images in each Work folder",
        "aggregate_catalogue": "portfolio_compiled_works_metadata/catalog.json",
        "ordering_authority": "portfolio_order_contract.json",
        "ordering_authority_rule": CATALOGUE_POLICY["ordering_rule"],
        "work_folder_numeric_order": folder_numbers,
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
    parser.add_argument("--sync-tex", action="store_true", help="rewrite the TeX inventory from work.json/catalogue data")
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
