import os, json, re, hashlib
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag
import requests
from bs4 import BeautifulSoup

BASE = os.path.dirname(__file__)
CONFIG = os.path.join(BASE, "competitors.json")
SNAP = os.path.join(BASE, "snapshots")
OUT = os.path.join(BASE, "page_inventory.json")

HEADERS = {"User-Agent": "Mozilla/5.0 (3C Content Intelligence Hub/2.1; +https://github.com/xphoeliu-sudo/3c-content-intelligence-hub)"}
TIMEOUT = 25
MAX_PDP_PER_PCP = 12
MIN_TEXT = 250

# Generic URL signals. This is deliberately conservative.
PDP_HINTS = [
    "/shop/", "/buy/", "/products/", "/product/", "/p/", "/watch-", "/iphone-",
    "/ipad-", "/airpods", "/galaxy-s", "/galaxy-z", "/galaxy-watch",
    "/galaxy-buds", "/galaxy-tab", "/forerunner", "/fenix", "/venu", "/vivoactive",
    "/epix", "/marq", "/instinct", "/descent", "/lily", "/approach"
]
BAD_HINTS = [
    "/support", "/newsroom", "/blog", "/community", "/accessories",
    "/compare", "/comparison", "/service", "/repair", "/search", "/help"
]

def norm(url):
    url, _ = urldefrag(url)
    return url.rstrip("/")

def same_domain(a, b):
    return urlparse(a).netloc.lower().replace("www.", "") == urlparse(b).netloc.lower().replace("www.", "")

def get(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    return r.url, r.text

def visible_text(soup):
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    return " ".join(soup.stripped_strings)

def candidate_score(url, anchor_text):
    u = url.lower()
    score = 0
    if any(x in u for x in PDP_HINTS): score += 3
    if any(x in u for x in BAD_HINTS): score -= 5
    if re.search(r"/[a-z0-9-]{5,}$", u): score += 1
    if anchor_text and len(anchor_text.strip()) > 5: score += 1
    return score

def discover_pdp(pcp_url, html):
    soup = BeautifulSoup(html, "html.parser")
    candidates = {}
    for a in soup.find_all("a", href=True):
        href = norm(urljoin(pcp_url, a["href"]))
        if not href.startswith(("http://", "https://")) or not same_domain(pcp_url, href):
            continue
        text = " ".join(a.stripped_strings)
        score = candidate_score(href, text)
        if score >= 3:
            candidates[href] = max(candidates.get(href, 0), score)
    return [u for u, _ in sorted(candidates.items(), key=lambda x: (-x[1], x[0]))][:MAX_PDP_PER_PCP]

def extract_snapshot(url, html, brand, market, category, page_type):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1 = " ".join(soup.h1.stripped_strings) if soup.h1 else ""
    headings = []
    for h in soup.find_all(["h1","h2","h3"]):
        t = " ".join(h.stripped_strings)
        if t and t not in headings:
            headings.append(t[:300])

    buttons = []
    for el in soup.find_all(["button", "a"]):
        t = " ".join(el.stripped_strings)
        if t and len(t) <= 120 and any(k in t.lower() for k in [
            "buy","shop","learn","compare","add","order","discover","explore",
            "purchase","compare","view","more","选购","购买","了解","比较"
        ]):
            if t not in buttons:
                buttons.append(t)

    videos = []
    for v in soup.find_all(["video", "iframe"]):
        src = v.get("src") or v.get("data-src") or ""
        if src:
            videos.append(norm(urljoin(url, src)))

    images = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
        if src:
            images.append(norm(urljoin(url, src)))

    text = visible_text(BeautifulSoup(html, "html.parser"))
    text = re.sub(r"\s+", " ", text).strip()

    # Lightweight module fingerprint based on headings/semantic blocks.
    modules = []
    for h in headings:
        low = h.lower()
        if any(k in low for k in ["compare", "comparison", "比较"]): modules.append("comparison")
        elif any(k in low for k in ["faq", "frequently asked", "常见问题"]): modules.append("faq")
        elif any(k in low for k in ["health", "fitness", "健康", "运动"]): modules.append("health_fitness")
        elif any(k in low for k in ["battery", "电池", "续航"]): modules.append("battery")
        elif any(k in low for k in ["camera", "相机", "摄影"]): modules.append("camera")
        elif any(k in low for k in ["ai", "智能", "人工智能"]): modules.append("ai")
        elif any(k in low for k in ["design", "display", "屏幕", "设计"]): modules.append("design_display")
        elif any(k in low for k in ["accessor", "配件"]): modules.append("accessories")
        elif any(k in low for k in ["connect", "生态", "ecosystem"]): modules.append("ecosystem")
        else: modules.append("content")
    modules = list(dict.fromkeys(modules))

    return {
        "url": norm(url),
        "brand": brand,
        "market": market,
        "category": category,
        "pageType": page_type,
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "title": title[:500],
        "h1": h1[:500],
        "headings": headings[:120],
        "buttons": buttons[:80],
        "videos": videos[:80],
        "images": images[:120],
        "modules": modules,
        "text": text[:30000],
        "textHash": hashlib.sha1(text.encode("utf-8")).hexdigest(),
    }

def save_snapshot(item):
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = hashlib.sha1(item["url"].encode("utf-8")).hexdigest()[:16]
    folder = os.path.join(SNAP, item["brand"], item["market"], item["category"])
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{slug}_{day}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)

def main():
    with open(CONFIG, encoding="utf-8") as f:
        config = json.load(f)

    inventory = []
    for brand, markets in config.items():
        for market, cats in markets.items():
            for category, pcp_urls in cats.items():
                for pcp_url in pcp_urls:
                    try:
                        final_url, html = get(pcp_url)
                        pcp = extract_snapshot(final_url, html, brand, market, category, "PCP")
                        save_snapshot(pcp)
                        inventory.append({"brand": brand, "market": market, "category": category, "pageType": "PCP", "url": final_url})

                        for pdp_url in discover_pdp(final_url, html):
                            try:
                                final_pdp, pdp_html = get(pdp_url)
                                text = visible_text(BeautifulSoup(pdp_html, "html.parser"))
                                if len(text) < MIN_TEXT:
                                    continue
                                pdp = extract_snapshot(final_pdp, pdp_html, brand, market, category, "PDP")
                                save_snapshot(pdp)
                                inventory.append({"brand": brand, "market": market, "category": category, "pageType": "PDP", "url": final_pdp})
                            except Exception as ex:
                                print("PDP error:", brand, market, category, pdp_url, ex)
                    except Exception as ex:
                        print("PCP error:", brand, market, category, pcp_url, ex)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(inventory, f, ensure_ascii=False, indent=2)

    print(f"Page monitoring completed. Inventory: {len(inventory)} pages.")

if __name__ == "__main__":
    main()
