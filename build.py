#!/usr/bin/env python3
"""Static site generator for the affiliate guides site. Standard library only.

Usage: python build.py
Reads site.json and data/categories/*.json, writes the finished site to dist/.
"""
import datetime
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
CONFIG = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
BASE = CONFIG.get("base_path", "").rstrip("/")
SITE_URL = CONFIG["site_url"].rstrip("/")

# Groups categories for the homepage and for "related guides" cross-links.
# A slug not listed here falls back to "More guides" so a new category file
# never breaks the build; add it here when convenient.
GROUPS = {
    "Kitchen": [
        "air-fryers", "coffee-machines", "slow-cookers", "kettles", "blenders",
        "toasters", "microwaves", "food-processors", "fridge-freezers", "dishwashers", "bread-makers", "rice-cookers", "stand-mixers", "ice-cream-makers", "coffee-grinders", "sandwich-toasters", "electric-grills",
        "kitchen-knives", "food-storage-containers", "lunch-boxes",
    ],
    "Laundry, heating & air": [
        "washing-machines", "tumble-dryers", "steam-irons", "heated-airers",
        "dehumidifiers", "humidifiers", "air-purifiers", "air-quality-monitors", "fans", "portable-air-conditioners",
        "electric-heaters", "electric-blankets",
    ],
    "Cleaning": ["robot-vacuums", "cordless-vacuums", "corded-vacuum-cleaners", "steam-cleaners"],
    "Audio & TV": [
        "wireless-earbuds", "over-ear-headphones", "on-ear-headphones", "kids-headphones",
        "workout-headphones", "gaming-headsets", "bluetooth-speakers", "soundbars", "tvs", "projectors",
    ],
    "Computing & desk": [
        "laptops", "tablets", "pc-monitors", "monitor-arms", "mechanical-keyboards",
        "gaming-mice", "webcams", "pc-conference-headsets", "external-ssds", "wifi-routers", "printers",
        "standing-desks", "office-chairs", "gaming-chairs",
    ],
    "Phones, power & wearables": [
        "smartphones", "samsung-chargers", "iphone-charging-cables", "power-banks",
        "portable-power-stations", "smartwatches", "smart-rings",
    ],
    "Smart home & security": ["video-doorbells", "home-security-cameras", "action-cameras", "smart-plugs"],
    "Sleep & comfort": ["mattresses", "mattress-toppers", "pillows", "duvets", "pregnancy-pillows"],
    "Bathroom": ["bath-towels", "shower-heads"],
    "Gym & fitness": [
        "adjustable-dumbbells", "resistance-bands", "rowing-machines",
        "exercise-bikes", "yoga-mats", "massage-guns",
    ],
    "Camping & hiking": ["family-tents", "sleeping-bags", "hiking-boots"],
    "Cycling": ["bike-lights", "cycling-helmets"],
    "Clothing": [
        "mens-down-jackets", "womens-puffer-jackets", "mens-belts", "ski-jackets",
        "womens-leggings", "running-socks", "walking-socks", "womens-socks", "winter-gloves",
        "heated-gilets", "foot-warmers", "mens-boxers",
    ],
    "Golf": ["golf-club-sets", "golf-balls", "golf-gloves", "golf-shirts", "golf-trousers", "golf-shoes", "golf-rangefinders", "golf-bags", "golf-trolleys", "golf-push-trolleys", "golf-umbrellas", "womens-golf-shirts", "womens-golf-shoes", "womens-golf-trousers"],
    "Sports": ["football-boots", "running-shoes", "gym-training-shoes", "tennis-rackets", "swimming-goggles"],
    "Personal care": ["electric-toothbrushes"],
    "Men": ["electric-shavers", "hair-clippers", "beard-trimmers", "nose-hair-trimmers", "mens-hair-removal-cream"],
    "Women": ["epilators", "bikini-trimmers", "ipl-hair-removal", "hair-dryers", "hair-straighteners", "travel-hair-dryers"],
    "Kids": ["trending-kids-toys", "trampolines", "balance-bikes", "kids-scooters"],
    "Lighting": ["smart-bulbs"],
    "Garden": [
        "lawn-mowers", "pressure-washers", "bbqs", "hedge-trimmers",
        "garden-pest-repellers", "leaf-blowers", "robot-lawn-mowers",
        "grass-trimmers",
    ],
    "DIY & tools": ["cordless-drills", "tool-sets", "smoke-alarms", "carbon-monoxide-alarms", "circular-saws", "jigsaws", "multi-tools", "mitre-saws", "impact-drivers", "sanders"],
    "Automotive": ["dash-cams", "tyre-inflators", "car-phone-mounts", "jump-starters", "car-vacuum-cleaners", "car-battery-chargers", "wiper-blades", "car-seat-covers", "car-sun-shades", "car-shampoo", "car-scratch-removers", "car-wax-sealant"],
    "Luggage & travel": ["suitcases", "travel-adaptors"],
    "Pet supplies": ["dog-beds", "cat-carriers", "automatic-pet-feeders", "pet-cameras", "dog-poo-bags"],
    "Baby": ["baby-monitors", "pushchairs", "toddler-car-seats", "baby-carriers", "high-chairs", "travel-cots", "baby-bouncers", "breast-pumps", "stair-gates", "baby-bottles", "sterilisers", "changing-bags", "newborn-cribs", "travel-systems", "lightweight-strollers", "double-buggies", "baby-car-seats", "nursing-bras", "baby-carrier-backpacks", "cabin-approved-strollers"],
}


