"""
Romax Digital – Wallet Pass Creator
scraping.py – Website scraping, brand extraction & multi-design variant generation
"""

import re
import base64
import requests
from collections import Counter
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

try:
    from PIL import Image
    import io as _io
except ImportError:  # pragma: no cover
    Image = None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

# Colour helpers

def hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return r, g, b


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return "#{:02X}{:02X}{:02X}".format(
        max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b)))
    )


def luminance(hex_color: str) -> float:
    r, g, b = [x / 255.0 for x in hex_to_rgb(hex_color)]

    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def saturation(hex_color: str) -> float:
    r, g, b = [x / 255.0 for x in hex_to_rgb(hex_color)]
    mx, mn = max(r, g, b), min(r, g, b)
    return 0 if mx == 0 else (mx - mn) / mx


def is_greyish(hex_color: str) -> bool:
    """True for near-white / near-black / low-saturation greys we don't want as 'brand' colours."""
    lum = luminance(hex_color)
    if lum > 0.94 or lum < 0.06:
        return True
    return saturation(hex_color) < 0.12


def best_foreground(bg_hex: str) -> str:
    return "#FFFFFF" if luminance(bg_hex) < 0.35 else "#000000"


def mix(hex_a: str, hex_b: str, ratio: float) -> str:
    ra, ga, ba = hex_to_rgb(hex_a)
    rb, gb, bb = hex_to_rgb(hex_b)
    return rgb_to_hex(
        ra + (rb - ra) * ratio,
        ga + (gb - ga) * ratio,
        ba + (bb - ba) * ratio,
    )


def darken(hex_color: str, amount: float = 0.35) -> str:
    return mix(hex_color, "#000000", amount)


def lighten(hex_color: str, amount: float = 0.35) -> str:
    return mix(hex_color, "#FFFFFF", amount)


def readable_on(fg_candidate: str, bg_hex: str, fallback_dark="#101418", fallback_light="#FFFFFF") -> str:
    bg_lum = luminance(bg_hex)
    fg_lum = luminance(fg_candidate)
    contrast = abs(bg_lum - fg_lum)
    if contrast > 0.25:
        return fg_candidate
    return fallback_dark if bg_lum > 0.5 else fallback_light


# Colour extraction — CSS files, inline styles, <style> blocks, theme-color,
# ranked by how often each colour is actually used (dominant, not just "first")

HEX_RE = re.compile(r"#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")

BRAND_PROPERTY_RE = re.compile(
    r"(?:background(?:-color)?|border(?:-color)?|fill|--(?:brand|primary|accent|theme)[a-z\-]*)\s*:\s*"
    r"#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})",
    re.IGNORECASE,
)


def _norm_hex(c: str) -> str:
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return "#" + c.upper()


def extract_colors_from_css_text(css_text: str) -> Counter:
    counts = Counter()
    for m in HEX_RE.finditer(css_text):
        c = _norm_hex(m.group(1))
        if not is_greyish(c):
            counts[c] += 1
    for m in BRAND_PROPERTY_RE.finditer(css_text):
        c = _norm_hex(m.group(1))
        if not is_greyish(c):
            counts[c] += 4  # weight declarations that are likely brand colours
    return counts


def gather_page_colors(soup: BeautifulSoup, base_url: str) -> list:
    """Collect colours from inline styles, <style> blocks, meta theme-color and
    up to 3 linked stylesheets, then rank by weighted frequency."""
    counts = Counter()

    theme_meta = soup.find("meta", attrs={"name": "theme-color"})
    if theme_meta and theme_meta.get("content", "").startswith("#"):
        c = theme_meta["content"].strip()
        if re.fullmatch(r"#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})", c):
            counts[_norm_hex(c.lstrip("#"))] += 10  # strong brand signal

    for tag in soup.find_all(style=True):
        counts.update(extract_colors_from_css_text(tag["style"]))

    for style in soup.find_all("style"):
        counts.update(extract_colors_from_css_text(style.get_text()))

    css_links = []
    for link in soup.find_all("link", rel=lambda v: v and "stylesheet" in v):
        href = link.get("href")
        if href:
            css_links.append(urljoin(base_url, href))

    for href in css_links[:3]:
        try:
            r = requests.get(href, timeout=6, headers=HEADERS)
            if r.status_code == 200:
                counts.update(extract_colors_from_css_text(r.text[:200000]))
        except Exception:
            continue

    return [c for c, _ in counts.most_common(12)]


