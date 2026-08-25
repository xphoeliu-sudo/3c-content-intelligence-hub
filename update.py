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
    "User-Agent": "Mozilla/5.0 (3C Content Intelligence Hub/3.0)"
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


FEEDS = [
    (
        "Apple",
        "Global",
        "Official",
        "https://www.apple.com/newsroom/rss-feed.rss",
    ),
    (
        "Samsung",
        "Global",
        "Discovery",
        "https://news.google.com/rss/search?q=site%3Anews.samsung.com%2Fglobal%20Samsung%20AI%20OR%20Galaxy%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen",
    ),
    (
        "Samsung",
        "Malaysia",
        "Official",
        "https://news.google.com/rss/search?q=site%3Anews.samsung.com%2Fmy%20Samsung%20Galaxy%20when%3A1d&hl=en-US&gl=MY&ceid=MY%3Aen",
    ),
    (
        "Garmin",
        "Global",
        "Discovery",
        "https://news.google.com/rss/search?q=site%3Agarmin.com%2Fen-CA%2Fblog%20Garmin%20when%3A7d&hl=en-US&gl=US&ceid=US%3Aen",
    ),
    (
        "Garmin",
        "Malaysia",
        "Discovery",
        "https://news.google.com/rss/search?q=site%3Agarmin.com.my%2Fnews%20Garmin%20when%3A7d&hl=en-US&gl=MY&ceid=MY%3Aen",
    ),
    (
        "Google",
        "Global",
        "Discovery",
        "https://news.google.com/rss/search?q=Google%20Pixel%20AI%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen",
    ),
    (
        "Xiaomi",
        "Global",
        "Discovery",
        "https://news.google.com/rss/search?q=Xiaomi%20smartphone%20wearable%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen",
    ),
    (
        "Sony",
        "Global",
        "Discovery",
        "https://news.google.com/rss/search?q=Sony%20headphones%20camera%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen",
    ),
    (
        "Bose",
        "Global",
        "Discovery",
        "https://news.google.com/rss/search?q=Bose%20audio%20headphones%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen",
    ),
    (
        "YouTube",
        "Global",
        "Discovery",
        "https://news.google.com/rss/search?q=Apple%20Samsung%20Garmin%20YouTube%20campaign%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen",
    ),
    (
        "Reddit",
        "Global",
        "Discovery",
        "https://news.google.com/rss/search?q=site%3Areddit.com%20Apple%20Samsung%20Garmin%20watch%20audio%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen",
    ),
]


def pdate(e):
    for k in ("published", "updated"):
        if e.get(k):
            try:
                return parsedate_to_datetime(e[k]).isoformat()
            except Exception:
                pass

    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean_text(text):
    return BeautifulSoup(
        text or "",
        "html.parser"
    ).get_text(" ", strip=True)


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

            feed = feedparser.parse(r.content)

            for e in feed.entries[:15]:

                title = clean_text(
                    e.get("title", "")
                )

                summary = clean_text(
                    e.get("summary", "")
                )

                link = e.get("link", "")

                key = hashlib.sha1(
                    (
                        brand
                        + market
                        + title
                    ).lower().encode("utf-8")
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
                        "summary": summary[:900],
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
        f"Fetched {len(out)} unique feed items."
    )

    return out