def group_for(slug):
    for group, slugs in GROUPS.items():
        if slug in slugs:
            return group
    return "More guides"


# Sidebar/homepage groups that nest visually under a parent group, e.g. Golf
# is shown as a subsection of Sports rather than its own top-level heading.
# group_for() still returns the child name ("Golf") so breadcrumbs can note
# it; PARENT_OF resolves that up to the top-level group for display.
PARENT_OF = {"Golf": "Sports", "Men": "Personal care", "Women": "Personal care"}


def top_group_for(slug):
    return PARENT_OF.get(group_for(slug), group_for(slug))


def sidebar_label(title):
    """Drop the leading "Best " from a guide title for quicker skimming in the
    sidebar menu. Full titles are kept everywhere else (H1s, tiles, <title>)."""
    return re.sub(r"^Best\s+", "", title)


def sidebar_nav(categories, current_slug):
    """A menu of every category, grouped. Sticky on the left on desktop; a plain
    block below the article on mobile (no JS, no fragile <details> CSS override)."""
    by_group = {}
    for c in categories:
        by_group.setdefault(group_for(c["slug"]), []).append(c)

    group_order = list(GROUPS.keys())
    ordered_groups = [g for g in group_order if g in by_group]
    ordered_groups += [g for g in by_group if g not in ordered_groups]
    top_groups = [g for g in ordered_groups if g not in PARENT_OF]

    def render_items(items):
        return "".join(
            f'<li><a href="{BASE}/{c["slug"]}/"{" aria-current=\"page\"" if c["slug"] == current_slug else ""}>{esc(sidebar_label(c["title"]))}</a></li>'
            for c in items
        )

    sections = []
    for group in top_groups:
        parts = [f'<p class="sidebar-heading">{esc(group)}</p><ul>{render_items(by_group[group])}</ul>']
        for child in [g for g in ordered_groups if PARENT_OF.get(g) == group]:
            parts.append(f'<p class="sidebar-subheading">{esc(child)}</p><ul>{render_items(by_group[child])}</ul>')
        sections.append("".join(parts))
    sections_html = "".join(sections)

    return f"""<nav class="sidebar-nav" aria-label="All guides">
  <p class="sidebar-title">Browse all guides</p>
  {sections_html}
</nav>"""


def esc(value):
    return html.escape(str(value), quote=True)


