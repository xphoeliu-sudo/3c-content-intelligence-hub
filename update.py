import os
import json
import datetime as dt
import re
import hashlib

import requests
import feedparser
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime


BASE = os.path.dirname(__file__)
DATA = os.path.join(BASE, "data.json")

H = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/147.0 Safari/537.36 "
        "3C-Wearables-Intelligence/4.0"
    )
}

QWEN_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1"
)

QWEN_MODEL = os.getenv(
    "QWEN_MODEL",
    "qwen3.5-plus"
)

MAX_AI_ITEMS = 60
MAX_FEED_ITEMS = 100
MAX_PDP_PAGES = 6


# ============================================================
# WEARABLE CONTENT KEYWORDS
# ============================================================

WEARABLE_KEYWORDS = [
    "apple watch",
    "watch series",
    "watch se",
    "watch ultra",
    "galaxy watch",
    "galaxy watch ultra",
    "galaxy watch classic",
    "garmin watch",
    "garmin smartwatch",
    "fēnix",
    "fenix",
    "forerunner",
    "venu",
    "instinct",
    "vívoactive",
    "vivoactive",
    "tactix",
    "quatix",
    "enduro",
    "lily",
    "smartwatch",
    "smart watch",
    "wearable",
    "fitness watch",
    "sports watch",
    "gps watch",
    "health watch",
    "running watch",
    "fitness tracker",
    "watchos",
    "wear os",
    "galaxy wearable",
]


def is_wearable(title, summary=""):

    text = (
        (title or "") +
        " " +
        (summary or "")
    ).lower()

    return any(
        keyword.lower() in text
        for keyword in WEARABLE_KEYWORDS
    )


# ============================================================
# FEEDS
# ============================================================

FEEDS = [

    # ---------------- Apple ----------------

    (
        "Apple",
        "Global",
        "Official",
        "https://www.apple.com/newsroom/rss-feed.rss",
    ),

    (
        "Apple",
        "Malaysia",
        "Official",
        "https://www.apple.com/my/newsroom/rss-feed.rss",
    ),

    # ---------------- Samsung ----------------

    (
        "Samsung",
        "Global",
        "Discovery",
        "https://news.google.com/rss/search?q="
        "site%3Anews.samsung.com%2Fglobal "
        "(Galaxy%20Watch%20OR%20wearable%20OR%20smartwatch)"
        "%20when%3A7d"
        "&hl=en-US&gl=US&ceid=US%3Aen",
    ),

    (
        "Samsung",
        "Malaysia",
        "Discovery",
        "https://news.google.com/rss/search?q="
        "site%3Anews.samsung.com%2Fmy "
        "(Galaxy%20Watch%20OR%20wearable%20OR%20smartwatch)"
        "%20when%3A7d"
        "&hl=en-US&gl=MY&ceid=MY%3Aen",
    ),

    (
        "Samsung",
        "UK",
        "Discovery",
        "https://news.google.com/rss/search?q="
        "Samsung%20Galaxy%20Watch%20UK"
        "%20when%3A7d"
        "&hl=en-GB&gl=GB&ceid=GB%3Aen",
    ),

    (
        "Samsung",
        "Germany",
        "Discovery",
        "https://news.google.com/rss/search?q="
        "Samsung%20Galaxy%20Watch%20Germany"
        "%20when%3A7d"
        "&hl=de&gl=DE&ceid=DE%3Ade",
    ),

    # ---------------- Garmin ----------------

    (
        "Garmin",
        "Global",
        "Discovery",
        "https://news.google.com/rss/search?q="
        "site%3Agarmin.com "
        "(Garmin%20watch%20OR%20smartwatch%20OR%20fēnix%20OR%20Forerunner%20OR%20Venu)"
        "%20when%3A7d"
        "&hl=en-US&gl=US&ceid=US%3Aen",
    ),

    (
        "Garmin",
        "Malaysia",
        "Discovery",
        "https://news.google.com/rss/search?q="
        "Garmin%20Malaysia%20watch"
        "%20when%3A7d"
        "&hl=en-US&gl=MY&ceid=MY%3Aen",
    ),

    (
        "Garmin",
        "UK",
        "Discovery",
        "https://news.google.com/rss/search?q="
        "Garmin%20UK%20watch"
        "%20when%3A7d"
        "&hl=en-GB&gl=GB&ceid=GB%3Aen",
    ),

    (
        "Garmin",
        "Germany",
        "Discovery",
        "https://news.google.com/rss/search?q="
        "Garmin%20Germany%20watch"
        "%20when%3A7d"
        "&hl=de&gl=DE&ceid=DE%3Ade",
    ),
]


