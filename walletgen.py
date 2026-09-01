"""
Romax Digital – Wallet Pass Creator
walletgen.py – Builds a REAL Apple Wallet .pkpass bundle and a REAL
"Add to Google Wallet" save link (signed JWT) — not just raw JSON.

Apple Wallet
A .pkpass is a zip containing pass.json + icon/logo PNGs + manifest.json
(sha1 of every file) + a `signature` file: a detached CMS/PKCS#7 signature
of manifest.json, produced with the organisation's Apple Pass Type ID
certificate + the Apple WWDR intermediate certificate.
Without those certificates Apple's spec makes it *impossible* for anyone
(including us) to produce a pass that will actually install on a phone —
that identity check is the whole point of Wallet passes. So:
  * if the logged-in user has uploaded their own cert.pem / key.pem / wwdr.pem
    (Settings → Wallet Setup) we sign the pass for real and it is installable.
  * otherwise we still build the full, correct .pkpass file structure so the
    user can see/inspect exactly what will ship, clearly labelled "unsigned
    preview", with instructions on how to make it a real, installable pass.

Google Wallet
Google's "Generic Pass" flow lets you embed the full class + object payload
directly inside a JWT signed with a Google Cloud service-account private key
(RS256) — no separate API call needed. Clicking the resulting
https://pay.google.com/gp/v/save/<jwt> link both creates and adds the pass.
That requires the organisation's own Google Wallet service-account JSON key
+ Issuer ID (Settings → Wallet Setup). Without it we fall back to returning
the structured pass object for preview.
"""

import hashlib
import io
import json
import time
import zipfile
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
import base64 as b64

try:
    import jwt as pyjwt
except ImportError:  # pragma: no cover
    pyjwt = None

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography import x509


# Image generation (icon / logo) — always produced, even with no source logo

def _load_font(size):
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size
        )
    except Exception:
        return ImageFont.load_default()


