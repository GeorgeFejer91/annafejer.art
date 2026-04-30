import os
import json
import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'Portfolio' / 'portfolio_compiled_works_metadata'

# Load existing catalog if present
catalog_path = root / 'catalog.json'
if catalog_path.exists():
    with open(catalog_path, 'r', encoding='utf-8') as f:
        try:
            catalog = json.load(f)
        except Exception:
            catalog = []
else:
    catalog = []

# Helper: map folder -> catalog index
catalog_by_folder = {item.get('folder'): idx for idx, item in enumerate(catalog)}

# Find all work.json files
work_files = sorted(root.glob('Work */work.json'), key=lambda p: int(p.parent.name.split()[-1]))

# Update catalog entries from work.json
seen_folders = set()
for wf in work_files:
    folder = wf.parent.name
    seen_folders.add(folder)
    metadata = {}
    try:
        with open(wf, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    except Exception:
        metadata = {}

    if folder in catalog_by_folder:
        idx = catalog_by_folder[folder]
        entry = catalog[idx]
        # update basic fields
        for k in ('title', 'year', 'materials', 'format', 'size', 'location'):
            if k in metadata:
                entry[k] = metadata[k]
        entry['metadata_file'] = str(Path('portfolio_compiled_works_metadata') / folder / 'work.json')
        catalog[idx] = entry
    else:
        # create new entry
        # compute next work_number
        nums = [it.get('work_number') for it in catalog if isinstance(it.get('work_number'), int)]
        next_num = max(nums) + 1 if nums else 1
        key = f"work{next_num:02d}"
        entry = {
            'work_number': next_num,
            'work_label': folder,
            'folder': folder,
            'title': metadata.get('title',''),
            'year': metadata.get('year',''),
            'materials': metadata.get('materials',''),
            'format': metadata.get('format',''),
            'size': metadata.get('size',''),
            'location': metadata.get('location',''),
            'key': key,
            'page_count': 0,
            'metadata_file': str(Path('portfolio_compiled_works_metadata') / folder / 'work.json'),
            'images': [],
            'content_start_page': None,
            'content_end_page': None
        }
        catalog.append(entry)
        catalog_by_folder[folder] = len(catalog)-1

# Optionally, keep catalog sorted by work_number
catalog_sorted = sorted(catalog, key=lambda x: x.get('work_number', 0))

# Write updated catalog.json
with open(catalog_path, 'w', encoding='utf-8') as f:
    json.dump(catalog_sorted, f, indent=2, ensure_ascii=False)

# Write catalog.csv (basic fields)
csv_path = root / 'catalog.csv'
with open(csv_path, 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    header = ['work_number','work_label','folder','title','year','materials','format','size','location','metadata_file']
    writer.writerow(header)
    for it in catalog_sorted:
        writer.writerow([it.get(h,'') for h in header])

# Regenerate filename_map.json by scanning image files
img_exts = {'.png','.jpg','.jpeg','.gif','.tif','.tiff'}
filename_map = []
for folder in sorted(root.glob('Work *'), key=lambda p: int(p.name.split()[-1])):
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.suffix.lower() in img_exts:
            rel = str(p.relative_to(root.parent))
            filename_map.append({
                'work': folder.name,
                'old_path': rel,
                'new_path': rel,
                'renamed': False
            })

fm_json_path = root / 'filename_map.json'
with open(fm_json_path, 'w', encoding='utf-8') as f:
    json.dump(filename_map, f, indent=2, ensure_ascii=False)

# Also write filename_map.csv
fm_csv_path = root / 'filename_map.csv'
with open(fm_csv_path, 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['work','old_path','new_path','renamed'])
    for it in filename_map:
        writer.writerow([it['work'], it['old_path'], it['new_path'], str(it['renamed'])])

print('Regenerated catalog.json, catalog.csv, filename_map.json, filename_map.csv')