def linkify(text):
    """Escape text, but turn `[label](/some/path/)` into a real internal link
    first. Only relative, site-internal paths (starting with '/') are
    accepted; anything else is left as plain escaped text. Lets guide
    answers and hub intros safely link to other guides without allowing
    arbitrary HTML."""
    parts = []
    last = 0
    for m in re.finditer(r"\[([^\]]+)\]\((/[a-z0-9/-]*)\)", text):
        parts.append(esc(text[last:m.start()]))
        label, url = m.group(1), m.group(2)
        parts.append(f'<a href="{BASE}{esc(url)}">{esc(label)}</a>')
        last = m.end()
    parts.append(esc(text[last:]))
    return "".join(parts)


def delink(text):
    """Strip `[label](/path/)` markdown-link syntax down to just the label,
    for plain-text contexts like JSON-LD that shouldn't contain markup."""
    return re.sub(r"\[([^\]]+)\]\((/[a-z0-9/-]*)\)", r"\1", text)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def fmt_month(iso):
    return datetime.date.fromisoformat(iso).strftime("%B %Y")


def affiliate_url(product):
    tag = CONFIG["amazon_tag"]
    domain = CONFIG["amazon_domain"]
    if product.get("asin"):
        return f"https://{domain}/dp/{product['asin']}?tag={tag}"
    query = quote_plus(product.get("search") or f"{product['brand']} {product['name']}")
    return f"https://{domain}/s?k={query}&tag={tag}"


def source_names(categories, limit=10):
    """Unique publication names cited across all guides, in first-seen order,
    for the homepage trust bar. Strips anything after a colon, e.g.
    "Expert Reviews: best kettles" -> "Expert Reviews"."""
    seen = []
    for c in categories:
        for s in c.get("sources", []):
            name = s["name"].split(":")[0].strip()
            if name not in seen:
                seen.append(name)
    return seen[:limit]


def load_categories():
    categories = []
    for path in sorted((ROOT / "data" / "categories").glob("*.json")):
        if path.name.startswith("_"):
            continue
        categories.append(json.loads(path.read_text(encoding="utf-8")))
    return categories


def load_hubs():
    """Gift-guide hub pages: curated groupings of existing category guides,
    e.g. 'Gifts for golfers'. Each hub only links to guides that already
    exist and are already sourced; no new product research happens here."""
    hubs = []
    hub_dir = ROOT / "data" / "hubs"
    if not hub_dir.exists():
        return hubs
    for path in sorted(hub_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        hubs.append(json.loads(path.read_text(encoding="utf-8")))
    return hubs


def write(rel_path, content):
    target = DIST / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


DISCLOSURE = (
    "As an Amazon Associate we earn from qualifying purchases. "
    "If you buy through our links we may earn a commission at no extra cost to you."
)


def layout(title, description, path, body, jsonld=None, wide=False, noindex=False):
    canonical = f"{SITE_URL}{path}"
    og_image = f"{SITE_URL}{BASE}/assets/og-image.png"
    robots_meta = '<meta name="robots" content="noindex,follow">\n' if noindex else ""
    ld = ""
    if jsonld:
        blocks = jsonld if isinstance(jsonld, list) else [jsonld]
        ld = "".join(
            f'<script type="application/ld+json">{json.dumps(b, ensure_ascii=False)}</script>'
            for b in blocks
        )
    main_class = "wrap wrap-wide" if wide else "wrap"
    return f"""<!doctype html>
<html lang="{esc(CONFIG['language'])}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
{robots_meta}<link rel="canonical" href="{esc(canonical)}">
<link rel="icon" type="image/svg+xml" href="{BASE}/assets/favicon.svg">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:site_name" content="{esc(CONFIG['name'])}">
<meta property="og:image" content="{esc(og_image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(description)}">
<meta name="twitter:image" content="{esc(og_image)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Sora:wght@600;700;800&display=swap">
<link rel="stylesheet" href="{BASE}/assets/style.css">
{ld}
</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header">
  <div class="wrap header-inner">
    <a class="brand" href="{BASE}/">{esc(CONFIG['name'])}</a>
    <nav><a href="{BASE}/">Guides</a><a href="{BASE}/gift-guides/">Gift guides</a><a href="{BASE}/about/">How we pick</a></nav>
  </div>
</header>
<p class="disclosure-bar"><span class="wrap">{esc(DISCLOSURE)}</span></p>
<main class="{main_class}" id="main">
{body}
</main>
<footer class="site-footer">
  <div class="wrap">
    <p>{esc(DISCLOSURE)}</p>
    <p><a href="{BASE}/about/">How we pick</a> · <a href="{BASE}/affiliate-disclosure/">Affiliate disclosure</a> · <a href="{BASE}/privacy/">Privacy</a></p>
    <p>&copy; {datetime.date.today().year} {esc(CONFIG['name'])}</p>
  </div>
</footer>
</body>
</html>
"""


def breadcrumb(items):
    """items: list of (label, url_or_None). Last item has no link. Returns (html, jsonld)."""
    parts = []
    for i, (label, url) in enumerate(items):
        if url:
            parts.append(f'<a href="{esc(url)}">{esc(label)}</a>')
        else:
            parts.append(f'<span aria-current="page">{esc(label)}</span>')
    html_nav = f'<nav class="breadcrumb" aria-label="Breadcrumb">{" <span class=\"sep\">/</span> ".join(parts)}</nav>'
    ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "name": label,
                **({"item": url} if url else {}),
            }
            for i, (label, url) in enumerate(items)
        ],
    }
    return html_nav, ld


