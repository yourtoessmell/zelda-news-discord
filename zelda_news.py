raise Exception("THIS IS THE NEW FILE")
import json
import os
import requests
from bs4 import BeautifulSoup

ZELDA_URL = "https://zelda.nintendo.com/"
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")


def fetch_page():
    response = requests.get(
        ZELDA_URL,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
        timeout=30,
        verify=False
    )

    response.raise_for_status()
    return response.text


def get_news_links():
    html = fetch_page()

    soup = BeautifulSoup(html, "html.parser")

    articles = []

    for link in soup.find_all("a", href=True):
        title = link.get_text(strip=True)
        url = link["href"]

        if not title:
            continue

        if url.startswith("/"):
            url = "https://zelda.nintendo.com" + url

        articles.append({
            "title": title,
            "url": url
        })

    # Remove duplicates
    seen = set()
    unique = []

    for article in articles:
        if article["url"] not in seen:
            seen.add(article["url"])
            unique.append(article)

    return unique


def load_seen():
    try:
        with open("seen.json", "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
        return set()


def save_seen(urls):
    with open("seen.json", "w", encoding="utf-8") as f:
        json.dump(list(urls), f, indent=2)


def send_to_discord(article):
    if not DISCORD_WEBHOOK:
        print("No Discord webhook found.")
        return

    payload = {
        "content":
            f"🗡️ **New Zelda Link Found**\n"
            f"**{article['title']}**\n"
            f"{article['url']}"
    }

    requests.post(
        DISCORD_WEBHOOK,
        json=payload,
        timeout=30
    )


def main():
    print("Bot started")

    articles = get_news_links()

    print(f"Found {len(articles)} links")

    current_urls = {a["url"] for a in articles}
    seen = load_seen()

    if not seen:
        print("First run, saving all links")
        save_seen(current_urls)
        return

    new_articles = [
        article
        for article in articles
        if article["url"] not in seen
    ]

    print(f"Found {len(new_articles)} new links")

    for article in new_articles:
        send_to_discord(article)

    save_seen(seen | current_urls)


if __name__ == "__main__":
    main()