def dominant_colors_from_image(image_bytes: bytes, n: int = 3) -> list:
    """Sample the most common non-grey colours out of an image (e.g. the logo itself)."""
    if not Image:
        return []
    try:
        img = Image.open(_io.BytesIO(image_bytes)).convert("RGBA")
        img.thumbnail((80, 80))
        counts = Counter()
        for px in img.getdata():
            r, g, b, a = px
            if a < 128:
                continue
            hexc = rgb_to_hex(r, g, b)
            if not is_greyish(hexc):
                counts[hexc] += 1
        return [c for c, _ in counts.most_common(n)]
    except Exception:
        return []


# Logo extraction — prioritised chain of signals

LOGO_HINTS = ("logo", "brand", "site-icon", "wordmark")
NEGATIVE_HINTS = ("sprite", "icon-arrow", "avatar", "flag", "payment", "social")


def _candidate_score(img_tag, src: str) -> int:
    alt = (img_tag.get("alt") or "").lower()
    cls = " ".join(img_tag.get("class", [])).lower()
    idv = (img_tag.get("id") or "").lower()
    blob = f"{alt} {cls} {idv} {src.lower()}"
    score = 0
    if any(bad in blob for bad in NEGATIVE_HINTS):
        score -= 10
    if any(hint in blob for hint in LOGO_HINTS):
        score += 5
    if src.lower().endswith(".svg"):
        score += 2
    parent_names = [p.name for p in img_tag.parents if p.name]
    if "header" in parent_names or "nav" in parent_names:
        score += 4
    return score


def find_logo_url(soup: BeautifulSoup, base_url: str) -> str:
    # 1) any <img> with logo-ish attributes or sitting in header/nav (highest confidence)
    candidates = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src or src.startswith("data:"):
            continue
        score = _candidate_score(img, src)
        if score > 0:
            candidates.append((score, src))
    if candidates:
        candidates.sort(key=lambda t: t[0], reverse=True)
        return urljoin(base_url, candidates[0][1])

    # 2) any <img> at all in the header/nav
    header = soup.find("header") or soup.find(attrs={"class": re.compile("header|navbar|nav-", re.I)})
    if header:
        img = header.find("img")
        if img and img.get("src"):
            return urljoin(base_url, img["src"])

    # 3) apple-touch-icon (usually a decent square brand mark)
    for rel in ("apple-touch-icon", "apple-touch-icon-precomposed"):
        link = soup.find("link", rel=lambda v: v and rel in v)
        if link and link.get("href"):
            return urljoin(base_url, link["href"])

    # 4) largest declared <link rel="icon">
    icon_links = soup.find_all("link", rel=lambda v: v and "icon" in v)
    best_href, best_size = "", -1
    for link in icon_links:
        href = link.get("href")
        if not href:
            continue
        sizes = link.get("sizes", "")
        m = re.search(r"(\d+)x\d+", sizes)
        size = int(m.group(1)) if m else 32
        if size > best_size:
            best_size, best_href = size, href
    if best_href:
        return urljoin(base_url, best_href)

    # 5) plain /favicon.ico as an absolute last resort
    return urljoin(base_url, "/favicon.ico")


def find_banner_url(soup: BeautifulSoup, base_url: str) -> str:
    """A wide hero/social image suitable for use as a background strip on the pass."""
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return urljoin(base_url, og_image["content"])
    twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
    if twitter_image and twitter_image.get("content"):
        return urljoin(base_url, twitter_image["content"])
    return ""