RANK_CLASS = {1: " rank-gold", 2: " rank-silver", 3: " rank-bronze"}


def product_card(index, product):
    pid = slugify(f"{product['brand']}-{product['name']}")
    specs = "".join(
        f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in product.get("specs", {}).items()
    )
    pros = "".join(f"<li>{esc(x)}</li>" for x in product.get("pros", []))
    cons = "".join(f"<li>{esc(x)}</li>" for x in product.get("cons", []))
    cons_block = f"<div><h4>Cons</h4><ul class=\"cons\">{cons}</ul></div>" if cons else ""
    rank_class = RANK_CLASS.get(index, "")
    return f"""<article class="card" id="{pid}">
  <div class="rank{rank_class}" aria-hidden="true">{index}</div>
  <div class="card-body">
    <p class="badge">{esc(product['badge'])}</p>
    <h3>{esc(product['brand'])} {esc(product['name'])}</h3>
    <p>{esc(product['summary'])}</p>
    <dl class="specs">{specs}</dl>
    <div class="proscons">
      <div><h4>Pros</h4><ul class="pros">{pros}</ul></div>
      {cons_block}
    </div>
    <p><a class="btn" href="{esc(affiliate_url(product))}" rel="sponsored nofollow noopener" target="_blank">Check price on Amazon</a></p>
  </div>
</article>"""


def spotlight(cat):
    """A prominent 'top pick' box for the #1 product, shown above the comparison table."""
    top = cat["products"][0]
    pros = "".join(f"<li>{esc(x)}</li>" for x in top.get("pros", [])[:3])
    pid = slugify(f"{top['brand']}-{top['name']}")
    return f"""<div class="spotlight">
  <div class="spotlight-rank" aria-hidden="true">1</div>
  <div class="spotlight-body">
    <p class="eyebrow">Our top pick</p>
    <h2 class="spotlight-title"><a href="#{pid}">{esc(top['brand'])} {esc(top['name'])}</a></h2>
    <p class="badge">{esc(top['badge'])}</p>
    <p>{esc(top['summary'])}</p>
    <ul class="spotlight-pros">{pros}</ul>
    <div class="spotlight-actions">
      <a class="btn" href="{esc(affiliate_url(top))}" rel="sponsored nofollow noopener" target="_blank">Check price on Amazon</a>
      <a class="btn-text" href="#{pid}">See full review and all {len(cat['products'])} picks &darr;</a>
    </div>
  </div>
</div>"""


