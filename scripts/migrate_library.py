"""Migrate library: extract folder from filename if folder field is missing."""
import json
from pathlib import Path

p = Path(__file__).parent.parent / "projects" / "_library" / "index.json"
items = json.loads(p.read_text(encoding="utf-8"))
fixed = 0
for item in items:
    if item.get("folder"):
        continue
    fname = item.get("filename", "")
    if "/" in fname:
        parts = fname.rsplit("/", 1)
        item["folder"] = parts[0]
        item["filename"] = parts[1]
        fixed += 1
    elif "\\" in fname:
        parts = fname.rsplit("\\", 1)
        item["folder"] = parts[0]
        item["filename"] = parts[1]
        fixed += 1
p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Fixed {fixed} items, total {len(items)}")
items2 = json.loads(p.read_text(encoding="utf-8"))
with_folder = sum(1 for i in items2 if i.get("folder"))
print(f"Items with folder: {with_folder}")
if items2:
    print(f"Sample: {items2[0].get('folder', 'N/A')} / {items2[0].get('filename', 'N/A')}")
