import os, json, glob
from datetime import datetime, timezone

BASE = os.path.dirname(__file__)
SNAP = os.path.join(BASE, "snapshots")
OUT = os.path.join(BASE, "page_changes.json")

def latest_two(folder):
    files = sorted(glob.glob(os.path.join(folder, "*.json")))
    # Same-day files are not useful for a daily diff; keep the two latest capture dates.
    by_day = {}
    for f in files:
        name = os.path.basename(f)
        parts = name.rsplit("_", 1)
        if len(parts) != 2:
            continue
        day = parts[1].replace(".json", "")
        by_day.setdefault(day, []).append(f)
    days = sorted(by_day.keys())
    if len(days) < 2:
        return None, None
    return by_day[days[-2]][0], by_day[days[-1]][0]

def compare(old, new):
    changes = []
    for field in ["title", "h1", "headings", "buttons", "videos", "modules", "textHash"]:
        if old.get(field) != new.get(field):
            changes.append(field)

    added_modules = sorted(set(new.get("modules", [])) - set(old.get("modules", [])))
    removed_modules = sorted(set(old.get("modules", [])) - set(new.get("modules", [])))
    added_videos = len(new.get("videos", [])) - len(old.get("videos", []))
    removed_videos = len(old.get("videos", [])) - len(new.get("videos", []))

    return {
        "changed": bool(changes),
        "fieldsChanged": changes,
        "addedModules": added_modules,
        "removedModules": removed_modules,
        "videoDelta": {"added": max(0, added_videos), "removed": max(0, removed_videos)},
        "oldHeadings": old.get("headings", []),
        "newHeadings": new.get("headings", [])
    }

def main():
    changes = []
    for root, dirs, files in os.walk(SNAP):
        json_files = [x for x in files if x.endswith(".json")]
        if len(json_files) < 2:
            continue

        old_path, new_path = latest_two(root)
        if not old_path or not new_path:
            continue

        with open(old_path, encoding="utf-8") as f:
            old = json.load(f)
        with open(new_path, encoding="utf-8") as f:
            new = json.load(f)

        result = compare(old, new)
        if result["changed"]:
            changes.append({
                "brand": new["brand"],
                "market": new["market"],
                "category": new["category"],
                "pageType": new["pageType"],
                "url": new["url"],
                "capturedAt": new["capturedAt"],
                **result
            })

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(changes, f, ensure_ascii=False, indent=2)

    print(f"Page changes detected: {len(changes)}")

if __name__ == "__main__":
    main()
