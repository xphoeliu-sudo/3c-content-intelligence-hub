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
    "User-Agent": "Mozilla/5.0 (3C Content Intelligence Hub/2.0)"
}

# =========================
# Configuration
# =========================

# Alibaba Cloud Model Studio / Qwen
# For China (Beijing), the legacy endpoint remains supported.
# You can later switch to a workspace-specific endpoint if needed.
QWEN_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1"
)

QWEN_MODEL = os.getenv(
    "QWEN_MODEL",
    "qwen3.5-plus"
)

# Maximum number of items sent to AI.
# Feed data can still contain up to 100 items.
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


# =========================
# Helpers
# =========================

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


# =========================
# Fetch RSS
# =========================

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


# =========================
# AI Analysis
# =========================

def ai(items):

    from openai import OpenAI

    key = os.getenv("DASHSCOPE_API_KEY")

    if not key:
        print(
            "DASHSCOPE_API_KEY is not configured. "
            "Skipping AI analysis."
        )
        return None

    # Reduce noise and token usage.
    ai_items = items[:MAX_AI_ITEMS]

    client = OpenAI(
        api_key=key,
        base_url=QWEN_BASE_URL,
    )

    prompt = f"""
You are the daily 3C content intelligence analyst
for HUAWEI overseas content operations.

Analyse the collected competitor and industry content below.

Prioritise:
1. Apple
2. Samsung
3. Garmin

Also identify useful signals from Google, Xiaomi,
Sony, Bose, YouTube and Reddit.

Produce ONLY valid JSON.

Required structure:

{{
  "signals": [
    {{
      "brand": "",
      "market": "",
      "type": "",
      "priority": "HIGH|MEDIUM|LOW",
      "title": "",
      "summary": "",
      "implication": "",
      "url": ""
    }}
  ],

  "seo": [
    {{
      "keywordPattern": "",
      "brand": "",
      "market": "",
      "signal": "",
      "opportunity": ""
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
  ]
}}

Rules:

- Source facts must be traceable to the supplied URLs.
- Never invent metrics, launches, features or campaign results.
- Strategic implications are analysis, not facts.
- Keep the analysis concise.
- Use professional British English.
- Focus on:
  launches,
  campaigns,
  PDP/product messaging,
  SEO/how-to,
  video/social formats,
  AI,
  health,
  fitness,
  audio,
  community,
  local-market storytelling.
- Keep no more than 10 signals.
- Keep no more than 10 SEO items.
- Keep no more than 8 actions.
- contentMix should contain only brands for which meaningful
  content signals exist.
- If the data is insufficient, return fewer items rather
  than inventing information.
- Do NOT wrap the JSON in Markdown code fences.

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

        # Print actual usage when available.
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

        # Remove accidental Markdown code fences.
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


# =========================
# Main
# =========================

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

    # If AI succeeds
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

    # If AI fails, keep the dashboard alive
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