def category_page(cat, all_categories):
    year = datetime.date.fromisoformat(cat["reviewed"]).year
    title = f"{cat['title']} ({year}): Our Top Picks"
    products = cat["products"]
    group = top_group_for(cat["slug"])

    crumb_html, crumb_ld = breadcrumb([
        ("Guides", f"{SITE_URL}/"),
        (group, f"{SITE_URL}/#{slugify(group)}"),
        (cat["title"], None),
    ])

    rows = "".join(
        f"<tr><td><a href=\"#{slugify(p['brand'] + '-' + p['name'])}\">{esc(p['brand'])} {esc(p['name'])}</a></td>"
        f"<td>{esc(p['badge'])}</td><td>{esc(p['key_spec'])}</td>"
        f"<td><a class=\"btn small\" href=\"{esc(affiliate_url(p))}\" rel=\"sponsored nofollow noopener\" target=\"_blank\">Check price</a></td></tr>"
        for p in products
    )
    table = (
        '<div class="table-wrap"><table class="compare">'
        f'<caption class="sr-only">Quick comparison of all {esc(cat["title"])}</caption>'
        "<thead><tr>"
        "<th scope=\"col\">Product</th><th scope=\"col\">Best for</th><th scope=\"col\">Key spec</th><th scope=\"col\">Buy</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )
    cards = "".join(product_card(i, p) for i, p in enumerate(products, start=1))
    faq = "".join(
        f"<details><summary>{esc(g['q'])}</summary><p>{linkify(g['a'])}</p></details>" for g in cat["guide"]
    )
    sources = "".join(
        f'<li><a href="{esc(s["url"])}" rel="noopener nofollow" target="_blank">{esc(s["name"])}</a></li>'
        for s in cat["sources"]
    )

    related = [c for c in all_categories if group_for(c["slug"]) == group and c["slug"] != cat["slug"]][:4]
    related_heading = "Related guides"
    if len(related) < 4:
        # Small or single-category groups (e.g. Lighting, Bathroom) would
        # otherwise dead-end with nothing else to click through to; top up
        # with other guides site-wide so every page always links onward.
        fallback = [
            c for c in all_categories
            if c["slug"] != cat["slug"] and c not in related
        ]
        related = related + fallback[: 4 - len(related)]
        related_heading = "You might also like"
    related_html = ""
    if related:
        related_items = "".join(
            f'<a class="tile" href="{BASE}/{r["slug"]}/"><h3>{esc(r["title"])}</h3><p>{esc(r["short"])}</p></a>'
            for r in related
        )
        related_html = f"""<h2>{related_heading}</h2>
<div class="tiles">{related_items}</div>"""

    body = f"""<article>
{crumb_html}
<h1>{esc(cat['title'])} ({year})</h1>
<p class="meta">Picks reviewed {esc(fmt_month(cat['reviewed']))} · Sources verified {esc(fmt_month(cat['verified']))}</p>
<p class="lead">{esc(cat['intro'])}</p>
<p class="note">We have not hands-on tested these products. Our picks are based on published independent tests and reviews, listed at the bottom of this page. <a href="{BASE}/about/">How we pick</a>.</p>
{spotlight(cat)}
<h2>Quick comparison</h2>
{table}
<h2>Our picks in detail</h2>
{cards}
<h2>Buying guide</h2>
<div class="faq">{faq}</div>
<h2>Sources</h2>
<ul class="sources">{sources}</ul>
{related_html}
</article>"""

    item_list = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": cat["title"],
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i,
                "name": f"{p['brand']} {p['name']}",
                "url": f"{SITE_URL}/{cat['slug']}/#{slugify(p['brand'] + '-' + p['name'])}",
            }
            for i, p in enumerate(products, start=1)
        ],
    }
    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": g["q"], "acceptedAnswer": {"@type": "Answer", "text": delink(g["a"])}}
            for g in cat["guide"]
        ],
    }
    return layout(title, cat["short"], f"/{cat['slug']}/", body, [item_list, faq_ld, crumb_ld])


