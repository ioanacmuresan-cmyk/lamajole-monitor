#!/usr/bin/env python3
# LaMajole Monitor — rulează de 2x pe zi cu cron sau Task Scheduler
# pip install requests beautifulsoup4

import requests, json, os, smtplib
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from datetime import datetime

NOTIFY_EMAIL = "ioana_curta@yahoo.com"
SENDER_EMAIL = "ioanacmuresan@gmail.com"
APP_PASSWORD  = "poeq agxo xfff kmhe"
SNAPSHOT_FILE = "lamajole_seen.json"
URL = "https://lamajole.ro/femei.html"
TARGET_SIZES = ["40/l", "42/l", "38/l", "/l,", "/l ", "marime: l", "marime: 40"]

def get_products():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(URL, headers=headers, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    results = {}
    for item in soup.select("li.product-item, .product-item"):
        name_el = item.select_one("a.product-item-link, strong a")
        if not name_el: continue
        name = name_el.get_text(strip=True)
        url = name_el.get("href", "")
        if not url.startswith("http"): url = "https://lamajole.ro" + url
        text = item.get_text(" ", strip=True).lower()
        if any(s in text for s in TARGET_SIZES):
            import re
            size_m = re.search(r'[mă]rime[:\s]+([^\n]+)', item.get_text(), re.IGNORECASE)
            size = size_m.group(1).strip() if size_m else "L/40"
            price_el = item.select_one(".price")
            price = price_el.get_text(strip=True) if price_el else ""
            results[url] = {"name": name, "size": size, "price": price}
    return results

def send_email(new_items):
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
    print(f"Email trimis: {len(new_items)} produse")

def main():
    current = get_products()
    print(f"Produse L/40 găsite: {len(current)}")
    if os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE) as f:
            seen = json.load(f)
        new_items = {u: d for u, d in current.items() if u not in seen}
        if new_items:
            print(f"Produse NOI: {len(new_items)}")
            send_email(new_items)
        else:
            print("Nicio noutate.")
    else:
        print("Prima rulare — se salvează snapshot-ul.")
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()

# PROGRAMARE AUTOMATĂ:
# Mac/Linux cron (de 2x/zi, 9:00 și 18:00):
#   crontab -e
#   0 9,18 * * * /usr/bin/python3 /calea/catre/lamajole_monitor.py
#
# Windows Task Scheduler: creează task cu trigger la 09:00 și 18:00
