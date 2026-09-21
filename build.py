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


def esc(value):
    return html.escape(str(value), quote=True)


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


def load_categories():
    categories = []
    for path in sorted((ROOT / "data" / "categories").glob("*.json")):
        if path.name.startswith("_"):
            continue
        categories.append(json.loads(path.read_text(encoding="utf-8")))
    return categories


def write(rel_path, content):
    target = DIST / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


DISCLOSURE = (
    "As an Amazon Associate we earn from qualifying purchases. "
    "If you buy through our links we may earn a commission at no extra cost to you."
)


def layout(title, description, path, body, jsonld=None):
    canonical = f"{SITE_URL}{path}"
    ld = ""
    if jsonld:
        blocks = jsonld if isinstance(jsonld, list) else [jsonld]
        ld = "".join(
            f'<script type="application/ld+json">{json.dumps(b, ensure_ascii=False)}</script>'
            for b in blocks
        )
    return f"""<!doctype html>
<html lang="{esc(CONFIG['language'])}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{esc(canonical)}">
<link rel="stylesheet" href="{BASE}/assets/style.css">
{ld}
</head>
<body>
<header class="site-header">
  <div class="wrap header-inner">
    <a class="brand" href="{BASE}/">{esc(CONFIG['name'])}</a>
    <nav><a href="{BASE}/">Guides</a><a href="{BASE}/about/">How we pick</a></nav>
  </div>
</header>
<p class="disclosure-bar"><span class="wrap">{esc(DISCLOSURE)}</span></p>
<main class="wrap">
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


def product_card(index, product):
    pid = slugify(f"{product['brand']}-{product['name']}")
    specs = "".join(
        f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in product.get("specs", {}).items()
    )
    pros = "".join(f"<li>{esc(x)}</li>" for x in product.get("pros", []))
    cons = "".join(f"<li>{esc(x)}</li>" for x in product.get("cons", []))
    cons_block = f"<div><h4>Cons</h4><ul class=\"cons\">{cons}</ul></div>" if cons else ""
    return f"""<article class="card" id="{pid}">
  <div class="rank" aria-hidden="true">{index}</div>
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


def category_page(cat):
    year = datetime.date.fromisoformat(cat["reviewed"]).year
    title = f"{cat['title']} ({year}): Our Top Picks"
    products = cat["products"]

    rows = "".join(
        f"<tr><td><a href=\"#{slugify(p['brand'] + '-' + p['name'])}\">{esc(p['brand'])} {esc(p['name'])}</a></td>"
        f"<td>{esc(p['badge'])}</td><td>{esc(p['key_spec'])}</td>"
        f"<td><a class=\"btn small\" href=\"{esc(affiliate_url(p))}\" rel=\"sponsored nofollow noopener\" target=\"_blank\">Check price</a></td></tr>"
        for p in products
    )
    table = (
        '<div class="table-wrap"><table class="compare"><thead><tr>'
        "<th>Product</th><th>Best for</th><th>Key spec</th><th></th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )
    cards = "".join(product_card(i, p) for i, p in enumerate(products, start=1))
    faq = "".join(
        f"<details><summary>{esc(g['q'])}</summary><p>{esc(g['a'])}</p></details>" for g in cat["guide"]
    )
    sources = "".join(
        f'<li><a href="{esc(s["url"])}" rel="noopener nofollow" target="_blank">{esc(s["name"])}</a></li>'
        for s in cat["sources"]
    )
    body = f"""<article>
<h1>{esc(cat['title'])} ({year})</h1>
<p class="meta">Picks reviewed {esc(fmt_month(cat['reviewed']))} · Sources verified {esc(fmt_month(cat['verified']))}</p>
<p class="lead">{esc(cat['intro'])}</p>
<p class="note">We have not hands-on tested these products. Our picks are based on published independent tests and reviews, listed at the bottom of this page. <a href="{BASE}/about/">How we pick</a>.</p>
<h2>Quick comparison</h2>
{table}
<h2>Our picks in detail</h2>
{cards}
<h2>Buying guide</h2>
<div class="faq">{faq}</div>
<h2>Sources</h2>
<ul class="sources">{sources}</ul>
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
            {"@type": "Question", "name": g["q"], "acceptedAnswer": {"@type": "Answer", "text": g["a"]}}
            for g in cat["guide"]
        ],
    }
    return layout(title, cat["short"], f"/{cat['slug']}/", body, [item_list, faq_ld])


def home_page(categories):
    tiles = "".join(
        f"""<a class="tile" href="{BASE}/{c['slug']}/"><h3>{esc(c['title'])}</h3><p>{esc(c['short'])}</p>
<span>{len(c['products'])} picks · reviewed {esc(fmt_month(c['reviewed']))}</span></a>"""
        for c in categories
    )
    body = f"""<section class="hero">
<h1>{esc(CONFIG['name'])}</h1>
<p class="lead">{esc(CONFIG['tagline'])}</p>
</section>
<h2>Buying guides</h2>
<div class="tiles">{tiles}</div>
<h2>How this site works</h2>
<p>We compare products using published independent tests and reviews, then summarise who each one suits. Every guide lists its sources and the date it was last reviewed. <a href="{BASE}/about/">Read how we pick</a>.</p>"""
    return layout(
        f"{CONFIG['name']}: Buying Guides", CONFIG["tagline"], "/", body
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
    return layout(f"Affiliate disclosure | {CONFIG['name']}", "How this site earns money through affiliate links.", "/affiliate-disclosure/", body)


def privacy_page():
    body = f"""<article>
<h1>Privacy</h1>
<p>{esc(CONFIG['name'])} does not run advertising or tracking scripts, and does not set cookies of its own.</p>
<p>When you click a link to Amazon you leave this site. Amazon may set cookies to record that you came from us so a commission can be credited. Amazon's own privacy notice explains how it uses your data.</p>
<p>Our hosting provider may keep standard server logs, such as IP addresses, for security and operations.</p>
<p>If we add analytics in future we will update this page first.</p>
</article>"""
    return layout(f"Privacy | {CONFIG['name']}", "How this site handles your data.", "/privacy/", body)


def not_found_page():
    body = f"""<article><h1>Page not found</h1><p>That page does not exist. <a href="{BASE}/">Back to all guides</a>.</p></article>"""
    return layout(f"Page not found | {CONFIG['name']}", "Page not found.", "/404.html", body)


def sitemap(categories):
    today = datetime.date.today().isoformat()
    urls = [("/", today), ("/about/", today), ("/affiliate-disclosure/", today), ("/privacy/", today)]
    urls += [(f"/{c['slug']}/", c["reviewed"]) for c in categories]
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
    write("index.html", home_page(categories))
    write("about/index.html", about_page())
    write("affiliate-disclosure/index.html", disclosure_page())
    write("privacy/index.html", privacy_page())
    write("404.html", not_found_page())
    for cat in categories:
        write(f"{cat['slug']}/index.html", category_page(cat))
    write("sitemap.xml", sitemap(categories))
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")
    if CONFIG.get("custom_domain"):
        write("CNAME", CONFIG["custom_domain"] + "\n")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Built {len(categories)} categories, {sum(len(c['products']) for c in categories)} products -> {DIST}")


if __name__ == "__main__":
    main()