def hub_page(hub, categories_by_slug):
    """A gift-guide hub: a curated set of links to existing, already-sourced
    category guides, grouped for a recipient or occasion (e.g. Christmas
    gifts for golfers). No new product claims are made here; each tile
    surfaces that guide's own #1 pick and links through to the full guide,
    where sources and the rest of the comparison live."""
    picks = [
        {**p, "cat": categories_by_slug[p["category_slug"]]}
        for p in hub["picks"]
        if p["category_slug"] in categories_by_slug
    ]

    crumb_html, crumb_ld = breadcrumb([
        ("Guides", f"{SITE_URL}/"),
        ("Gift guides", f"{SITE_URL}/gift-guides/"),
        (hub["title"], None),
    ])

    cards = []
    for p in picks:
        cat = p["cat"]
        top = cat["products"][0]
        cards.append(f"""<a class="tile gift-tile" href="{BASE}/{cat['slug']}/">
  <h3>{esc(cat['title'])}</h3>
  <p class="gift-note">{esc(p['note'])}</p>
  <p class="gift-top-pick"><strong>Top pick:</strong> {esc(top['brand'])} {esc(top['name'])} &mdash; {esc(top['badge'])}</p>
</a>""")
    cards_html = f'<div class="tiles">{"".join(cards)}</div>'

    body = f"""<article>
{crumb_html}
<h1>{esc(hub['title'])}</h1>
<p class="meta">Updated {esc(fmt_month(hub['updated']))}</p>
<p class="lead">{linkify(hub['intro'])}</p>
<p class="note">Every guide linked below lists its own sources, and we have not hands-on tested these products ourselves. <a href="{BASE}/about/">How we pick</a>.</p>
{cards_html}
</article>"""

    item_list = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": hub["title"],
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i,
                "name": p["cat"]["title"],
                "url": f"{SITE_URL}/{p['cat']['slug']}/",
            }
            for i, p in enumerate(picks, start=1)
        ],
    }
    return layout(f"{hub['title']} | {CONFIG['name']}", hub["short"], f"/{hub['slug']}/", body, [item_list, crumb_ld])


def gift_guides_index_page(hubs):
    crumb_html, crumb_ld = breadcrumb([
        ("Guides", f"{SITE_URL}/"),
        ("Gift guides", None),
    ])
    tiles = "".join(
        f'<a class="tile" href="{BASE}/{h["slug"]}/"><h3>{esc(h["title"])}</h3><p>{esc(h["short"])}</p></a>'
        for h in hubs
    )
    body = f"""<article>
{crumb_html}
<h1>Gift Guides</h1>
<p class="lead">Struggling to know what to buy? These guides group our research-based picks by who they're for, pulling the top recommendation from each relevant buying guide.</p>
{f'<div class="tiles">{tiles}</div>' if hubs else '<p>New gift guides are coming soon.</p>'}
</article>"""
    return layout(
        f"Gift Guides | {CONFIG['name']}",
        "Gift guide hubs grouping our research-based buying guides by recipient and occasion.",
        "/gift-guides/",
        body,
        crumb_ld,
    )