def _initials(name: str) -> str:
    words = [w for w in (name or "").split() if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return (name or "RD")[:2].upper()


def _decode_data_uri(data_uri: str):
    try:
        header, encoded = data_uri.split(",", 1)
        raw = b64.b64decode(encoded)
        return Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:
        return None


def _square_logo_image(brand_name: str, logo_base64: str, bg_hex: str, fg_hex: str, px: int) -> Image.Image:
    bg = tuple(int(bg_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    canvas = Image.new("RGBA", (px, px), bg)

    source = _decode_data_uri(logo_base64) if logo_base64 else None
    if source:
        source.thumbnail((int(px * 0.78), int(px * 0.78)), Image.LANCZOS)
        offset = ((px - source.width) // 2, (px - source.height) // 2)
        canvas.paste(source, offset, source)
        return canvas

    # No source logo → draw brand initials
    draw = ImageDraw.Draw(canvas)
    txt = _initials(brand_name)
    font = _load_font(int(px * 0.42))
    fg = tuple(int(fg_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    try:
        bbox = draw.textbbox((0, 0), txt, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((px - w) / 2 - bbox[0], (px - h) / 2 - bbox[1]), txt, font=font, fill=fg)
    except Exception:
        draw.text((px * 0.2, px * 0.3), txt, font=font, fill=fg)
    return canvas


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_pass_images(brand_name: str, logo_base64: str, bg_hex: str, fg_hex: str) -> dict:
    """Returns a dict of filename -> PNG bytes matching Apple's required set."""
    sizes = {
        "icon.png": 29, "icon@2x.png": 58, "icon@3x.png": 87,
        "logo.png": 160, "logo@2x.png": 320,
    }
    files = {}
    for fname, px in sizes.items():
        img = _square_logo_image(brand_name, logo_base64, bg_hex, fg_hex, px)
        files[fname] = _png_bytes(img)
    return files


# Apple Wallet (.pkpass)

def _hex_to_rgb_str(hex_color: str) -> str:
    hex_color = (hex_color or "#1A6B8A").lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgb({r},{g},{b})"


def build_apple_pass_json(cfg: dict, serial: str, user=None) -> dict:
    team_id = (user.apple_team_id if user and user.apple_team_id else "ROMAX2026")
    pass_type_id = (user.apple_pass_type_id if user and user.apple_pass_type_id
                    else "pass.co.uk.romax.digital.membership")

    custom_fields = cfg.get("custom_fields") or []
    secondary_fields = [
        {"key": f"field{i}", "label": (f.get("label") or "").upper()[:20], "value": f.get("value", "")}
        for i, f in enumerate(custom_fields[:4])
    ] or [
        {"key": "tier", "label": "TIER", "value": cfg.get("tier", "Standard")},
    ]
    if cfg.get("expiry") and cfg.get("expiry") != "No expiry":
        secondary_fields.append({"key": "expires", "label": "VALID UNTIL", "value": cfg.get("expiry", "")})

    barcode_format = {
        "QR": "PKBarcodeFormatQR",
        "BARCODE": "PKBarcodeFormatCode128",
    }.get(cfg.get("barcode_type", "QR"), "PKBarcodeFormatQR")

    apple_pass = {
        "formatVersion": 1,
        "passTypeIdentifier": pass_type_id,
        "serialNumber": serial,
        "teamIdentifier": team_id,
        "organizationName": cfg.get("brand_name", "Organisation"),
        "description": cfg.get("pass_type", "Membership Card"),
        "logoText": cfg.get("brand_name", ""),
        "foregroundColor": _hex_to_rgb_str(cfg.get("foreground_color", "#FFFFFF")),
        "backgroundColor": _hex_to_rgb_str(cfg.get("primary_color", "#1A6B8A")),
        "labelColor": _hex_to_rgb_str(cfg.get("foreground_color", "#FFFFFF")),
        "webServiceURL": None,
        "barcodes": [{
            "message": cfg.get("qr_value", serial),
            "format": barcode_format,
            "messageEncoding": "iso-8859-1",
            "altText": cfg.get("qr_value", serial),
        }],
        "generic": {
            "primaryFields": [
                {"key": "member", "label": "MEMBER", "value": cfg.get("member_name", "Your Name")}
            ],
            "secondaryFields": secondary_fields,
            "auxiliaryFields": [
                {"key": "id", "label": "ID", "value": serial},
            ],
            "backFields": [
                {"key": "website", "label": "WEBSITE", "value": cfg.get("website_url", "")},
                {"key": "phone", "label": "PHONE", "value": cfg.get("phone", "")},
                {"key": "email", "label": "EMAIL", "value": cfg.get("email", "")},
                {"key": "terms", "label": "TERMS", "value": "This card remains the property of the issuer."},
            ],
        },
    }
    # legacy single-barcode key for older iOS versions
    apple_pass["barcode"] = apple_pass["barcodes"][0]
    return apple_pass


def _apple_certs_available(user) -> bool:
    return bool(user and getattr(user, "apple_certs_uploaded", False))


def _sign_manifest(manifest_bytes: bytes, cert_dir: str, key_password: str) -> bytes:
    """Detached DER PKCS#7/CMS signature of manifest.json, as required by Apple."""
    import os
    with open(os.path.join(cert_dir, "cert.pem"), "rb") as f:
        signer_cert = x509.load_pem_x509_certificate(f.read())
    with open(os.path.join(cert_dir, "key.pem"), "rb") as f:
        key_bytes = f.read()
        private_key = serialization.load_pem_private_key(
            key_bytes, password=(key_password.encode() if key_password else None)
        )
    with open(os.path.join(cert_dir, "wwdr.pem"), "rb") as f:
        wwdr_cert = x509.load_pem_x509_certificate(f.read())

    signature = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(manifest_bytes)
        .add_signer(signer_cert, private_key, hashes.SHA256())
        .add_certificate(wwdr_cert)
        .sign(
            serialization.Encoding.DER,
            [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary],
        )
    )
    return signature


def build_pkpass(cfg: dict, serial: str, user=None, cert_dir: str = None):
    """
    Returns (zip_bytes, signed: bool, error: str|None)
    """
    apple_pass = build_apple_pass_json(cfg, serial, user)

    images = generate_pass_images(
        cfg.get("brand_name", "Organisation"),
        cfg.get("logo_base64"),
        cfg.get("primary_color", "#1A6B8A"),
        cfg.get("foreground_color", "#FFFFFF"),
    )

    files = dict(images)
    files["pass.json"] = json.dumps(apple_pass, indent=2).encode()

    manifest = {name: hashlib.sha1(content).hexdigest() for name, content in files.items()}
    manifest_bytes = json.dumps(manifest).encode()
    files["manifest.json"] = manifest_bytes

    signed = False
    sign_error = None
    if _apple_certs_available(user) and cert_dir:
        try:
            files["signature"] = _sign_manifest(manifest_bytes, cert_dir, user.apple_key_password or "")
            signed = True
        except Exception as exc:
            sign_error = str(exc)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    zip_buffer.seek(0)
    return zip_buffer.getvalue(), signed, sign_error


# Google Wallet (signed "Add to Google Wallet" save link)

def build_google_pass_objects(cfg: dict, serial: str, user) -> tuple:
    issuer_id = user.google_issuer_id
    class_suffix = user.google_class_suffix or "romax_generic_class"
    class_id = f"{issuer_id}.{class_suffix}"
    object_id = f"{issuer_id}.romax_{serial}"

    text_modules = [
        {"header": "TIER", "body": cfg.get("tier", "Standard"), "id": "tier"},
        {"header": "MEMBER ID", "body": serial, "id": "member_id"},
    ]
    if cfg.get("expiry") and cfg.get("expiry") != "No expiry":
        text_modules.append({"header": "VALID UNTIL", "body": cfg.get("expiry", ""), "id": "expiry"})
    for i, f in enumerate((cfg.get("custom_fields") or [])[:4]):
        text_modules.append({"header": (f.get("label") or "").upper(), "body": f.get("value", ""), "id": f"custom{i}"})

    generic_class = {
        "id": class_id,
        "classTemplateInfo": {
            "cardTemplateOverride": {
                "cardRowTemplateInfos": [{
                    "twoItems": {
                        "startItem": {"firstValue": {"fields": [{"fieldPath": "object.textModulesData['tier']"}]}},
                        "endItem": {"firstValue": {"fields": [{"fieldPath": "object.textModulesData['member_id']"}]}},
                    }
                }]
            }
        },
    }

    generic_object = {
        "id": object_id,
        "classId": class_id,
        "genericType": "GENERIC_TYPE_UNSPECIFIED",
        "hexBackgroundColor": cfg.get("primary_color", "#1A6B8A"),
        "logo": {"sourceUri": {"uri": cfg.get("logo_url") or "https://romax.co.uk/favicon.ico"}},
        "cardTitle": {"defaultValue": {"language": "en-GB", "value": cfg.get("brand_name", "Organisation")}},
        "subheader": {"defaultValue": {"language": "en-GB", "value": cfg.get("pass_type", "Membership Card")}},
        "header": {"defaultValue": {"language": "en-GB", "value": cfg.get("member_name", "Your Name")}},
        "barcode": {"type": "QR_CODE", "value": cfg.get("qr_value", serial)},
        "textModulesData": text_modules,
        "linksModuleData": {
            "uris": [{"uri": cfg.get("website_url", ""), "description": "Visit Website", "id": "website"}]
        } if cfg.get("website_url") else None,
        "state": "ACTIVE",
    }
    if not generic_object["linksModuleData"]:
        del generic_object["linksModuleData"]

    return generic_class, generic_object


def build_google_wallet_save_url(cfg: dict, serial: str, user, cert_dir: str):
    """
    Returns dict:
      {"configured": True, "save_url": "...", "object_id": "..."}
    or
      {"configured": False, "reason": "..."}
    """
    import os

    if pyjwt is None:
        return {"configured": False, "reason": "PyJWT not installed on server."}

    if not (user and user.google_creds_uploaded and user.google_issuer_id):
        return {"configured": False, "reason": "Google Wallet credentials not configured for this account."}

    key_path = os.path.join(cert_dir, "service_account.json")
    if not os.path.exists(key_path):
        return {"configured": False, "reason": "Service account key file missing."}

    with open(key_path, "r") as f:
        service_account = json.load(f)

    private_key = service_account.get("private_key")
    client_email = service_account.get("client_email")
    if not private_key or not client_email:
        return {"configured": False, "reason": "Service account JSON is missing private_key/client_email."}

    generic_class, generic_object = build_google_pass_objects(cfg, serial, user)

    claims = {
        "iss": client_email,
        "aud": "google",
        "typ": "savetowallet",
        "iat": int(time.time()),
        "origins": [],
        "payload": {
            "genericClasses": [generic_class],
            "genericObjects": [generic_object],
        },
    }

    token = pyjwt.encode(claims, private_key, algorithm="RS256")
    if isinstance(token, bytes):
        token = token.decode()

    return {
        "configured": True,
        "save_url": f"https://pay.google.com/gp/v/save/{token}",
        "object_id": generic_object["id"],
        "class_id": generic_class["id"],
    }
