import json
import os
import re
import ssl
import urllib.request
from urllib.parse import urljoin

ZELDA_URL = "https://zelda.nintendo.com/"
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

NEWS_WORDS = (
    "news",
    "anniversary",
    "concert",
    "zelda",
    "ocarina",
    "soundtrack",
    "nintendo",
)


def fetch(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )

    # Ignore SSL certificate verification issues
    context = ssl._create_unverified_context()

    with urllib.request.urlopen(
        req,
        timeout=30,
        context=context
    ) as response:
        return response.read().decode("utf-8", errors="ignore")


def get_news_links():
    html = fetch(ZELDA_URL)

    matches = re.findall(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    articles = []

    for href, inner_html in matches:
        title = re.sub(r"<[^>]+>", " ", inner_html)
        title = re.sub(r"\s+", " ", title).strip()

        if not title:
            continue

        url = urljoin(ZELDA_URL, href)

        combined = (title + " " + url).lower()

        if not any(word in combined for word in NEWS_WORDS):
            continue

        if any(
            bad in url.lower()
            for bad in (
                "facebook.com",
                "twitter.com",
                "x.com",
                "youtube.com",
                "instagram.com",
                "privacy",
                "terms",
                "support",
            )
        ):
            continue

        articles.append(
            {
                "title": title,
                "url": url,
            }
        )

    unique = []
    seen_urls = set()

    for article in articles:
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            unique.append(article)

    return unique


def load_seen():
    try:
        with open("seen.json", "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(urls):
    with open("seen.json", "w", encoding="utf-8") as f:
        json.dump(sorted(urls), f, indent=2)


def send_to_discord(article):
    if not DISCORD_WEBHOOK:
        raise RuntimeError("DISCORD_WEBHOOK secret is missing.")

    payload = {
        "content": (
            "🗡️ **New Zelda News!**\n"
            f"**{article['title']}**\n"
            f"{article['url']}"
        )
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        DISCORD_WEBHOOK,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ZeldaNewsDiscordBot/1.0",
        },
        method="POST",
    )

    context = ssl._create_unverified_context()

    with urllib.request.urlopen(
        req,
        timeout=30,
        context=context
    ) as response:
        response.read()


def main():
    print(f"Checking {ZELDA_URL}")

    articles = get_news_links()

    current_urls = {article["url"] for article in articles}
    seen = load_seen()

    print(f"Found {len(articles)} Zelda links.")

    if not seen:
        print("First run: saving existing articles.")
        save_seen(current_urls)
        return

    new_articles = [
        article
        for article in articles
        if article["url"] not in seen
    ]

    print(f"Found {len(new_articles)} new article(s).")

    for article in reversed(new_articles):
        print("Sending:", article["title"])
        send_to_discord(article)

    save_seen(seen | current_urls)


if __name__ == "__main__":
    main()