def home_page(categories, hubs=None):
    by_group = {}
    for c in categories:
        by_group.setdefault(group_for(c["slug"]), []).append(c)

    # Show groups in a fixed, sensible order; any unlisted group (e.g. a
    # future "More guides" catch-all) is appended after.
    group_order = list(GROUPS.keys())
    ordered_groups = [g for g in group_order if g in by_group]
    ordered_groups += [g for g in by_group if g not in ordered_groups]

    def tiles_for(items):
        return "".join(
            f"""<a class="tile" href="{BASE}/{c['slug']}/" data-search="{esc((c['title'] + ' ' + c['short']).lower())}"><h3>{esc(c['title'])}</h3><p>{esc(c['short'])}</p>
<span>{len(c['products'])} picks · reviewed {esc(fmt_month(c['reviewed']))}</span></a>"""
            for c in items
        )

    top_groups = [g for g in ordered_groups if g not in PARENT_OF]
    sections = []
    for group in top_groups:
        inner = f'<div class="tiles">{tiles_for(by_group[group])}</div>'
        for child in [g for g in ordered_groups if PARENT_OF.get(g) == group]:
            inner += (
                f'<div class="guide-subgroup"><h3 class="guide-subgroup-title">{esc(child)}</h3>'
                f'<div class="tiles">{tiles_for(by_group[child])}</div></div>'
            )
        sections.append(f'<section class="guide-group" id="{slugify(group)}"><h2>{esc(group)}</h2>\n{inner}</section>')
    tiles_html = "\n".join(sections)

    total_products = sum(len(c["products"]) for c in categories)
    sources = source_names(categories)
    trust_bar = "".join(f"<span>{esc(s)}</span>" for s in sources)

    body = f"""<div class="page-grid">
{sidebar_nav(categories, current_slug=None)}
<article>
<section class="hero">
<h1>{esc(CONFIG['name'])}</h1>
<p class="lead">{esc(CONFIG['tagline'])}</p>
<p class="hero-stats">{len(categories)} guides &middot; {total_products} products researched &middot; updated monthly</p>
</section>
{f'<a class="gift-promo" href="{BASE}/gift-guides/">&#127873; Not sure what to buy? Browse our <strong>gift guides</strong> &rarr;</a>' if hubs else ''}
<div class="trust-bar">
  <span class="trust-label">Sourced from</span>
  {trust_bar}
  <span>and more</span>
</div>
<div class="search-box">
  <label for="guide-search" class="sr-only">Search guides</label>
  <input type="search" id="guide-search" placeholder="Search guides, e.g. air fryer, headphones, running">
</div>
{tiles_html}
<p class="no-results" id="no-results" hidden>No guides match that search. <a href="{BASE}/">Clear search</a> to see all {len(categories)}.</p>
<h2>How this site works</h2>
<p>We compare products using published independent tests and reviews, then summarise who each one suits. Every guide lists its sources and the date it was last reviewed. <a href="{BASE}/about/">Read how we pick</a>.</p>
</article>
</div>
<script>
(function () {{
  var input = document.getElementById('guide-search');
  var noResults = document.getElementById('no-results');
  if (!input) return;
  var groups = document.querySelectorAll('.guide-group');
  input.addEventListener('input', function () {{
    var q = input.value.trim().toLowerCase();
    var anyVisibleOverall = false;
    groups.forEach(function (group) {{
      var anyVisible = false;
      group.querySelectorAll('.tile').forEach(function (tile) {{
        var match = !q || tile.getAttribute('data-search').indexOf(q) !== -1;
        tile.style.display = match ? '' : 'none';
        if (match) anyVisible = true;
      }});
      group.style.display = anyVisible ? '' : 'none';
      if (anyVisible) anyVisibleOverall = true;
    }});
    if (noResults) noResults.hidden = anyVisibleOverall;
  }});
}})();
</script>"""

    website_ld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": CONFIG["name"],
        "url": f"{SITE_URL}/",
        "description": CONFIG["tagline"],
    }
    org_ld = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": CONFIG["name"],
        "url": f"{SITE_URL}/",
    }
    home_description = (
        f"{len(categories)} research-based UK buying guides built from independent tests: "
        "air fryers, headphones, vacuum cleaners, TVs, laptops, mattress toppers and more. "
        "Sources listed on every guide."
    )
    return layout(
        f"{CONFIG['name']}: Independent UK Buying Guides",
        home_description,
        "/",
        body,
        [website_ld, org_ld],
        wide=True,
    )


def about_page():
    body = f"""<article>
<h1>How we pick</h1>
<p>{esc(CONFIG['name'])} publishes buying guides based on research, not personal testing. We do not claim to have used the products we list.</p>
<h2>Our process</h2>
<ul>
<li>We read independent tests and reviews from established UK publications and consumer groups.</li>
<li>We shortlist products that keep appearing near the top, and note what each is best for, its main strengths and its drawbacks.</li>
<li>We list our sources at the bottom of every guide so you can read the original tests.</li>
</ul>
<h2>Updates</h2>
<p>Each guide shows two dates. <strong>Picks reviewed</strong> is when we last reassessed which products to recommend. <strong>Sources verified</strong> is when an automated monthly check last confirmed our source links still work. The second date can be newer than the first when nothing changed.</p>
<h2>How we earn money</h2>
<p>Links to Amazon are affiliate links. If you buy after clicking, we may earn a commission at no extra cost to you. This does not change which products we recommend. See our <a href="{BASE}/affiliate-disclosure/">affiliate disclosure</a>.</p>
<h2>Prices</h2>
<p>We do not show prices because they change constantly. Use the button on each product to see the current price on Amazon.</p>
</article>"""
    return layout(f"How we pick | {CONFIG['name']}", "How we research and choose the products we recommend.", "/about/", body)


