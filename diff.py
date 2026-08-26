import os, json, glob

BASE = os.path.dirname(__file__)
SNAP = os.path.join(BASE, 'snapshots')
OUT = os.path.join(BASE, 'page_changes.json')


def latest_by_day(folder):
    files = sorted(glob.glob(os.path.join(folder, '*.json')))
    by_day = {}
    for f in files:
        name = os.path.basename(f)
        if '_' not in name:
            continue
        day = name.rsplit('_', 1)[-1].replace('.json', '')
        by_day.setdefault(day, []).append(f)
    days = sorted(by_day)
    if len(days) < 2:
        return None, None
    return sorted(by_day[days[-2]])[0], sorted(by_day[days[-1]])[0]


def compare(old, new):
    fields = ['title', 'h1', 'headings', 'buttons', 'videos', 'modules', 'textHash']
    changed = [f for f in fields if old.get(f) != new.get(f)]
    old_modules = set(old.get('modules', []))
    new_modules = set(new.get('modules', []))
    old_heads = set(old.get('headings', []))
    new_heads = set(new.get('headings', []))
    return {
        'changed': bool(changed),
        'fieldsChanged': changed,
        'addedModules': sorted(new_modules - old_modules),
        'removedModules': sorted(old_modules - new_modules),
        'addedHeadings': sorted(new_heads - old_heads)[:30],
        'removedHeadings': sorted(old_heads - new_heads)[:30],
        'videoDelta': {
            'added': max(0, len(new.get('videos', [])) - len(old.get('videos', []))),
            'removed': max(0, len(old.get('videos', [])) - len(new.get('videos', [])))
        },
        'oldTitle': old.get('title', ''),
        'newTitle': new.get('title', ''),
        'oldH1': old.get('h1', ''),
        'newH1': new.get('h1', ''),
    }


def main():
    changes = []
    if not os.path.exists(SNAP):
        print('No snapshots directory found.')
        with open(OUT, 'w', encoding='utf-8') as f: json.dump([], f)
        return

    for root, _, files in os.walk(SNAP):
        if len([x for x in files if x.endswith('.json')]) < 2:
            continue
        old_path, new_path = latest_by_day(root)
        if not old_path or not new_path:
            continue
        try:
            with open(old_path, encoding='utf-8') as f: old = json.load(f)
            with open(new_path, encoding='utf-8') as f: new = json.load(f)
        except Exception as ex:
            print('diff read error', root, ex)
            continue
        result = compare(old, new)
        if result['changed']:
            changes.append({
                'brand': new.get('brand',''),
                'market': new.get('market',''),
                'category': new.get('category',''),
                'pageType': new.get('pageType',''),
                'title': new.get('title',''),
                'url': new.get('url',''),
                'capturedAt': new.get('capturedAt',''),
                **result
            })

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(changes, f, ensure_ascii=False, indent=2)
    print(f'Page changes detected: {len(changes)}')


if __name__ == '__main__': main()
