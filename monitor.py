import requests
import json
import os
import smtplib
import base64
import re
from email.mime.text import MIMEText
from datetime import datetime

NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "ioanacmuresan@gmail.com")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
SNAPSHOT_FILE = "snapshot.json"
TARGET_SIZES = ["40/l", "42/l", "38/l", "40/xl", "marime: l", "marime: 40", "38/m-l"]

# Magento REST API — femei category, sorted by newest, page 1
API_URL = (
    "https://lamajole.ro/rest/V1/products?"
    "searchCriteria[filterGroups][0][filters][0][field]=category_id&"
    "searchCriteria[filterGroups][0][filters][0][value]=12&"
    "searchCriteria[filterGroups][0][filters][0][conditionType]=eq&"
    "searchCriteria[sortOrders][0][field]=created_at&"
    "searchCriteria[sortOrders][0][direction]=DESC&"
    "searchCriteria[pageSize]=100&"
    "searchCriteria[currentPage]=1&"
    "fields=items[id,sku,name,custom_attributes,price]"
)


def get_products():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    r = requests.get(API_URL, headers=headers, timeout=20)
    print(f"API status: {r.status_code}")

    if r.status_code != 200:
        print(f"API error: {r.text[:200]}")
        return {}

    data = r.json()
    items = data.get("items", [])
    print(f"Products from API: {len(items)}")

    results = {}
    for item in items:
        name = item.get("name", "")
        sku = item.get("sku", "")
        price = item.get("price", "")
        url = f"https://lamajole.ro/{sku.lower().replace(' ', '-')}.html"

        # Get size from custom_attributes
        size = ""
        for attr in item.get("custom_attributes", []):
            if attr.get("attribute_code") in ["marime", "size", "clothing_size"]:
                size = str(attr.get("value", "")).lower()
                break

        # Also check name for size hints
        name_lower = name.lower()
        size_lower = size.lower()
        combined = f"{name_lower} {size_lower}"

        if any(s in combined for s in TARGET_SIZES):
            results[sku] = {
                "name": name,
                "size": size or "L/40",
                "price": f"{price} RON",
                "url": url
            }

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
    for sku, item in new_items.items():
        body += f"• {item['name']}\n  Mărime: {item['size']} | {item['price']}\n  {item.get('url', '')}\n\n"
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
        new_items = {k: v for k, v in current.items() if k not in seen}
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
