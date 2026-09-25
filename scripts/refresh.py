#!/usr/bin/env python3
"""Monthly maintenance check. Standard library only.

Usage:
  python scripts/refresh.py            # validate data, check source links and dates, print a report
  python scripts/refresh.py --stamp    # also set "verified" to today for categories that pass
  python scripts/refresh.py --offline  # fast: validate data only, no network, no stamping (used on every push)

What this does:
  - validates every category file,
  - checks each source link still loads,
  - reads each source page's "last updated" date and flags guides whose source was updated
    AFTER our "reviewed" date, and guides whose picks have not been reassessed in 120 days.
    These go into review-queue.md so they can be re-reviewed by hand.

What this does NOT do: it does not change which products are recommended. Product picks
are reviewed separately (the "reviewed" date), so the two dates on each page stay honest.

Exit code 1 means the data is invalid and the site should not be published.
"""
import datetime
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATEGORY_DIR = ROOT / "data" / "categories"
REPORT = ROOT / "refresh-report.md"
QUEUE = ROOT / "review-queue.md"

REQUIRED_CATEGORY = ["slug", "title", "short", "intro", "reviewed", "verified", "products", "guide", "sources"]
REQUIRED_PRODUCT = ["brand", "name", "badge", "best_for", "key_spec", "summary", "specs", "pros", "cons"]
# Sites that block bots answer 401/403/429. That means the page exists, so we do not count it as broken.
REACHABLE_CODES = {401, 403, 429}
USER_AGENT = "Mozilla/5.0 (compatible; SiteMaintenanceCheck/1.0)"
MAX_BYTES = 600_000
OVERDUE_DAYS = 120
POLITE_DELAY = 1.0

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
ISO_RE = r"(\d{4})-(\d{2})-(\d{2})"
DMY_RE = r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})"
MDY_RE = r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})"
LABEL_RE = r"(?:last\s+updated|updated\s+on|updated|last\s+modified|modified)\s*:?\s*"


def validate(cat, filename):
    errors = []
    for key in REQUIRED_CATEGORY:
        if key not in cat:
            errors.append(f"{filename}: missing category field '{key}'")
    for i, p in enumerate(cat.get("products", []), start=1):
        label = f"{filename} product #{i}"
        for key in REQUIRED_PRODUCT:
            if key not in p:
                errors.append(f"{label}: missing field '{key}'")
        if not p.get("asin") and not p.get("search"):
            errors.append(f"{label}: needs an 'asin' or a 'search' term to build its link")
        asin = p.get("asin", "")
        if asin and not (len(asin) == 10 and asin.isalnum()):
            errors.append(f"{label}: asin '{asin}' is not a 10-character code")
    for key in ("reviewed", "verified"):
        try:
            datetime.date.fromisoformat(cat.get(key, ""))
        except ValueError:
            errors.append(f"{filename}: '{key}' must be a YYYY-MM-DD date")
    return errors


def to_date(y, m, d):
    try:
        return datetime.date(int(y), int(m), int(d))
    except ValueError:
        return None


def parse_date_text(text):
    """Find the first date in a short string. Returns a date or None."""
    m = re.search(ISO_RE, text)
    if m:
        return to_date(*m.groups())
    m = re.search(DMY_RE, text)
    if m and m.group(2).lower() in MONTHS:
        return to_date(m.group(3), MONTHS[m.group(2).lower()], m.group(1))
    m = re.search(MDY_RE, text)
    if m and m.group(1).lower() in MONTHS:
        return to_date(m.group(3), MONTHS[m.group(1).lower()], m.group(2))
    return None


def extract_source_date(page):
    """Return (date, how) for the latest 'modified' date found on the page, or (None, reason)."""
    found = []
    for pattern in (
        r'<meta[^>]+(?:property|name)=["\'](?:article:modified_time|og:updated_time|last-modified|revised)["\'][^>]*content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:article:modified_time|og:updated_time|last-modified|revised)["\']',
        r'"dateModified"\s*:\s*"([^"]+)"',
    ):
        for m in re.finditer(pattern, page, flags=re.I):
            d = parse_date_text(m.group(1))
            if d:
                found.append(d)
    if found:
        return max(found), "page metadata"

    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text)[:80_000]
    for m in re.finditer(LABEL_RE, text, flags=re.I):
        d = parse_date_text(text[m.end():m.end() + 40])
        if d:
            found.append(d)
    if found:
        return max(found), "visible 'updated' date"
    return None, "no updated date found"


