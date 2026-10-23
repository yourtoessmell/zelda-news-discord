import json
import os
import re
import unicodedata
from urllib.parse import (
    parse_qsl,
    urlencode,
    urldefrag,
    unquote,
    urljoin,
    urlparse,
    urlunparse,
)

import requests
from bs4 import BeautifulSoup


SOURCES = [
    "https://zelda.nintendo.com/",
    "https://www.nintendo.com/us/whatsnew/",
    "https://www.nintendo.com/en-gb/News/News-Updates-11145.html",
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

TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "ref",
    "srsltid",
}

HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 30


def fetch_page(url):
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def clean_text(text):
    return " ".join((text or "").split())


def normalize_title(title):
    text = unicodedata.normalize("NFKD", title.casefold())
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", text))


def normalize_url(url):
    url, _ = urldefrag(url)
    parsed = urlparse(url)

    hostname = (parsed.hostname or "").casefold()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    port = parsed.port
    netloc = hostname
    if port and port not in (80, 443):
        netloc = f"{hostname}:{port}"

    path = re.sub(r"/+", "/", parsed.path).rstrip("/") or "/"

    query_parameters = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in TRACKING_PARAMETERS
    ]

    return urlunparse(
        (
            "https",
            netloc,
            path,
            "",
            urlencode(sorted(query_parameters)),
            "",
        )
    )


def is_nintendo_url(url):
    hostname = urlparse(url).hostname or ""
    hostname = hostname.casefold()
    return hostname == "nintendo.com" or hostname.endswith(".nintendo.com")


def contains_any(text, keywords):
    text = text.casefold()
    return any(keyword.casefold() in text for keyword in keywords)


def is_relevant(text):
    # Always-post topics override skip terms.
    if contains_any(text, ALWAYS_POST):
        return True

    # Otherwise, skip promotional posts.
    if contains_any(text, SKIP_KEYWORDS):
        return False

    has_game_series = contains_any(text, GAME_SERIES)
    has_news_topic = contains_any(text, NEWS_KEYWORDS)

    is_general_game_news = contains_any(
        text,
        ["new game", "release date", "launch"],
    )

    return (has_game_series and has_news_topic) or is_general_game_news


def get_link_title(link):
    # Prefer the headline instead of combining it with the date or preview.
    heading = link.find(["h1", "h2", "h3", "h4", "h5", "h6"])
    if heading:
        title = clean_text(heading.get_text(" ", strip=True))
        if title:
            return title

    for attribute in ("aria-label", "title"):
        title = clean_text(link.get(attribute, ""))
        if title:
            return title

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

            if not is_nintendo_url(url):
                continue

            url = normalize_url(url)
            if url in seen_urls:
                continue

            title = get_link_title(link)
            if not title:
                continue

            # Filter using all the text in the link, but post only the headline.
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


def title_key_from_url(url):
    path = unquote(urlparse(url).path).rstrip("/")
    slug = path.rsplit("/", 1)[-1]
    slug = re.sub(r"\.(html?|aspx?)$", "", slug, flags=re.IGNORECASE)
    return normalize_title(slug.replace("-", " ").replace("_", " "))


def load_seen():
    try:
        with open("seen.json", "r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return {"urls": set(), "titles": set()}

    # Older versions stored only a list of URLs.
    if isinstance(data, list):
        urls = data
        titles = []
    elif isinstance(data, dict):
        urls = data.get("urls", [])
        titles = data.get("titles", [])
    else:
        raise ValueError("seen.json must contain a URL list or an object with urls and titles.")

    if not isinstance(urls, list) or not all(
        isinstance(url, str) for url in urls
    ):
        raise ValueError("seen.json 'urls' must be a list of strings.")

    if not isinstance(titles, list) or not all(
        isinstance(title, str) for title in titles
    ):
        raise ValueError("seen.json 'titles' must be a list of strings.")

    normalized_urls = {normalize_url(url) for url in urls}
    normalized_titles = set(titles)

    # Older records have URLs but no saved headline keys. Use URL slugs as a
    # best-effort bridge so old links can match their current headlines.
    normalized_titles.update(
        key for key in (title_key_from_url(url) for url in urls) if key
    )

    return {"urls": normalized_urls, "titles": normalized_titles}


def save_seen(seen):
    data = {
        "urls": sorted(seen["urls"]),
        "titles": sorted(seen["titles"]),
    }
    with open("seen.json", "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


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

    seen = load_seen()

    if not seen["urls"] and not seen["titles"]:
        print("First run: saving matching links without sending them.")
        seen["urls"].update(article["url"] for article in articles)
        seen["titles"].update(
            normalize_title(article["title"]) for article in articles
        )
        save_seen(seen)
        return

    new_count = 0

    for article in articles:
        url_key = normalize_url(article["url"])
        title_key = normalize_title(article["title"])

        # Either a known URL or a known headline means this story was seen.
        if url_key in seen["urls"] or title_key in seen["titles"]:
            seen["urls"].add(url_key)
            seen["titles"].add(title_key)
            continue

        print(f"Sending: {article['title']}")
        send_to_discord(article)

        seen["urls"].add(url_key)
        seen["titles"].add(title_key)
        save_seen(seen)
        new_count += 1

    save_seen(seen)
    print(f"Sent {new_count} new articles")


if __name__ == "__main__":
    main()
