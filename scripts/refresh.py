#!/usr/bin/env python3
"""Monthly maintenance check. Standard library only.

Usage:
  python scripts/refresh.py            # validate data and check source links, print a report
  python scripts/refresh.py --stamp    # also set "verified" to today for categories that pass

What this does NOT do: it does not change which products are recommended. Product picks
are reviewed separately (the "reviewed" date), so the two dates on each page stay honest.

Exit code 1 means the data is invalid and the site should not be published.
"""
import datetime
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATEGORY_DIR = ROOT / "data" / "categories"
REPORT = ROOT / "refresh-report.md"

REQUIRED_CATEGORY = ["slug", "title", "short", "intro", "reviewed", "verified", "products", "guide", "sources"]
REQUIRED_PRODUCT = ["brand", "name", "badge", "best_for", "key_spec", "summary", "specs", "pros", "cons"]
# Sites that block bots answer 401/403/429. That means the page exists, so we do not count it as broken.
REACHABLE_CODES = {401, 403, 429}
USER_AGENT = "Mozilla/5.0 (compatible; SiteMaintenanceCheck/1.0)"


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


def check_url(url):
    """Return (ok, detail)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return True, str(response.status)
    except urllib.error.HTTPError as exc:
        if exc.code in REACHABLE_CODES:
            return True, f"{exc.code} (bot-blocked, page exists)"
        return False, str(exc.code)
    except Exception as exc:  # timeouts, DNS failures, TLS errors
        return False, type(exc).__name__


def main():
    stamp = "--stamp" in sys.argv
    today = datetime.date.today().isoformat()
    lines = [f"# Refresh report {today}", ""]
    hard_errors = []

    for path in sorted(CATEGORY_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        cat = json.loads(path.read_text(encoding="utf-8"))
        errors = validate(cat, path.name)
        hard_errors += errors

        broken = []
        for source in cat.get("sources", []):
            ok, detail = check_url(source["url"])
            if not ok:
                broken.append(f"{source['name']} ({source['url']}): {detail}")

        lines.append(f"## {cat.get('title', path.name)}")
        lines.append(f"- Picks reviewed: {cat.get('reviewed')}")
        lines.append(f"- Products: {len(cat.get('products', []))}")
        lines.append(f"- Products without a direct ASIN link: {sum(1 for p in cat.get('products', []) if not p.get('asin'))}")
        lines += [f"- DATA ERROR: {e}" for e in errors]
        lines += [f"- BROKEN SOURCE: {b}" for b in broken]

        if stamp and not errors and not broken:
            if cat["verified"] != today:
                cat["verified"] = today
                path.write_text(json.dumps(cat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            lines.append(f"- Stamped verified = {today}")
        elif stamp:
            lines.append("- NOT stamped: fix the problems above")
        lines.append("")

        reviewed = datetime.date.fromisoformat(cat["reviewed"]) if not errors else None
        if reviewed and (datetime.date.today() - reviewed).days > 120:
            lines.append("- REVIEW DUE: picks have not been reassessed in over 4 months")
            lines.append("")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    if hard_errors:
        print(f"\n{len(hard_errors)} data error(s). Not safe to publish.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
