"""La Majole new-arrivals monitor.

Reads the shop's own GraphQL feed (the same one the website uses), finds
women's pieces in your sizes that were not there on the previous run, and
emails them to you. Standard library only.
"""
import html
import json
import os
import smtplib
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

GRAPHQL = "https://lamajole.ro/graphql"
SITE = "https://lamajole.ro"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json")
PAGE_SIZE = 300
SEED_DAYS = 3        # first run only: email pieces added in the last N days, stay quiet about the rest
MAX_IN_EMAIL = 60

# category id, size attribute and size option ids come from the site itself.
# Women's clothing L/XL, women's shoes 37/39 (shoes carried over from the old monitor).
# To add men's later: cat "2016", attr "marime_haine_barbati", L "1100", XL "1101".
TARGETS = [
    {
        "name": "Femei",
        "cat": "1947",
        "attr": "marime_haine_femei",
        "sizes": {"L": "4289", "XL": "4292"},
    },
    {
        "name": "Femei incaltaminte",
        "cat": "1947",
        "attr": "marime_incaltaminte",
        "sizes": {"37": "996", "39": "1004"},
    },
]

QUERY = """
query($cat: String!, $val: String!, $page: Int!) {
  products(
    filter: {category_id: {eq: $cat}, %s: {eq: $val}}
    pageSize: %d
    currentPage: $page
  ) {
    page_info { total_pages }
    items {
      name url_key sku created_at stock_status
      small_image { url }
      price_range { minimum_price { final_price { value currency } } }
    }
  }
}
"""


def gql(query, variables):
    req = urllib.request.Request(
        GRAPHQL,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (lamajole-monitor)"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    if data.get("errors"):
        raise RuntimeError(data["errors"][0]["message"])
    return data["data"]


def fetch_all(target, size_label):
    """Every in-category piece in one size. The default order is NOT newest first,
    so we always read every page instead of just the first one."""
    q = QUERY % (target["attr"], PAGE_SIZE)
    items, page, total = [], 1, 1
    while page <= total:
        d = gql(q, {"cat": target["cat"], "val": target["sizes"][size_label], "page": page})["products"]
        total = d["page_info"]["total_pages"]
        for it in d["items"]:
            it["size"] = size_label
            items.append(it)
        page += 1
    return items


def collect():
    found = {}
    for t in TARGETS:
        for label in t["sizes"]:
            for it in fetch_all(t, label):
                if it.get("stock_status") == "IN_STOCK":
                    found[it["url_key"]] = it
    return found


def load_state():
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE) as f:
        return set(json.load(f)["seen"])


def save_state(keys):
    with open(STATE_FILE, "w") as f:
        json.dump({"seen": sorted(keys)}, f)


def added_at(item):
    return datetime.strptime(item["created_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def build_email(items):
    items = sorted(items, key=added_at, reverse=True)
    shown = items[:MAX_IN_EMAIL]
    rows = []
    for it in shown:
        p = it["price_range"]["minimum_price"]["final_price"]
        img = (it.get("small_image") or {}).get("url") or ""
        link = f"{SITE}/{it['url_key']}.html"
        rows.append(
            f'<tr><td style="padding:8px"><a href="{link}"><img src="{html.escape(img)}" width="90"></a></td>'
            f'<td style="padding:8px"><a href="{link}">{html.escape(it["name"])}</a><br>'
            f'Marime {it["size"]} &middot; {p["value"]:g} {p["currency"]}<br>'
            f'<small>adaugat {it["created_at"]} UTC</small></td></tr>'
        )
    more = f"<p>... si inca {len(items) - len(shown)} piese pe site.</p>" if len(items) > len(shown) else ""
    body = f'<table style="font-family:sans-serif">{"".join(rows)}</table>{more}'
    return f"La Majole: {len(items)} piese noi in marimile tale", body


def send_email(subject, body):
    user = os.environ["SENDER_EMAIL"]
    pwd = os.environ["APP_PASSWORD"]
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, os.environ.get("NOTIFY_EMAIL") or user
    msg.attach(MIMEText(body, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(user, pwd)
        s.send_message(msg)


def main():
    current = collect()
    seen = load_state()

    if not current:
        # Never overwrite memory with an empty result: that means the fetch went wrong.
        print("Got 0 items, treating as a failed fetch.", file=sys.stderr)
        return 1

    if seen is None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=SEED_DAYS)
        new = [it for it in current.values() if added_at(it) > cutoff]
        print(f"First run: {len(current)} pieces indexed, {len(new)} from the last {SEED_DAYS} days.")
    else:
        new = [it for k, it in current.items() if k not in seen]
        print(f"{len(current)} pieces in your sizes, {len(new)} new since last run.")

    if new:
        send_email(*build_email(new))   # if this raises, state is not saved, so we retry next run
        print("Email sent.")

    save_state(set(current))
    return 0


if __name__ == "__main__":
    sys.exit(main())