# ============================================================
# OFFICIAL WEARABLE PAGES
# ============================================================

PDP_PAGES = [

    {
        "brand": "Apple",
        "market": "Malaysia",
        "pageType": "Wearables category",
        "url": "https://www.apple.com/my/watch/",
    },

    {
        "brand": "Apple",
        "market": "Malaysia",
        "pageType": "E-commerce lineup",
        "url": "https://www.apple.com/my/shop/buy-watch",
    },

    {
        "brand": "Samsung",
        "market": "Malaysia",
        "pageType": "Wearables category",
        "url": "https://www.samsung.com/my/watches/",
    },

    {
        "brand": "Samsung",
        "market": "Malaysia",
        "pageType": "Galaxy Watch category",
        "url": "https://www.samsung.com/my/watches/galaxy-watch/",
    },

    {
        "brand": "Garmin",
        "market": "Global",
        "pageType": "Smartwatch category",
        "url": "https://www.garmin.com/en-US/c/wearables-smartwatches/",
    },
]


# ============================================================
# HELPERS
# ============================================================

def pdate(e):

    for k in ("published", "updated"):

        if e.get(k):

            try:
                return parsedate_to_datetime(
                    e[k]
                ).isoformat()

            except Exception:
                pass

    return dt.datetime.now(
        dt.timezone.utc
    ).isoformat()


def clean_text(text):

    return BeautifulSoup(
        text or "",
        "html.parser"
    ).get_text(
        " ",
        strip=True
    )


def normalise_space(text):

    return re.sub(
        r"\s+",
        " ",
        text or ""
    ).strip()


def hash_text(text):

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


# ============================================================
# FEED FETCH
# ============================================================

def fetch():

    out = []
    seen = set()

    for brand, market, kind, url in FEEDS:

        try:

            r = requests.get(
                url,
                headers=H,
                timeout=20
            )

            r.raise_for_status()

            feed = feedparser.parse(
                r.content
            )

            for e in feed.entries[:20]:

                title = clean_text(
                    e.get("title", "")
                )

                summary = clean_text(
                    e.get("summary", "")
                )

                link = e.get(
                    "link",
                    ""
                )

                # ----------------------------------------
                # Wearables only
                # ----------------------------------------

                if not is_wearable(
                    title,
                    summary
                ):
                    continue

                key = hashlib.sha1(
                    (
                        brand +
                        market +
                        title
                    ).lower().encode(
                        "utf-8"
                    )
                ).hexdigest()

                if key in seen:
                    continue

                seen.add(key)

                out.append(
                    {
                        "brand": brand,
                        "market": market,
                        "source_kind": kind,
                        "title": title,
                        "summary": summary[:1000],
                        "url": link,
                        "published": pdate(e),
                    }
                )

        except Exception as ex:

            print(
                "feed error:",
                brand,
                market,
                str(ex)
            )

    print(
        f"Fetched {len(out)} unique "
        f"wearables feed items."
    )

    return out


# ============================================================
# PDP FETCH
# ============================================================

def fetch_pdp_pages():

    results = []

    for page in PDP_PAGES[:MAX_PDP_PAGES]:

        try:

            r = requests.get(
                page["url"],
                headers=H,
                timeout=25
            )

            r.raise_for_status()

            soup = BeautifulSoup(
                r.text,
                "html.parser"
            )

            # Remove non-content elements
            for tag in soup([
                "script",
                "style",
                "noscript",
                "svg"
            ]):
                tag.decompose()

            text = soup.get_text(
                " ",
                strip=True
            )

            text = normalise_space(
                text
            )

            # Keep the snapshot reasonably small
            text = text[:30000]

            results.append(
                {
                    "brand": page["brand"],
                    "market": page["market"],
                    "pageType": page["pageType"],
                    "url": page["url"],
                    "contentHash": hash_text(text),
                    "text": text,
                }
            )

            print(
                "PDP fetched:",
                page["brand"],
                page["market"],
                page["pageType"]
            )

        except Exception as ex:

            print(
                "PDP error:",
                page["brand"],
                page["url"],
                str(ex)
            )

    print(
        f"Fetched {len(results)} monitored PDP pages."
    )

    return results


# ============================================================
# PDP DIFF
# ============================================================

