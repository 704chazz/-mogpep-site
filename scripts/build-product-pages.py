"""Generate a static page per product (e.g. /ghk-cu/index.html) from index.html.

Each page reuses the homepage's styles, cart, checkout and age gate, but gets its
own title, description, canonical URL and Product structured data, and ships the
product detail already rendered in the HTML so search engines can read it.

Run from the repo root after changing products, prices or the homepage:
    python scripts/build-product-pages.py
Requires Node.js (used to render the product template exactly as the site does).
"""
import json
import os
import re
import subprocess
import tempfile
from html import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://mogpep.com/"
src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()


def grab(pattern, flags=re.S):
    m = re.search(pattern, src, flags)
    if not m:
        raise SystemExit(f"Could not find {pattern!r} in index.html")
    return m.group(0)


# --- Render every product with the site's own template (via Node) -------------
js_parts = [
    grab(r"function fmtPrice\(n\)\{.*?\}\n"),
    grab(r"const PRODUCTS = \[.*?\n\];"),
    grab(r"const STOCK = \{.*?\n\};"),
    grab(r"function getStockHTML\(id\) \{.*?\n\}\n"),
    grab(r"const PRODUCT_IMGS = \{.*?\n  \};"),
    grab(r"const PRODUCT_SLUGS = \{.*?\};"),
    grab(r"function productUrl\(id\) \{.*?\}"),
    grab(r"function openProduct\(id\) \{.*?\n\}\n"),
]
harness = """
const window = { MOGPEP_PAGE: 'x' };
const overlay = { innerHTML: '', classList: { add() {} }, scrollTop: 0 };
const document = { getElementById: () => overlay, body: { style: {} } };
const history = { pushState() {} };
const PDP_H = 'h1';
let pdpQty = 1;
%s
const out = {};
for (const p of PRODUCTS) { openProduct(p.id); out[p.id] = { html: overlay.innerHTML, product: p, slug: PRODUCT_SLUGS[p.id], img: PRODUCT_IMGS[p.id] }; }
process.stdout.write(JSON.stringify(out));
""" % "\n".join(js_parts)
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
    tmp.write(harness)
try:
    proc = subprocess.run(["node", tmp.name], capture_output=True, text=True, encoding="utf-8")
finally:
    os.unlink(tmp.name)
if proc.returncode != 0:
    raise SystemExit("Node render failed:\n" + proc.stderr)
rendered = json.loads(proc.stdout)

# --- Strip the homepage-only sections; product pages show the product -----------
start, end = src.index("<!-- HERO -->"), src.index('<div class="disclaimer">')
shell = src[:start] + src[end:]


def set_meta(html, pattern, value):
    new, n = re.subn(pattern, lambda m: m.group(1) + escape(value, quote=True) + m.group(2), html, count=1)
    if n != 1:
        raise SystemExit(f"meta not found: {pattern}")
    return new


sitemap_urls = [SITE]
for pid, r in rendered.items():
    p, slug = r["product"], r["slug"]
    url = f"{SITE}{slug}/"
    name = f"{p['name']} {p['dose']}" if p["dose"] not in p["name"] else p["name"]
    title = f"{name} Research Peptide Australia | {p['sub']} | Mogpep"
    desc = (f"{p['name']} {p['dose']} ({p['sub']}) lyophilised research peptide, ${p['price']:g} AUD. "
            f"≥99% purity, CoA with every order, dispatched from Australia within 48h. Research use only.")
    img = SITE + (r["img"] or "images/logo.png")

    page = shell
    page = page.replace("<head>", f'<head>\n<base href="/">\n<script>window.MOGPEP_PAGE = {json.dumps(pid)};</script>', 1)
    page = re.sub(r"<title>[^<]*</title>", f"<title>{escape(title)}</title>", page, count=1)
    page = set_meta(page, r'(<meta name="description" content=")[^"]*(">)', desc)
    page = set_meta(page, r'(<link rel="canonical" href=")[^"]*(">)', url)
    page = set_meta(page, r'(<meta property="og:url" content=")[^"]*(">)', url)
    page = set_meta(page, r'(<meta property="og:title" content=")[^"]*(">)', title)
    page = set_meta(page, r'(<meta property="og:description" content=")[^"]*(">)', desc)
    page = set_meta(page, r'(<meta property="og:image" content=")[^"]*(">)', img)
    page = set_meta(page, r'(<meta name="twitter:title" content=")[^"]*(">)', title)
    page = set_meta(page, r'(<meta name="twitter:image" content=")[^"]*(">)', img)
    page = re.sub(r'<meta property="og:type" content="[^"]*">', '<meta property="og:type" content="product">', page, count=1)

    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "Product", "@id": url + "#product", "name": f"{p['name']} {p['dose']}", "sku": pid,
         "description": p["description"], "image": img, "brand": {"@type": "Brand", "name": "Mogpep"},
         "offers": {"@type": "Offer", "url": url, "priceCurrency": "AUD", "price": p["price"],
                    "availability": "https://schema.org/InStock",
                    "seller": {"@type": "Organization", "name": "Mogpep Research Solutions", "url": SITE}}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE},
            {"@type": "ListItem", "position": 2, "name": "Research Peptides", "item": SITE + "#products"},
            {"@type": "ListItem", "position": 3, "name": p["name"], "item": url}]}]}
    page, n = re.subn(r'<script type="application/ld\+json">.*?</script>',
                      lambda m: '<script type="application/ld+json">\n' + json.dumps(ld, indent=2, ensure_ascii=False) + "\n</script>",
                      page, count=1, flags=re.S)
    if n != 1:
        raise SystemExit("structured data block not found")

    page = page.replace('<div class="pdp-overlay" id="pdpOverlay"></div>',
                        f'<div class="pdp-overlay open" id="pdpOverlay">{r["html"]}</div>', 1)
    page = page.replace("</body>", f"<script>document.addEventListener('DOMContentLoaded', function () {{ openProduct({json.dumps(pid)}); }});</script>\n</body>", 1)

    os.makedirs(os.path.join(ROOT, slug), exist_ok=True)
    with open(os.path.join(ROOT, slug, "index.html"), "w", encoding="utf-8", newline="") as f:
        f.write(page)
    sitemap_urls.append(url)
    print(f"built /{slug}/")

with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8", newline="\n") as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
    for u in sitemap_urls:
        f.write(f"  <url>\n    <loc>{u}</loc>\n    <changefreq>weekly</changefreq>\n    <priority>{'1.0' if u == SITE else '0.8'}</priority>\n  </url>\n")
    f.write("</urlset>\n")
print(f"sitemap.xml: {len(sitemap_urls)} URLs")
