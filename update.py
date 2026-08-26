import os, json, datetime as dt, re, hashlib
import requests, feedparser
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime

BASE = os.path.dirname(__file__)
DATA = os.path.join(BASE, 'data.json')
PAGE_CHANGES = os.path.join(BASE, 'page_changes.json')
PAGE_INVENTORY = os.path.join(BASE, 'page_inventory.json')
H = {'User-Agent': 'Mozilla/5.0 (3C Content Intelligence Hub/3.0)'}

FEEDS = [
    ('Apple','Global','Official','https://www.apple.com/newsroom/rss-feed.rss'),
    ('Samsung','Global','Discovery','https://news.google.com/rss/search?q=site%3Anews.samsung.com%2Fglobal%20Samsung%20Galaxy%20Watch%20OR%20wearable%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen'),
    ('Samsung','Malaysia','Discovery','https://news.google.com/rss/search?q=site%3Anews.samsung.com%2Fmy%20Galaxy%20Watch%20OR%20wearable%20when%3A1d&hl=en-US&gl=MY&ceid=MY%3Aen'),
    ('Samsung','UK','Discovery','https://news.google.com/rss/search?q=site%3Anews.samsung.com%2Fuk%20Galaxy%20Watch%20OR%20wearable%20when%3A1d&hl=en-US&gl=GB&ceid=GB%3Aen'),
    ('Garmin','Global','Discovery','https://news.google.com/rss/search?q=site%3Agarmin.com%20Garmin%20watch%20OR%20wearable%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen'),
    ('Garmin','Malaysia','Discovery','https://news.google.com/rss/search?q=site%3Agarmin.com.my%20Garmin%20watch%20OR%20wearable%20when%3A7d&hl=en-US&gl=MY&ceid=MY%3Aen'),
    ('Garmin','UK','Discovery','https://news.google.com/rss/search?q=site%3Agarmin.com%2Fen-GB%20Garmin%20watch%20OR%20wearable%20when%3A7d&hl=en-US&gl=GB&ceid=GB%3Aen'),
]


def pdate(e):
    for k in ('published','updated'):
        if e.get(k):
            try:
                return parsedate_to_datetime(e[k]).isoformat()
            except Exception:
                pass
    return dt.datetime.now(dt.timezone.utc).isoformat()


def fetch():
    out, seen = [], set()
    for brand, market, kind, url in FEEDS:
        try:
            r = requests.get(url, headers=H, timeout=15)
            feed = feedparser.parse(r.content)
            for e in feed.entries[:15]:
                title = BeautifulSoup(e.get('title',''), 'html.parser').get_text(' ', strip=True)
                summary = BeautifulSoup(e.get('summary',''), 'html.parser').get_text(' ', strip=True)
                link = e.get('link','')
                key = hashlib.sha1((brand+market+title).lower().encode()).hexdigest()
                if key not in seen:
                    seen.add(key)
                    out.append({'brand':brand,'market':market,'source_kind':kind,'title':title,'summary':summary[:900],'url':link,'published':pdate(e)})
        except Exception as ex:
            print('feed error', brand, market, ex)
    return out