def create_pdp_changes(
    current_pages,
    old_data
):

    old_pages = {
        x.get("url"): x
        for x in old_data.get(
            "pdpSnapshots",
            []
        )
    }

    changes = []

    for current in current_pages:

        old = old_pages.get(
            current["url"]
        )

        if not old:

            # First run:
            # establish baseline but don't
            # claim that this is a change.
            continue

        if (
            old.get("contentHash")
            ==
            current.get("contentHash")
        ):
            continue

        old_text = old.get(
            "text",
            ""
        )

        new_text = current.get(
            "text",
            ""
        )

        old_words = set(
            old_text.split()
        )

        new_words = set(
            new_text.split()
        )

        added = list(
            new_words - old_words
        )

        removed = list(
            old_words - new_words
        )

        # Keep diff compact for AI
        added_text = " ".join(
            added[:250]
        )

        removed_text = " ".join(
            removed[:250]
        )

        changes.append(
            {
                "brand": current["brand"],
                "market": current["market"],
                "pageType": current["pageType"],
                "url": current["url"],
                "changeDetected": True,
                "addedText": added_text,
                "removedText": removed_text,
            }
        )

    print(
        f"Detected {len(changes)} PDP changes."
    )

    return changes


# ============================================================
# AI ANALYSIS
# ============================================================

