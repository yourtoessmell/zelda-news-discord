import json
import os
import requests
from bs4 import BeautifulSoup

SOURCES = [
    "https://zelda.nintendo.com/",
    "https://www.nintendo.com/us/whatsnew/"
]

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")


def fetch_page(url):
    response = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
        timeout=30
    )

    response.raise_for_status()
    return response.text


def get_news_links():
    articles = []

    for source_url in SOURCES:
        print(f"Checking {source_url}")

        try:
            html = fetch_page(source_url)
            soup = BeautifulSoup(html, "html.parser")

            for link in soup.find_all("a", href=True):
                title = link.get_text(strip=True)
                url = link["href"]

                if not title:
                    continue

                if url.startswith("/"):
                    if "nintendo.com" in source_url:
                        url = "https://www.nintendo.com" + url
                    else:
                        url = "https://zelda.nintendo.com" + url

                articles.append({
                    "title": title,
                    "url": url
                })

        except Exception as e:
            print(f"Error checking {source_url}: {e}")

    seen_urls = set()
    unique = []

    for article in articles:
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            unique.append(article)

    return unique


def load_seen():
    try:
        with open("seen.json", "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(urls):
    with open("seen.json", "w", encoding="utf-8") as f:
        json.dump(sorted(list(urls)), f, indent=2)


def send_to_discord(article):
    if not DISCORD_WEBHOOK:
        print("No Discord webhook configured.")
        return

    payload = {
        "content": (
            "🎮 **New Nintendo news just came in! <@&1052211616663470160>**\n\n"
            f"**{article['title']}**\n"
            f"{article['url']}"
        )
    }

    requests.post(
        DISCORD_WEBHOOK,
        json=payload,
        timeout=30
    )


def main():
    print("Starting Nintendo + Zelda News Bot")

    articles = get_news_links()

    print(f"Found {len(articles)} unique links")

    current_urls = {article["url"] for article in articles}
    seen = load_seen()

    if not seen:
        print("First run: saving all links.")
        save_seen(current_urls)
        return

    new_articles = [
        article
        for article in articles
        if article["url"] not in seen
    ]

    print(f"Found {len(new_articles)} new links")

    for article in new_articles:
        print(f"Sending: {article['title']}")
        send_to_discord(article)

    save_seen(seen | current_urls)


if __name__ == "__main__":
    main()