def disclosure_page():
    body = f"""<article>
<h1>Affiliate disclosure</h1>
<p>{esc(DISCLOSURE)}</p>
<p>{esc(CONFIG['name'])} is a participant in the Amazon EU Associates Programme, an affiliate advertising programme designed to provide a means for sites to earn advertising fees by advertising and linking to Amazon.co.uk.</p>
<p>Links marked as sponsored are affiliate links. Buying through them costs you nothing extra. Commissions do not influence which products we recommend or how we describe them.</p>
</article>"""
    return layout(f"Affiliate disclosure | {CONFIG['name']}", "How this site earns money through affiliate links.", "/affiliate-disclosure/", body, noindex=True)


def privacy_page():
    body = f"""<article>
<h1>Privacy</h1>
<p>{esc(CONFIG['name'])} does not run advertising or tracking scripts, and does not set cookies of its own.</p>
<p>When you click a link to Amazon you leave this site. Amazon may set cookies to record that you came from us so a commission can be credited. Amazon's own privacy notice explains how it uses your data.</p>
<p>Our hosting provider may keep standard server logs, such as IP addresses, for security and operations.</p>
<p>If we add analytics in future we will update this page first.</p>
</article>"""
    return layout(f"Privacy | {CONFIG['name']}", "How this site handles your data.", "/privacy/", body, noindex=True)


def not_found_page():
    body = f"""<article><h1>Page not found</h1><p>That page does not exist. <a href="{BASE}/">Back to all guides</a>.</p></article>"""
    return layout(f"Page not found | {CONFIG['name']}", "Page not found.", "/404.html", body)


def sitemap(categories, hubs):
    today = datetime.date.today().isoformat()
    urls = [("/", today), ("/about/", today)]
    urls += [(f"/{c['slug']}/", c["reviewed"]) for c in categories]
    if hubs:
        urls += [("/gift-guides/", today)]
        urls += [(f"/{h['slug']}/", h["updated"]) for h in hubs]
    items = "".join(
        f"<url><loc>{esc(SITE_URL + u)}</loc><lastmod>{d}</lastmod></url>" for u, d in urls
    )
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>\n'


def main():
    if "YOUR" in CONFIG["amazon_tag"]:
        print("WARNING: amazon_tag in site.json is still a placeholder. Links will not earn commission.", file=sys.stderr)
    if "example.com" in CONFIG["site_url"]:
        print("WARNING: site_url in site.json is still a placeholder.", file=sys.stderr)

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    shutil.copytree(ROOT / "static", DIST / "assets")

    categories = load_categories()
    hubs = load_hubs()
    categories_by_slug = {c["slug"]: c for c in categories}
    write("index.html", home_page(categories, hubs))
    write("about/index.html", about_page())
    write("affiliate-disclosure/index.html", disclosure_page())
    write("privacy/index.html", privacy_page())
    write("404.html", not_found_page())
    for cat in categories:
        write(f"{cat['slug']}/index.html", category_page(cat, categories))
    if hubs:
        write("gift-guides/index.html", gift_guides_index_page(hubs))
        for hub in hubs:
            write(f"{hub['slug']}/index.html", hub_page(hub, categories_by_slug))
    write("sitemap.xml", sitemap(categories, hubs))
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")
    if CONFIG.get("custom_domain"):
        write("CNAME", CONFIG["custom_domain"] + "\n")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Built {len(categories)} categories, {sum(len(c['products']) for c in categories)} products, {len(hubs)} gift guides -> {DIST}")


if __name__ == "__main__":
    main()