def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def ai(items, changes, inventory):
    key = os.getenv('DASHSCOPE_API_KEY') or os.getenv('OPENAI_API_KEY')
    if not key:
        print('DASHSCOPE_API_KEY / OPENAI_API_KEY is not configured. Skipping AI analysis.')
        return None

    from openai import OpenAI
    client = OpenAI(
        api_key=key,
        base_url=os.getenv('DASHSCOPE_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
    )
    model = os.getenv('QWEN_MODEL', 'qwen3.5-plus')

    # Keep the payload compact enough to control daily token usage.
    page_changes = changes[:80]
    feed_items = items[:80]
    page_inventory_summary = {
        'total': len(inventory),
        'byBrand': {},
        'byMarket': {},
        'byPageType': {},
    }
    for x in inventory:
        b, m, t = x.get('brand',''), x.get('market',''), x.get('pageType','')
        page_inventory_summary['byBrand'][b] = page_inventory_summary['byBrand'].get(b,0)+1
        page_inventory_summary['byMarket'][m] = page_inventory_summary['byMarket'].get(m,0)+1
        page_inventory_summary['byPageType'][t] = page_inventory_summary['byPageType'].get(t,0)+1

    prompt = f'''You are the daily 3C competitive content intelligence analyst for HUAWEI overseas e-commerce and content operations.

Scope: Apple, Samsung and Garmin only. Focus ONLY on wearables and smartwatches. Markets: Global, Malaysia and UK.

IMPORTANT: Do NOT produce a standalone SEO section. Prioritise:
1) new product/content production and product storytelling;
2) marketing launches, campaigns and creative formats;
3) PDP/PCP structure changes and shopper-facing messaging;
4) feature emphasis, modules, CTAs, comparison, video, scenario storytelling, ecosystem and AI/health/fitness/audio narratives;
5) concrete implications and actions for HUAWEI.

Source facts must be traceable to the supplied URLs. Do not invent metrics or claim a change unless the page-diff data supports it. Strategic implications are analysis, not facts.

Return ONLY valid JSON in this schema:
{{
  "signals":[{{"brand":"","market":"","type":"PRODUCT|MARKETING|PDP|PCP|CONTENT","priority":"HIGH|MEDIUM|LOW","title":"","summary":"","implication":"","url":""}}],
  "actions":[{{"priority":"P1|P2|P3","action":"","why":"","examples":""}}],
  "contentMix":[{{"brand":"","education":0,"campaign":0,"product":0,"scenario":0,"ai":0}}],
  "pageChanges":[{{"brand":"","market":"","category":"","pageType":"PDP|PCP","title":"","change":"","before":"","after":"","implication":"","priority":"HIGH|MEDIUM|LOW","url":""}}]
}}

PAGE INVENTORY SUMMARY:
{json.dumps(page_inventory_summary, ensure_ascii=False)}

VERIFIED PAGE CHANGES:
{json.dumps(page_changes, ensure_ascii=False)}

RECENT DISCOVERY / NEWS ITEMS:
{json.dumps(feed_items, ensure_ascii=False)}

Keep up to 12 signals, 10 actions and 15 pageChanges. If there are no verified page changes, return an empty pageChanges array.''' 

    res = client.responses.create(model=model, input=prompt)
    txt = re.sub(r'^```(?:json)?\s*|\s*```$', '', res.output_text.strip(), flags=re.S)
    result = json.loads(txt)
    return result


def main():
    print('=== 3C Content Intelligence Hub V4 — Wearables ===')
    items = fetch()
    changes = load_json(PAGE_CHANGES, [])
    inventory = load_json(PAGE_INVENTORY, [])
    print(f'Fetched {len(items)} unique feed items.')
    print(f'Page inventory: {len(inventory)} pages; verified changes: {len(changes)}.')

    result = ai(items, changes, inventory)
    now = dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat()

    if result:
        result['updatedAt'] = now
        result['timezone'] = 'Asia/Kuala_Lumpur'
        result['feedItems'] = items[:100]
        result['pageInventory'] = inventory
        result['pageChangesRaw'] = changes
        result['monitoring'] = {
            'brands': ['Apple','Samsung','Garmin'],
            'markets': ['Global','Malaysia','UK'],
            'categories': ['Wearables'],
            'scope': 'PDP and PCP monitoring',
            'inventoryCount': len(inventory),
            'verifiedChangeCount': len(changes),
        }
        old = load_json(DATA, {})
        result['sourceHealth'] = old.get('sourceHealth', [])
        with open(DATA, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print('AI analysis completed successfully.')
    else:
        old = load_json(DATA, {})
        old['updatedAt'] = now
        old['feedItems'] = items[:100]
        old['pageInventory'] = inventory
        old['pageChangesRaw'] = changes
        with open(DATA, 'w', encoding='utf-8') as f:
            json.dump(old, f, ensure_ascii=False, indent=2)
        print('AI analysis skipped; monitoring data preserved.')


if __name__ == '__main__':
    main()