def ai(
    items,
    pdp_changes
):

    from openai import OpenAI

    key = os.getenv(
        "DASHSCOPE_API_KEY"
    )

    if not key:

        print(
            "DASHSCOPE_API_KEY is not configured. "
            "Skipping AI analysis."
        )

        return None

    ai_items = items[
        :MAX_AI_ITEMS
    ]

    client = OpenAI(
        api_key=key,
        base_url=QWEN_BASE_URL,
    )

    prompt = f"""
You are a senior competitive content intelligence analyst
supporting HUAWEI overseas wearable product marketing,
e-commerce and content operations.

IMPORTANT SCOPE

This intelligence report is ONLY about wearables:

- smartwatches
- sports watches
- fitness watches
- health watches
- wearable health products

Prioritise:

1. Apple
2. Samsung
3. Garmin

The goal is NOT to create a technology news summary.

The goal is to understand:

WHAT competitors are doing
→ HOW they communicate it
→ WHAT changed in their product/e-commerce storytelling
→ WHY it matters
→ WHAT HUAWEI should learn or do

Use professional British English.

Return ONLY valid JSON.

Use exactly this structure:

{{
  "signals": [
    {{
      "brand": "",
      "market": "",
      "type": "PRODUCT|MARKETING|ECOMMERCE|CONTENT",
      "priority": "HIGH|MEDIUM|LOW",
      "title": "",
      "summary": "",
      "implication": "",
      "url": ""
    }}
  ],

  "actions": [
    {{
      "priority": "P1|P2|P3",
      "action": "",
      "why": "",
      "examples": ""
    }}
  ],

  "contentMix": [
    {{
      "brand": "",
      "education": 0,
      "campaign": 0,
      "product": 0,
      "seo": 0
    }}
  ],

  "contentStrategy": [
    {{
      "brand": "",
      "theme": "",
      "strength": 0,
      "observation": ""
    }}
  ],

  "marketInsights": [
    {{
      "brand": "",
      "market": "",
      "observation": "",
      "implication": ""
    }}
  ],

  "pdpChanges": [
    {{
      "brand": "",
      "market": "",
      "product": "",
      "change": "",
      "before": "",
      "after": "",
      "implication": "",
      "url": ""
    }}
  ]
}}

============================================================
SIGNALS
============================================================

Only include genuinely useful competitive signals.

PRODUCT:

Focus on:

- new smartwatch launches
- new wearable products
- major feature launches
- AI features
- health features
- fitness features
- training features
- sports features
- navigation
- battery
- materials
- sensors
- software experience
- ecosystem integration
- product positioning

Do NOT simply repeat specifications.

Ask:

"What is strategically new?"

============================================================
MARKETING
============================================================

Identify:

- launch campaigns
- brand campaigns
- product films
- social campaigns
- influencer activity
- KOL activity
- seasonal activity
- local-market campaigns
- community storytelling
- new creative formats
- new ways of demonstrating wearable benefits

Focus on HOW the product is marketed.

============================================================
CONTENT
============================================================

Identify emerging communication patterns.

Examples:

- health → actionable health guidance
- fitness → performance improvement
- sport → real-time assistance
- AI → personal coaching
- battery → freedom / less charging
- GPS → confidence / safety
- sensors → consumer outcome
- technical feature → everyday scenario

Do not merely repeat feature names.

============================================================
ECOMMERCE
============================================================

Only classify something as ECOMMERCE when there is actual evidence
of an e-commerce or product-page change.

Look for:

- hero messaging
- headline changes
- module sequencing
- product comparison
- product selector
- scenario modules
- feature modules
- video modules
- technical explanation
- benefit-led copy
- product cards
- comparison tables
- CTA
- cross-selling
- bundling
- navigation
- FAQ
- new merchandising structure

Do NOT invent PDP changes from a normal news article.

============================================================
PDP CHANGE DATA
============================================================

The supplied PDP changes are detected through page snapshots.

If the supplied data indicates a real change:

Explain:

1. What changed
2. Before
3. After
4. Why the change matters competitively

If the diff looks like a technical or irrelevant page change,
do NOT report it.

============================================================
HUAWEI ACTIONS
============================================================

Create practical recommendations.

Good examples:

- Reframe a technical feature around a consumer outcome.
- Add a scenario-led PDP module.
- Build a short demonstration video.
- Strengthen pre/during/post-workout storytelling.
- Add a product comparison module.
- Create a sport-specific content series.
- Localise product storytelling by market.
- Turn a complex health feature into a simple consumer explanation.

Avoid:

"Create more engaging content."

Recommendations must be usable by:

- e-commerce teams
- PDP teams
- content teams
- social teams
- video teams
- product marketing teams

============================================================
CONTENT MIX
============================================================

Give directional scores from 0 to 100.

education:
How much recent content is product/feature education.

campaign:
How much is campaign/creative marketing.

product:
How much is product launch/product-led content.

seo:
Keep this only as a small legacy field.
Do NOT generate SEO recommendations.

The values are directional, not market share.

============================================================
CONTENT STRATEGY
============================================================

Identify the strongest recurring themes for each brand.

Possible themes:

Health
Fitness
Training
Running
Cycling
Outdoor
Adventure
AI
Personalisation
Lifestyle
Safety
Ecosystem
Design
Battery
Navigation
Recovery

Give strength 0-100.

============================================================
MARKET INSIGHTS
============================================================

Only report meaningful market differences.

Do not invent localisation.

============================================================
GENERAL RULES
============================================================

- Trace factual claims to supplied URLs.
- Never invent metrics.
- Never invent campaign results.
- Never invent PDP changes.
- Strategic implications are analysis, not facts.
- Keep concise.
- No more than 12 signals.
- No more than 6 HUAWEI actions.
- No more than 10 PDP changes.
- No more than 9 content strategy entries.
- No more than 12 market insights.
- Do not force every brand into every category.
- Do not include generic technology news.
- Avoid repetitive items.
- Wearables only.

============================================================
FEED ITEMS
============================================================

{json.dumps(
    ai_items,
    ensure_ascii=False
)}

============================================================
PDP CHANGES
============================================================

{json.dumps(
    pdp_changes,
    ensure_ascii=False
)}
"""

    try:

        print(
            f"Sending {len(ai_items)} feed items "
            f"and {len(pdp_changes)} PDP changes "
            f"to {QWEN_MODEL}..."
        )

        res = client.responses.create(
            model=QWEN_MODEL,
            input=prompt,
        )

        if getattr(
            res,
            "usage",
            None
        ):

            usage = res.usage

            input_tokens = getattr(
                usage,
                "input_tokens",
                0
            )

            output_tokens = getattr(
                usage,
                "output_tokens",
                0
            )

            total_tokens = getattr(
                usage,
                "total_tokens",
                0
            )

            print(
                "Token usage:",
                f"input={input_tokens},",
                f"output={output_tokens},",
                f"total={total_tokens}"
            )

        txt = res.output_text.strip()

        txt = re.sub(
            r"^```json\s*",
            "",
            txt,
            flags=re.IGNORECASE
        )

        txt = re.sub(
            r"\s*```$",
            "",
            txt
        )

        result = json.loads(
            txt
        )

        return result

    except Exception as ex:

        print(
            "AI analysis error:",
            repr(ex)
        )

        return None


# ============================================================
# NORMALISE AI OUTPUT FOR DASHBOARD
# ============================================================