def fetch_image_as_base64(img_url: str):
    if not img_url:
        return None, None
    try:
        r = requests.get(img_url, timeout=6, headers=HEADERS)
        if r.status_code == 200 and "image" in r.headers.get("Content-Type", ""):
            content_type = r.headers["Content-Type"].split(";")[0].strip()
            data_uri = "data:" + content_type + ";base64," + base64.b64encode(r.content).decode()
            return data_uri, r.content
    except Exception:
        pass
    return None, None


# Standard sizes so every card renders logos/images the same way regardless
# of the wildly different dimensions real websites use.
LOGO_STANDARD_PX = 320
BANNER_STANDARD_SIZE = (680, 200)  # matches the 3.4:1 CSS aspect-ratio on the card


def standardize_image(image_bytes: bytes, size, fit: str = "contain"):
    """Resize/crop raw image bytes to a fixed size and return a PNG data URI.
    fit='contain' letterboxes on transparent background (logos).
    fit='cover' crops to fill exactly (banners)."""
    if not Image or not image_bytes:
        return None
    try:
        img = Image.open(_io.BytesIO(image_bytes)).convert("RGBA")
        target_w, target_h = size if isinstance(size, tuple) else (size, size)

        if fit == "cover":
            src_ratio = img.width / img.height
            dst_ratio = target_w / target_h
            if src_ratio > dst_ratio:
                new_w = int(img.height * dst_ratio)
                x0 = (img.width - new_w) // 2
                img = img.crop((x0, 0, x0 + new_w, img.height))
            else:
                new_h = int(img.width / dst_ratio)
                y0 = (img.height - new_h) // 2
                img = img.crop((0, y0, img.width, y0 + new_h))
            img = img.resize((target_w, target_h), Image.LANCZOS)
        else:
            canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            img.thumbnail((target_w, target_h), Image.LANCZOS)
            offset = ((target_w - img.width) // 2, (target_h - img.height) // 2)
            canvas.paste(img, offset, img)
            img = canvas

        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


# Design variants — three genuinely different LAYOUTS, not just recolours

def build_design_variants(primary_color: str, secondary_color: str) -> list:
    """
    Produce 3 distinct, ready-to-use layout treatments from the SAME scraped
    brand colours, so the user can pick the look they prefer without
    re-scraping the site. Each has its own `layout` so the preview actually
    renders a different card structure, not just a different colour.
    """
    brand_fg = best_foreground(primary_color)

    variants = [
        {
            "id": "corner-classic",
            "name": "Classic Corner",
            "description": "Logo badge in the top corner with clean stacked details below — the familiar membership-card layout.",
            "primary_color": primary_color,
            "secondary_color": secondary_color,
            "foreground_color": brand_fg,
            "style": "gradient",
            "layout": "corner-classic",
        },
        {
            "id": "image-strip",
            "name": "Image Strip",
            "description": "Full-width brand image band beneath the barcode, logo small and centred up top.",
            "primary_color": "#FFFFFF",
            "secondary_color": "#EEF1F5",
            "foreground_color": readable_on(primary_color, "#FFFFFF", fallback_dark=darken(primary_color, 0.15)),
            "accent_color": primary_color,
            "style": "flat-light",
            "layout": "image-strip",
        },
        {
            "id": "side-band",
            "name": "Side Band",
            "description": "Bold vertical colour band down the side with the logo centred in it — a premium, distinct silhouette.",
            "primary_color": darken(primary_color, 0.45),
            "secondary_color": secondary_color if secondary_color else darken(primary_color, 0.7),
            "foreground_color": readable_on(lighten(primary_color, 0.35), darken(primary_color, 0.45),
                                             fallback_light=lighten(primary_color, 0.55)),
            "style": "flat-dark",
            "layout": "side-band",
        },
    ]
    return variants


# Scraping

def scrape_website(url: str) -> dict:
    """Scrape a website and return structured brand data + 3 design variants."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        resp = requests.get(url, timeout=10, headers=HEADERS)
        resp.raise_for_status()
    except Exception as exc:
        return {"error": f"Could not reach {url}: {exc}"}

    soup = BeautifulSoup(resp.text, "html.parser")
    base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

    # ---- Brand name ---------------------------------------------------
    brand_name = ""
    og_site = soup.find("meta", property="og:site_name")
    if og_site and og_site.get("content"):
        brand_name = og_site["content"].strip()
    if not brand_name:
        title_tag = soup.find("title")
        if title_tag:
            brand_name = title_tag.get_text().split("|")[0].split("\u2013").pop(0).split("-")[0].strip()
    if not brand_name:
        brand_name = urlparse(url).netloc.replace("www.", "").split(".")[0].title()

    # ---- Description ----------------------------------------------------
    description = ""
    og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
    if og_desc and og_desc.get("content"):
        description = og_desc["content"].strip()[:120]

    # ---- Logo: header/nav img > apple-touch-icon > favicon (real chain of signals) --
    logo_url = find_logo_url(soup, base_url)
    logo_base64, logo_bytes = fetch_image_as_base64(logo_url) if logo_url else (None, None)
    if logo_bytes:
        standardized = standardize_image(logo_bytes, LOGO_STANDARD_PX, fit="contain")
        if standardized:
            logo_base64 = standardized

    # ---- Banner / hero image (separate from logo — used by the Image Strip layout) --
    banner_url = find_banner_url(soup, base_url)
    banner_base64, banner_bytes = fetch_image_as_base64(banner_url) if banner_url and banner_url != logo_url else (None, None)
    if banner_bytes:
        standardized = standardize_image(banner_bytes, BANNER_STANDARD_SIZE, fit="cover")
        if standardized:
            banner_base64 = standardized

    # ---- Colours: CSS/theme-color first, fall back to sampling the logo itself --
    colors = gather_page_colors(soup, base_url)
    if len(colors) < 2 and logo_bytes:
        colors = list(dict.fromkeys(colors + dominant_colors_from_image(logo_bytes, 4)))

    primary_color = colors[0] if colors else "#1A6B8A"
    secondary_color = colors[1] if len(colors) > 1 else darken(primary_color, 0.3)

    # ---- Contact / social ---------------------------------------------------
    phone = ""
    email = ""
    phone_re = re.compile(r"(\+?\d[\d\s\-\(\)]{7,}\d)")
    email_re = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    text_blob = soup.get_text(" ")
    phone_match = phone_re.search(text_blob)
    if phone_match:
        phone = phone_match.group(0).strip()[:20]
    email_match = email_re.search(text_blob)
    if email_match:
        email = email_match.group(0)

    # ---- Guess pass type ------------------------------------------------------
    text_lower = text_blob.lower()
    pass_type = "Membership Card"
    pass_type_hints = {
        "gym|fitness|sport|workout": "Membership Card",
        "charit|donat|support|volunte": "Supporter Card",
        "theatre|museum|gallery|visitor|attraction": "Annual Pass",
        "event|concert|festival|ticket": "Event Pass",
        "member|club|associat|society": "Member ID Card",
        "hotel|resort|hostel|stay": "Guest Pass",
        "library|borrow|lending": "Library Card",
        "student|university|college|school": "Student ID",
    }
    for pattern, pt in pass_type_hints.items():
        if any(kw in text_lower for kw in pattern.split("|")):
            pass_type = pt
            break

    design_variants = build_design_variants(primary_color, secondary_color)
    for v in design_variants:
        v["banner_base64"] = banner_base64 if v["layout"] == "image-strip" else None

    return {
        "brand_name": brand_name,
        "description": description,
        "logo_url": logo_url,
        "logo_base64": logo_base64,
        "banner_url": banner_url,
        "banner_base64": banner_base64,
        "primary_color": primary_color,
        "secondary_color": secondary_color,
        "foreground_color": best_foreground(primary_color),
        "colors_found": colors,
        "phone": phone,
        "email": email,
        "pass_type": pass_type,
        "website_url": url,
        "design_variants": design_variants,
    }
