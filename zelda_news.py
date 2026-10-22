import json
import os
import re
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


SOURCES = [
    "https://zelda.nintendo.com/",
    "https://www.nintendo.com/us/whatsnew/",
]

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

# A match here posts even if the text also contains a skip term.
ALWAYS_POST = [
    "zelda",
    "the legend of zelda",
    "hyrule",
    "nintendo direct",
    "tomodachi life",
    "mario",
    "super smash",
    "smash bros",
    "splatoon",
    "animal crossing",
]

# Other series are included when the text also matches a news term.
GAME_SERIES = [
    "donkey kong",
    "kirby",
    "metroid",
    "pikmin",
    "fire emblem",
    "xenoblade",
    "pokemon",
    "pokémon",
    "luigi's mansion",
    "luigi’s mansion",
    "yoshi",
    "star fox",
    "wario",
    "kid icarus",
    "f-zero",
]

NEWS_KEYWORDS = [
    "nintendo direct",
    "trailer",
    "gameplay",
    "announced",
    "announcement",
    "new game",
    "release date",
    "release",
    "launch",
    "update",
    "dlc",
    "expansion",
    "interview",
    "developer",
    "director",
    "producer",
    "talks about",
    "explains",
]

# These block regular news matches, but not ALWAYS_POST matches.
SKIP_KEYWORDS = [
    "sale",
    "sales",
    "discount",
    "discounts",
    "deal",
    "deals",
    "save on",
    "coupon",
    "coupons",
    "my nintendo rewards",
    "platinum points",
    "icon elements",
    "wallpaper",
    "limited time",
]

HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 30


def fetch_page(url):
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def clean_text(text):
    return " ".join(text.split())


def contains_any(text, keywords):
    text = text.casefold()
    return any(keyword.casefold() in text for keyword in keywords)


def is_nintendo_url(url):
    hostname = urlparse(url).hostname or ""
    return hostname == "nintendo.com" or hostname.endswith(".nintendo.com")


def is_relevant(text):
    # Always-post topics override skip terms.
    if contains_any(text, ALWAYS_POST):
        return True

    # Otherwise, skip promotional posts.
    if contains_any(text, SKIP_KEYWORDS):
        return False

    has_game_series = contains_any(text, GAME_SERIES)
    has_news_topic = contains_any(text, NEWS_KEYWORDS)

    # Include general new-game announcements and release news even if the
    # listing text doesn't clearly identify a series.
    is_general_game_news = contains_any(
        text,
        ["new game", "release date", "launch"],
    )

    return (has_game_series and has_news_topic) or is_general_game_news


def get_link_title(link):
    # Prefer the actual heading, rather than combining the date, description,
    # and other text that may also be inside the link.
    heading = link.find(["h1", "h2", "h3", "h4", "h5", "h6"])
    if heading:
        title = clean_text(heading.get_text(" ", strip=True))
        if title:
            return title

    # If the page provides an accessible title, prefer that over all link text.
    for attribute in ("aria-label", "title"):
        title = clean_text(link.get(attribute, ""))
        if title:
            return title

    # Last resort: use the link's visible text with spaces between elements.
    return clean_text(link.get_text(" ", strip=True))


def get_news_links():
    articles = []
    seen_urls = set()

    for source_url in SOURCES:
        print(f"Checking {source_url}")

        try:
            soup = BeautifulSoup(fetch_page(source_url), "html.parser")
        except requests.RequestException as error:
            print(f"Error checking {source_url}: {error}")
            continue

        for link in soup.find_all("a", href=True):
            url = urljoin(source_url, link["href"])
            url, _ = urldefrag(url)

            if not is_nintendo_url(url) or url in seen_urls:
                continue

            title = get_link_title(link)
            if not title:
                continue

            # Use all link text for filtering, but only the extracted title
            # for the Discord message.
            filter_text = " ".join(
                part
                for part in (
                    title,
                    clean_text(link.get_text(" ", strip=True)),
                    clean_text(link.get("aria-label", "")),
                    clean_text(link.get("title", "")),
                )
                if part
            )

            if not is_relevant(filter_text):
                continue

            seen_urls.add(url)
            articles.append({"title": title, "url": url})

    return articles


def load_seen():
    try:
        with open("seen.json", "r", encoding="utf-8") as file:
            urls = json.load(file)
    except FileNotFoundError:
        return set()

    if not isinstance(urls, list) or not all(
        isinstance(url, str) for url in urls
    ):
        raise ValueError("seen.json must contain a JSON list of URLs.")

    return set(urls)


def save_seen(urls):
    with open("seen.json", "w", encoding="utf-8") as file:
        json.dump(sorted(urls), file, indent=2)


def send_to_discord(article):
    if not DISCORD_WEBHOOK:
        raise RuntimeError(
            "No Discord webhook configured. Set the DISCORD_WEBHOOK environment variable."
        )

    payload = {
        "content": (
            "✒️ **New Nintendo news just came in! "
            "<@&1052211616663470160>**\n\n"
            f"📰 **{article['title'][:150]}**\n\n"
            f"🔗 {article['url']}"
        )
    }

    response = requests.post(
        DISCORD_WEBHOOK,
        json=payload,
        timeout=TIMEOUT,
    )
    response.raise_for_status()


def main():
    print("Starting Nintendo + Zelda News Bot")

    articles = get_news_links()
    print(f"Found {len(articles)} relevant links")

    current_urls = {article["url"] for article in articles}
    seen = load_seen()

    if not seen:
        print("First run: saving matching links without sending them.")
        save_seen(current_urls)
        return

    new_articles = [
        article
        for article in articles
        if article["url"] not in seen
    ]

    print(f"Found {len(new_articles)} new articles")

    for article in new_articles:
        print(f"Sending: {article['title']}")
        send_to_discord(article)

    save_seen(seen | current_urls)


if __name__ == "__main__":
    main()
