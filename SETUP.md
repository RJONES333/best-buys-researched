# Setup and operations

## What is here

| Path | Purpose |
|---|---|
| `site.json` | Site name, domain, Amazon tag and marketplace |
| `data/categories/*.json` | One file per guide (products, buying guide, sources) |
| `build.py` | Generates the site into `dist/` |
| `scripts/refresh.py` | Monthly check: validates data, verifies source links, stamps the "verified" date |
| `.github/workflows/publish.yml` | Builds and publishes on every push and on the 1st of each month |

Run locally: `python scripts/refresh.py` then `python build.py`.

## Going live (you do these steps, I can't create accounts)

1. **Buy a domain** (about GBP 8-15/year) from any registrar.
2. **Create a GitHub account**, then a **public repository** and upload this folder.
3. In the repo: **Settings > Pages > Source: GitHub Actions**.
4. Edit `site.json`: set `site_url` to your domain (for example `https://yourdomain.co.uk`) and `custom_domain` to `yourdomain.co.uk`. Push the change; the site publishes automatically.
5. At your registrar, point the domain at GitHub Pages (GitHub's docs list the DNS records under Settings > Pages > Custom domain).
6. Add the site to **Google Search Console** and submit `/sitemap.xml`.
7. **Apply to Amazon Associates UK** once the site is live. When approved, put your tracking ID in `amazon_tag` in `site.json` (it looks like `yourname-21`).
8. You have 180 days from approval to make 3 qualifying sales through your links, so get the site indexed early.

## Monthly automation

On the 1st of each month the workflow runs `refresh.py --stamp`, which:

- validates every category file (a data error stops publishing and GitHub emails you),
- checks each source link still loads,
- sets the "Sources verified" date only for guides that pass,
- rebuilds and redeploys.

It does **not** change which products are recommended. "Picks reviewed" only changes when the picks are actually reassessed, so the dates on the page stay honest. The report warns when a guide has not been reviewed for 4 months. Ask me to run a review whenever you like, or once a quarter.

## Adding a guide

Copy `data/categories/_template.json` to a new file, fill it in, and push. The home page, sitemap and structured data update automatically.

## Improving links

Products currently link to an Amazon search for that product, which always works. Once you have your Associates account, add each product's `asin` (the 10-character code in its Amazon URL) so the button goes straight to the product page.