def normalise_result(
    result,
    pdp_changes
):

    if not result:
        return None

    result.setdefault(
        "signals",
        []
    )

    result.setdefault(
        "actions",
        []
    )

    result.setdefault(
        "contentMix",
        []
    )

    result.setdefault(
        "contentStrategy",
        []
    )

    result.setdefault(
        "marketInsights",
        []
    )

    result.setdefault(
        "pdpChanges",
        []
    )

    # ----------------------------------------
    # Keep only actual PDP changes
    # ----------------------------------------

    valid_pdp_urls = {
        x["url"]
        for x in pdp_changes
    }

    result["pdpChanges"] = [
        x
        for x in result["pdpChanges"]
        if x.get("url") in valid_pdp_urls
    ]

    # ----------------------------------------
    # Limit output
    # ----------------------------------------

    result["signals"] = result[
        "signals"
    ][:12]

    result["actions"] = result[
        "actions"
    ][:6]

    result["pdpChanges"] = result[
        "pdpChanges"
    ][:10]

    result["contentStrategy"] = result[
        "contentStrategy"
    ][:9]

    result["marketInsights"] = result[
        "marketInsights"
    ][:12]

    return result


# ============================================================
# SOURCE HEALTH
# ============================================================

def build_source_health():

    sources = []

    for brand, market, kind, url in FEEDS:

        sources.append(
            {
                "source": (
                    f"{brand} · "
                    f"{market}"
                ),
                "type": kind,
                "status": "MONITORED",
            }
        )

    for page in PDP_PAGES:

        sources.append(
            {
                "source": (
                    f"{page['brand']} · "
                    f"{page['market']}"
                ),
                "type": page["pageType"],
                "status": "MONITORED",
            }
        )

    return sources


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=== 3C Wearables Intelligence Hub ==="
    )

    print(
        "AI model:",
        QWEN_MODEL
    )

    # ----------------------------------------
    # Load existing data
    # ----------------------------------------

    old = {}

    if os.path.exists(DATA):

        try:

            with open(
                DATA,
                encoding="utf-8"
            ) as f:

                old = json.load(f)

        except Exception as ex:

            print(
                "Could not read existing data:",
                str(ex)
            )

            old = {}

    # ----------------------------------------
    # Fetch feeds
    # ----------------------------------------

    items = fetch()

    # ----------------------------------------
    # Fetch PDP pages
    # ----------------------------------------

    current_pdp_pages = fetch_pdp_pages()

    # ----------------------------------------
    # Detect PDP changes
    # ----------------------------------------

    pdp_changes = create_pdp_changes(
        current_pdp_pages,
        old
    )

    # ----------------------------------------
    # AI
    # ----------------------------------------

    result = ai(
        items,
        pdp_changes
    )

    now = (
        dt.datetime
        .now(
            dt.timezone.utc
        )
        .astimezone(
            dt.timezone(
                dt.timedelta(
                    hours=8
                )
            )
        )
        .isoformat()
    )

    # ----------------------------------------
    # Successful AI result
    # ----------------------------------------

    if result:

        result = normalise_result(
            result,
            pdp_changes
        )

        result["updatedAt"] = now

        result["timezone"] = (
            "Asia/Kuala_Lumpur"
        )

        result["feedItems"] = items[
            :MAX_FEED_ITEMS
        ]

        result["pdpSnapshots"] = [
            {
                "brand": x["brand"],
                "market": x["market"],
                "pageType": x["pageType"],
                "url": x["url"],
                "contentHash": x["contentHash"],
                "text": x["text"],
            }
            for x in current_pdp_pages
        ]

        result["sourceHealth"] = (
            build_source_health()
        )

        # Legacy compatibility
        result["seo"] = []

        with open(
            DATA,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                result,
                f,
                ensure_ascii=False,
                indent=2
            )

        print(
            "AI analysis completed successfully."
        )

        print(
            "Dashboard data written to:",
            DATA
        )

    # ----------------------------------------
    # AI failure
    # ----------------------------------------

    else:

        print(
            "AI analysis failed."
        )

        # Preserve previous AI analysis.
        # Still update feed and PDP snapshots
        # so the next run has fresh data.

        old["updatedAt"] = now

        old["timezone"] = (
            "Asia/Kuala_Lumpur"
        )

        old["feedItems"] = items[
            :MAX_FEED_ITEMS
        ]

        old["pdpSnapshots"] = [
            {
                "brand": x["brand"],
                "market": x["market"],
                "pageType": x["pageType"],
                "url": x["url"],
                "contentHash": x["contentHash"],
                "text": x["text"],
            }
            for x in current_pdp_pages
        ]

        old["sourceHealth"] = (
            build_source_health()
        )

        with open(
            DATA,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                old,
                f,
                ensure_ascii=False,
                indent=2
            )

        print(
            "Existing AI analysis preserved."
        )


if __name__ == "__main__":
    main()
