import requests
import json
import os
import smtplib
import base64
import re
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from datetime import datetime

NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "ioanacmuresan@gmail.com")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
SNAPSHOT_FILE = "snapshot.json"

# Size filters — matches Romanian sizing on lamajole
TARGET_SIZES = ["40/l", "42/l", "38/l", "40/xl", " l,", "/l,", "l\n", ": l\n", ":l"]

# Use allorigins proxy to bypass JS rendering issues
PROXY_URL = "https://api.allorigins.win/get?url={}"
TARGET_URL = "https://lamajole.ro/femei.html"


def get_products():
    headers = {"User-Agent": "Mozilla/5.0"}

    # Try direct first
    try:
        r = requests.get(TARGET_URL, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ro-RO,ro;q=0.9",
            "Referer": "https://lamajole.ro/",
        }, timeout=20)
        print(f"Direct status: {r.status_code}, size: {len(r.text)}")
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select("li.product-item")
        print(f"Direct items found: {len(items)}")

        if len(items) > 0:
            return parse_items(items)
    except Exception as e:
        print(f"Direct fetch failed: {e}")

    # Fallback: allorigins proxy
    try:
        proxy = PROXY_URL.format(requests.utils.quote(TARGET_URL))
        r2 = requests.get(proxy, timeout=30)
        data = r2.json()
        html = data.get("contents", "")
        print(f"Proxy size: {len(html)}")
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("li.product-item")
        print(f"Proxy items found: {len(items)}")
        if len(items) > 0:
            return parse_items(items)
    except Exception as e:
        print(f"Proxy fetch failed: {e}")

    # Last resort: scrape the homepage "Produse recent adaugate" section
    try:
        r3 = requests.get("https://lamajole.ro/", headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }, timeout=20)
        print(f"Homepage status: {r3.status_code}, size: {len(r3.text)}")
        soup = BeautifulSoup(r3.text, "html.parser")
        items = soup.select("li.product-item")
        print(f"Homepage items found: {len(items)}")
        return parse_items(items)
    except Exception as e:
        print(f"Homepage fetch failed: {e}")

    return {}


def parse_items(items):
    results = {}
    for item in items:
        name_el = item.select_one("a.product-item-link, strong a, a[class*='product']")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        if not name:
            continue
        url = name_el.get("href", "")
        if not url.startswith("http"):
            url = "https://lamajole.ro" + url

        item_text = item.get_text(" ", strip=True)
        item_lower = item_text.lower()

        # Check size match
        if any(s in item_lower for s in TARGET_SIZES):
            size_m = re.search(r'm[ăa]rime[:\s]+([^\n·\|]+)', item_text, re.IGNORECASE)
            size = size_m.group(1).strip() if size_m else "L/40"
            price_el = item.select_one(".price")
            price = price_el.get_text(strip=True) if price_el else ""
            results[url] = {"name": name, "size": size, "price": price}

    print(f"Produse L/40 gasite: {len(results)}")
    return results


def get_snapshot_from_github():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None, None
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{SNAPSHOT_FILE}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    r = requests.get(api_url, headers=headers)
    if r.status_code == 200:
        data = r.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return json.loads(content), data["sha"]
    return None, None


def save_snapshot_to_github(snapshot, sha=None):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{SNAPSHOT_FILE}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    content = base64.b64encode(
        json.dumps(snapshot, ensure_ascii=False, indent=2).encode()
    ).decode()
    payload = {"message": "Update snapshot", "content": content}
    if sha:
        payload["sha"] = sha
    resp = requests.put(api_url, headers=headers, json=payload)
    print(f"Snapshot saved: {resp.status_code}")


def send_email(new_items):
    if not SENDER_EMAIL or not APP_PASSWORD:
        print("Email neconfigurat, skip.")
        return
    body = f"🛍️ {len(new_items)} produse noi L/40 pe LaMajole — Femei\n\n"
    for url, item in new_items.items():
        body += f"• {item['name']}\n  Mărime: {item['size']} | {item['price']}\n  {url}\n\n"
    body += f"\nVerificat: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"LaMajole: {len(new_items)} produse noi L/40 ({datetime.now().strftime('%d.%m %H:%M')})"
    msg["From"] = SENDER_EMAIL
    msg["To"] = NOTIFY_EMAIL
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(SENDER_EMAIL, APP_PASSWORD)
        s.send_message(msg)
    print(f"Email trimis catre {NOTIFY_EMAIL}: {len(new_items)} produse")


def main():
    current = get_products()
    seen, sha = get_snapshot_from_github()

    if seen is not None:
        new_items = {u: d for u, d in current.items() if u not in seen}
        if new_items:
            print(f"Produse NOI: {len(new_items)}")
            send_email(new_items)
        else:
            print("Nicio noutate.")
    else:
        print("Prima rulare — se salveaza snapshot-ul.")

    save_snapshot_to_github(current, sha)


if __name__ == "__main__":
    main()