def fetch(url):
    """Return (ok, detail, page_text or None)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(MAX_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
            return True, str(response.status), raw.decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code in REACHABLE_CODES:
            return True, f"{exc.code} (bot-blocked, page exists)", None
        return False, str(exc.code), None
    except Exception as exc:  # timeouts, DNS failures, TLS errors
        return False, type(exc).__name__, None


def main():
    stamp = "--stamp" in sys.argv
    offline = "--offline" in sys.argv
    today = datetime.date.today()
    today_iso = today.isoformat()
    lines = [f"# Refresh report {today_iso}", ""]
    hard_errors = []
    updated_after_review = []
    overdue = []
    unreadable_dates = 0
    checked_sources = 0

    for path in sorted(CATEGORY_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        cat = json.loads(path.read_text(encoding="utf-8"))
        errors = validate(cat, path.name)
        hard_errors += errors

        reviewed = None if errors else datetime.date.fromisoformat(cat["reviewed"])
        broken = []
        source_notes = []
        for source in ([] if offline else cat.get("sources", [])):
            ok, detail, page = fetch(source["url"])
            checked_sources += 1
            time.sleep(POLITE_DELAY)
            if not ok:
                broken.append(f"{source['name']} ({source['url']}): {detail}")
                continue
            if page is None:
                unreadable_dates += 1
                source_notes.append(f"{source['name']}: source blocks bots, date unknown")
                continue
            src_date, how = extract_source_date(page)
            if src_date is None:
                unreadable_dates += 1
                source_notes.append(f"{source['name']}: {how}")
                continue
            source_notes.append(f"{source['name']}: updated {src_date.isoformat()} ({how})")
            if reviewed and src_date > reviewed:
                updated_after_review.append((cat.get("title", path.name), source["name"], source["url"], src_date, reviewed))

        lines.append(f"## {cat.get('title', path.name)}")
        lines.append(f"- Picks reviewed: {cat.get('reviewed')}")
        lines.append(f"- Products: {len(cat.get('products', []))}")
        lines.append(f"- Products without a direct ASIN link: {sum(1 for p in cat.get('products', []) if not p.get('asin'))}")
        lines += [f"- Source: {n}" for n in source_notes]
        lines += [f"- DATA ERROR: {e}" for e in errors]
        lines += [f"- BROKEN SOURCE: {b}" for b in broken]

        if offline:
            pass
        elif stamp and not errors and not broken:
            if cat["verified"] != today_iso:
                cat["verified"] = today_iso
                path.write_text(json.dumps(cat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            lines.append(f"- Stamped verified = {today_iso}")
        elif stamp:
            lines.append("- NOT stamped: fix the problems above")
        lines.append("")

        if reviewed and (today - reviewed).days > OVERDUE_DAYS:
            overdue.append((cat.get("title", path.name), cat["reviewed"], (today - reviewed).days))
            lines.append(f"- REVIEW DUE: picks have not been reassessed in over {OVERDUE_DAYS} days")
            lines.append("")

    queue = [
        f"# Review queue ({today_iso})",
        "",
        "Guides that need a human or Claude re-review. Generated by scripts/refresh.py each month.",
        "After re-reviewing a guide, update its `reviewed` date in data/categories/<slug>.json.",
        "",
        f"Checked {checked_sources} sources. Could not read an updated date for {unreadable_dates} of them "
        "(bot-blocked, or the page shows no date), so those are not flagged either way.",
        "",
        "## Source updated after we last reviewed",
    ]
    if updated_after_review:
        for title, name, url, src_date, reviewed in sorted(updated_after_review, key=lambda x: x[3], reverse=True):
            queue.append(f"- {title}: {name} updated {src_date.isoformat()}, we reviewed {reviewed.isoformat()} - {url}")
    else:
        queue.append("- None")
    queue += ["", f"## Picks not reassessed in over {OVERDUE_DAYS} days"]
    if overdue:
        for title, reviewed_iso, days in sorted(overdue, key=lambda x: x[2], reverse=True):
            queue.append(f"- {title}: last reviewed {reviewed_iso} ({days} days ago)")
    else:
        queue.append("- None")
    queue.append("")
    if not offline:
        QUEUE.write_text("\n".join(queue), encoding="utf-8")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("\n".join(queue))
    if hard_errors:
        print(f"\n{len(hard_errors)} data error(s). Not safe to publish.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
