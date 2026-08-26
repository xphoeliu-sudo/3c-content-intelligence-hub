import os
import json
import re
import hashlib
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup


BASE = os.path.dirname(__file__)
CONFIG = os.path.join(BASE, "competitors.json")
SNAP = os.path.join(BASE, "snapshots")
OUT = os.path.join(BASE, "page_inventory.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 15

# 第一轮测试只跑 Malaysia + UK
TEST_MARKETS = {"Malaysia", "UK"}

# 每个 PCP 最多发现 3 个 PDP
MAX_PDP_PER_PCP = 3

# 页面正文太短时，不认为是有效 PDP
MIN_TEXT_LENGTH = 250


PDP_HINTS = [
    "/shop/",
    "/buy/",
    "/products/",
    "/product/",
    "/p/",
    "/watch-",
    "/iphone-",
    "/ipad-",
    "/airpods",
    "/galaxy-s",
    "/galaxy-z",
    "/galaxy-watch",
    "/galaxy-buds",
    "/galaxy-tab",
    "/forerunner",
    "/fenix",
    "/venu",
    "/vivoactive",
    "/epix",
    "/marq",
    "/instinct",
    "/descent",
    "/lily",
    "/approach",
]

BAD_HINTS = [
    "/support",
    "/newsroom",
    "/blog",
    "/community",
    "/accessories",
    "/compare",
    "/comparison",
    "/service",
    "/repair",
    "/search",
    "/help",
]


def normalise_url(url):
    url, _ = urldefrag(url)
    return url.rstrip("/")


def same_domain(url_a, url_b):
    a = urlparse(url_a).netloc.lower().replace("www.", "")
    b = urlparse(url_b).netloc.lower().replace("www.", "")
    return a == b


def fetch_page(url):
    print(f"[REQUEST] {url}")

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    print(
        f"[OK] {response.status_code} "
        f"{response.url} "
        f"({len(response.text)} chars)"
    )

    return response.url, response.text


def clean_text(soup):
    soup = BeautifulSoup(str(soup), "html.parser")

    for tag in soup(
        ["script", "style", "noscript", "svg", "template"]
    ):
        tag.decompose()

    text = " ".join(soup.stripped_strings)

    return re.sub(r"\s+", " ", text).strip()


def score_candidate(url, anchor_text):
    url_lower = url.lower()

    score = 0

    if any(x in url_lower for x in PDP_HINTS):
        score += 3

    if any(x in url_lower for x in BAD_HINTS):
        score -= 5

    if anchor_text and len(anchor_text.strip()) > 5:
        score += 1

    if re.search(r"/[a-z0-9-]{5,}$", url_lower):
        score += 1

    return score


def discover_pdp_urls(pcp_url, html):
    soup = BeautifulSoup(html, "html.parser")

    candidates = {}

    for a in soup.find_all("a", href=True):

        href = normalise_url(
            urljoin(pcp_url, a["href"])
        )

        if not href.startswith(("http://", "https://")):
            continue

        if not same_domain(pcp_url, href):
            continue

        anchor_text = " ".join(a.stripped_strings)

        score = score_candidate(
            href,
            anchor_text
        )

        if score >= 3:

            if href not in candidates:
                candidates[href] = score

            else:
                candidates[href] = max(
                    candidates[href],
                    score
                )

    sorted_candidates = sorted(
        candidates.items(),
        key=lambda x: (-x[1], x[0])
    )

    results = [
        url
        for url, score in sorted_candidates
    ]

    return results[:MAX_PDP_PER_PCP]


def extract_page_snapshot(
    url,
    html,
    brand,
    market,
    category,
    page_type
):

    soup = BeautifulSoup(html, "html.parser")

    title = ""

    if soup.title:
        title = soup.title.get_text(
            " ",
            strip=True
        )

    h1 = ""

    if soup.h1:
        h1 = " ".join(
            soup.h1.stripped_strings
        )

    headings = []

    for heading in soup.find_all(
        ["h1", "h2", "h3"]
    ):

        text = " ".join(
            heading.stripped_strings
        )

        if text and text not in headings:
            headings.append(text[:300])

    buttons = []

    keywords = [
        "buy",
        "shop",
        "learn",
        "compare",
        "add",
        "order",
        "discover",
        "explore",
        "purchase",
        "view",
        "more",
        "购买",
        "选购",
        "了解",
        "比较",
    ]

    for element in soup.find_all(
        ["button", "a"]
    ):

        text = " ".join(
            element.stripped_strings
        )

        if not text:
            continue

        if len(text) > 120:
            continue

        lower = text.lower()

        if any(
            keyword in lower
            for keyword in keywords
        ):

            if text not in buttons:
                buttons.append(text)

    videos = []

    for element in soup.find_all(
        ["video", "iframe"]
    ):

        source = (
            element.get("src")
            or element.get("data-src")
            or ""
        )

        if source:

            videos.append(
                normalise_url(
                    urljoin(url, source)
                )
            )

    images = []

    for image in soup.find_all("img"):

        source = (
            image.get("src")
            or image.get("data-src")
            or image.get("data-lazy-src")
            or ""
        )

        if source:

            images.append(
                normalise_url(
                    urljoin(url, source)
                )
            )

    text = clean_text(soup)

    modules = []

    for heading in headings:

        lower = heading.lower()

        if any(
            x in lower
            for x in [
                "compare",
                "comparison",
                "比较"
            ]
        ):
            modules.append("comparison")

        elif any(
            x in lower
            for x in [
                "faq",
                "frequently asked",
                "常见问题"
            ]
        ):
            modules.append("faq")

        elif any(
            x in lower
            for x in [
                "health",
                "fitness",
                "健康",
                "运动"
            ]
        ):
            modules.append("health_fitness")

        elif any(
            x in lower
            for x in [
                "battery",
                "电池",
                "续航"
            ]
        ):
            modules.append("battery")

        elif any(
            x in lower
            for x in [
                "camera",
                "相机",
                "摄影"
            ]
        ):
            modules.append("camera")

        elif any(
            x in lower
            for x in [
                "ai",
                "artificial intelligence",
                "智能",
                "人工智能"
            ]
        ):
            modules.append("ai")

        elif any(
            x in lower
            for x in [
                "design",
                "display",
                "屏幕",
                "设计"
            ]
        ):
            modules.append("design_display")

        elif any(
            x in lower
            for x in [
                "accessor",
                "配件"
            ]
        ):
            modules.append("accessories")

        elif any(
            x in lower
            for x in [
                "connect",
                "ecosystem",
                "生态"
            ]
        ):
            modules.append("ecosystem")

        else:
            modules.append("content")

    modules = list(
        dict.fromkeys(modules)
    )

    return {
        "url": normalise_url(url),
        "brand": brand,
        "market": market,
        "category": category,
        "pageType": page_type,
        "capturedAt": datetime.now(
            timezone.utc
        ).isoformat(),

        "title": title[:500],
        "h1": h1[:500],

        "headings": headings[:100],
        "buttons": buttons[:50],

        "videos": videos[:50],
        "images": images[:100],

        "modules": modules,

        "text": text[:30000],

        "textHash": hashlib.sha1(
            text.encode("utf-8")
        ).hexdigest(),
    }


def save_snapshot(snapshot):

    today = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d")

    url_hash = hashlib.sha1(
        snapshot["url"].encode("utf-8")
    ).hexdigest()[:16]

    folder = os.path.join(
        SNAP,
        snapshot["brand"],
        snapshot["market"],
        snapshot["category"]
    )

    os.makedirs(
        folder,
        exist_ok=True
    )

    filename = (
        f"{url_hash}_{today}.json"
    )

    path = os.path.join(
        folder,
        filename
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            snapshot,
            f,
            ensure_ascii=False,
            indent=2
        )


def main():

    print(
        "=== 3C PDP / PCP Monitor V2.1 Test ==="
    )

    print(
        "Markets:",
        ", ".join(TEST_MARKETS)
    )

    print(
        "Max PDP per PCP:",
        MAX_PDP_PER_PCP
    )

    with open(
        CONFIG,
        encoding="utf-8"
    ) as f:

        config = json.load(f)

    inventory = []

    for brand, markets in config.items():

        if brand not in [
            "Apple",
            "Samsung",
            "Garmin"
        ]:
            continue

        for market, categories in markets.items():

            if market not in TEST_MARKETS:
                continue

            for category, pcp_urls in categories.items():

                for pcp_url in pcp_urls:

                    print()
                    print(
                        "================================"
                    )

                    print(
                        f"[PCP] {brand} | "
                        f"{market} | "
                        f"{category}"
                    )

                    try:

                        final_url, html = fetch_page(
                            pcp_url
                        )

                        pcp_snapshot = (
                            extract_page_snapshot(
                                final_url,
                                html,
                                brand,
                                market,
                                category,
                                "PCP"
                            )
                        )

                        save_snapshot(
                            pcp_snapshot
                        )

                        inventory.append({
                            "brand": brand,
                            "market": market,
                            "category": category,
                            "pageType": "PCP",
                            "url": final_url
                        })

                        pdp_urls = (
                            discover_pdp_urls(
                                final_url,
                                html
                            )
                        )

                        print(
                            f"[DISCOVERED] "
                            f"{len(pdp_urls)} PDP candidates"
                        )

                        for pdp_url in pdp_urls:

                            print(
                                f"[PDP] {pdp_url}"
                            )

                            try:

                                (
                                    final_pdp_url,
                                    pdp_html
                                ) = fetch_page(
                                    pdp_url
                                )

                                text = clean_text(
                                    BeautifulSoup(
                                        pdp_html,
                                        "html.parser"
                                    )
                                )

                                if len(text) < MIN_TEXT_LENGTH:

                                    print(
                                        "[SKIP] "
                                        "Page text too short"
                                    )

                                    continue

                                snapshot = (
                                    extract_page_snapshot(
                                        final_pdp_url,
                                        pdp_html,
                                        brand,
                                        market,
                                        category,
                                        "PDP"
                                    )
                                )

                                save_snapshot(
                                    snapshot
                                )

                                inventory.append({
                                    "brand": brand,
                                    "market": market,
                                    "category": category,
                                    "pageType": "PDP",
                                    "url": final_pdp_url
                                })

                            except Exception as error:

                                print(
                                    "[PDP ERROR]",
                                    pdp_url,
                                    error
                                )

                    except Exception as error:

                        print(
                            "[PCP ERROR]",
                            brand,
                            market,
                            category,
                            error
                        )

                        # 关键：
                        # 一个页面失败，不影响后面的页面。
                        continue

    with open(
        OUT,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            inventory,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print(
        "================================"
    )

    print(
        f"Page monitoring completed."
    )

    print(
        f"Inventory: {len(inventory)} pages."
    )


if __name__ == "__main__":
    main()