def ai(items):

    from openai import OpenAI

    key = os.getenv("DASHSCOPE_API_KEY")

    if not key:
        print(
            "DASHSCOPE_API_KEY is not configured. "
            "Skipping AI analysis."
        )
        return None

    ai_items = items[:MAX_AI_ITEMS]

    client = OpenAI(
        api_key=key,
        base_url=QWEN_BASE_URL,
    )

    prompt = f"""
You are a senior 3C competitive content intelligence analyst
supporting HUAWEI overseas product marketing and e-commerce teams.

Your job is NOT to produce a general technology news summary.

Your priority is to identify how major 3C competitors are
developing products, presenting products, marketing products,
and evolving their e-commerce content.

Prioritise:
1. Apple
2. Samsung
3. Garmin

Also use useful signals from Google, Xiaomi, Sony, Bose,
YouTube and Reddit.

Analyse the collected items and produce ONLY valid JSON.

Use exactly this structure:

{{
  "productMoves": [
    {{
      "brand": "",
      "market": "",
      "date": "",
      "priority": "HIGH|MEDIUM|LOW",
      "product": "",
      "moveType": "",
      "whatChanged": "",
      "whyItMatters": "",
      "url": ""
    }}
  ],

  "marketingMoves": [
    {{
      "brand": "",
      "market": "",
      "date": "",
      "priority": "HIGH|MEDIUM|LOW",
      "campaignType": "",
      "whatTheyDid": "",
      "creativeApproach": "",
      "whyItMatters": "",
      "url": ""
    }}
  ],

  "ecommerceMoves": [
    {{
      "brand": "",
      "market": "",
      "date": "",
      "priority": "HIGH|MEDIUM|LOW",
      "pageType": "",
      "structureOrMessaging": "",
      "consumerBenefit": "",
      "whyItMatters": "",
      "url": ""
    }}
  ],

  "huaweiActions": [
    {{
      "priority": "P1|P2|P3",
      "area": "PRODUCT|MARKETING|ECOMMERCE|CONTENT",
      "observation": "",
      "recommendedAction": "",
      "example": ""
    }}
  ]
}}

ANALYSIS PRIORITIES

PRODUCT MOVES:
Focus on:
- New products
- Product launches
- New features
- AI features
- Hardware innovation
- Materials and design
- Health and fitness capabilities
- Audio technology
- Camera technology
- Battery and charging
- Software/product experience
- Product positioning
- New product variants
- Product ecosystem development

Do NOT merely repeat product specifications.
Identify what is genuinely new or strategically notable.

MARKETING MOVES:
Focus on:
- New campaigns
- Product launch campaigns
- Brand films
- Social campaigns
- Video formats
- Influencer/KOL activity
- Community storytelling
- Seasonal campaigns
- Local-market campaigns
- Product storytelling
- New creative concepts
- New ways of demonstrating product benefits

Prioritise HOW the product is marketed rather than simply
reporting that a campaign exists.

E-COMMERCE MOVES:
This is a high-priority category.

Look for:
- PDP structure changes
- Hero section changes
- Selling-point sequencing
- Product comparison
- Product selector
- Scenario storytelling
- Feature modules
- Video modules
- Interactive modules
- How-to modules
- Technical explanation
- Benefit-led copy
- Product cards
- Comparison tables
- FAQ
- Cross-selling
- Bundling
- CTA strategy
- New page navigation
- New ways of explaining complex technology

Important:
Only classify something as an e-commerce move when the source
actually provides evidence of an e-commerce/product-page change.
Do NOT invent PDP changes from a normal product launch article.

HUAWEI ACTIONS:
Turn the strongest observations into practical recommendations
for HUAWEI overseas content operations.

Recommendations should be specific and usable by:
- Product page teams
- E-commerce content teams
- Social/content teams
- Video teams
- Product marketing teams

Examples of useful recommendations:
- Introduce a scenario-led PDP module
- Move a technical feature closer to its consumer benefit
- Use a short demonstration video instead of static specification copy
- Build a stronger pre/during/post-use storytelling structure
- Add a product comparison module
- Localise campaign storytelling for specific markets

Do NOT make generic recommendations such as
"create more engaging content".

GENERAL RULES:
- Source facts must be traceable to supplied URLs.
- Never invent metrics, launches, features or campaign results.
- Strategic implications are analysis, not facts.
- Use professional British English.
- Be concise and information-dense.
- Keep no more than 8 productMoves.
- Keep no more than 8 marketingMoves.
- Keep no more than 8 ecommerceMoves.
- Keep no more than 6 huaweiActions.
- Only include genuinely useful signals.
- If there is insufficient evidence, return fewer items.
- Do not force every brand into every category.
- Avoid generic technology news.
- Avoid repetitive items about the same product.
- Do not include a separate SEO section.

ITEMS:

{json.dumps(ai_items, ensure_ascii=False)}
"""

    try:

        print(
            f"Sending {len(ai_items)} items to "
            f"{QWEN_MODEL}..."
        )

        res = client.responses.create(
            model=QWEN_MODEL,
            input=prompt,
        )

        if getattr(res, "usage", None):

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

        return json.loads(txt)

    except Exception as ex:

        print(
            "AI analysis error:",
            repr(ex)
        )

        return None


def main():

    print(
        "=== 3C Content Intelligence Hub ==="
    )

    print(
        "AI model:",
        QWEN_MODEL
    )

    items = fetch()

    result = ai(items)

    now = (
        dt.datetime
        .now(dt.timezone.utc)
        .astimezone(
            dt.timezone(
                dt.timedelta(hours=8)
            )
        )
        .isoformat()
    )

    if result:

        result["updatedAt"] = now

        result["timezone"] = "Asia/Kuala_Lumpur"

        result["feedItems"] = items[:MAX_FEED_ITEMS]

        old = {}

        if os.path.exists(DATA):

            try:

                with open(
                    DATA,
                    encoding="utf-8"
                ) as f:
                    old = json.load(f)

            except Exception:
                old = {}

        result["sourceHealth"] = old.get(
            "sourceHealth",
            []
        )

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

    else:

        if os.path.exists(DATA):

            try:

                with open(
                    DATA,
                    encoding="utf-8"
                ) as f:
                    old = json.load(f)

            except Exception:
                old = {}

        else:
            old = {}

        old["updatedAt"] = now

        old["timezone"] = "Asia/Kuala_Lumpur"

        old["feedItems"] = items[:MAX_FEED_ITEMS]

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
            "AI analysis failed. "
            "Existing dashboard data preserved."
        )


if __name__ == "__main__":
    main()
