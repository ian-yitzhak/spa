"""Marketing kit (poster / social images)."""
import io
import os

import qrcode
from django import forms
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from PIL import Image, ImageDraw, ImageFont

from .forms import INPUT
from .models import Customer, Vendor
from .security import protect
from .views import vendor_required

FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
RED, DARK, ORANGE, WHITE = (230, 57, 70), (29, 29, 31), (244, 162, 97), (255, 255, 255)


def _font(size, bold=True):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT_R, size)
    except Exception:
        return ImageFont.load_default()


def _qr(url, size):
    img = qrcode.make(url, box_size=10, border=1).convert("RGB")
    return img.resize((size, size), Image.NEAREST)


def _logo(vendor, size):
    if vendor.logo and os.path.exists(vendor.logo.path):
        try:
            im = Image.open(vendor.logo.path).convert("RGBA"); im.thumbnail((size, size)); return im
        except Exception:
            return None
    return None


def _png(img):
    buf = io.BytesIO(); img.save(buf, "PNG", optimize=True); return buf.getvalue()


def _center(d, y, text, font, fill, W):
    w = d.textlength(text, font=font); d.text(((W - w) / 2, y), text, font=font, fill=fill)


def _fit(d, text, max_w, size, bold=True, min_size=24):
    """Largest font at or below `size` that keeps `text` within `max_w` pixels — long names must never run off or overlap."""
    while size > min_size and d.textlength(text, font=_font(size, bold)) > max_w:
        size -= 4
    return _font(size, bold)


def _put(d, xy, text, max_w, size, fill, bold=True, min_size=24):
    """Draw text shrunk to fit `max_w`; if it still doesn't fit at `min_size`, cut it with an ellipsis."""
    font = _fit(d, text, max_w, size, bold, min_size)
    while len(text) > 4 and d.textlength(text, font=font) > max_w:
        text = text[:-2].rstrip() + "…"
    d.text(xy, text, font=font, fill=fill)
    return font


def _menu_url(request, vendor, table=None):
    u = request.build_absolute_uri(vendor.get_menu_url())
    return f"{u}?table={table}" if table else u



# ── Marketing kit ──────────────────────────────────────────────────────

@vendor_required
def kit(request):
    return render(request, "dashboard/kit.html", {"vendor": request.vendor})


@vendor_required
def kit_image(request, kind):
    v = request.vendor
    url = _menu_url(request, v)
    tag = (v.tagline or f"{v.type_label} in {v.town or v.county or 'Kenya'}")[:90]
    if kind == "poster":  # A4 portrait 300dpi
        W, H = 2480, 3508; img = Image.new("RGB", (W, H), WHITE); d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 520], fill=DARK); logo = _logo(v, 320)
        if logo: img.paste(logo, (120, 100), logo)
        x = 520 if logo else 120; name_font = _fit(d, v.brand_name, W - x - 120, 150); tag_font = _fit(d, tag, W - x - 120, 64, False)
        block = int(name_font.size * 1.15) + 16 + int(tag_font.size * 1.15); y0 = (520 - block) // 2  # name + tagline centred in the band
        _put(d, (x, y0), v.brand_name, W - x - 120, 150, WHITE)
        _put(d, (x, y0 + int(name_font.size * 1.15) + 16), tag, W - x - 120, 64, ORANGE, False)
        _center(d, 700, "OUR PRICES", _font(140), RED, W); _center(d, 880, "Scan to see services, prices & photos", _font(72, False), DARK, W)
        q = _qr(url, 1500); img.paste(q, ((W - 1500) // 2, 1020)); _center(d, 2600, "Book your next appointment online", _font(72, False), (80, 80, 80), W)
        if v.phone: _center(d, 2720, f"Call / WhatsApp {v.phone}", _font(72), DARK, W)
        d.rectangle([0, H - 220, W, H], fill=RED); _center(d, H - 160, "Powered by BeautyFlow · beautyflow.co.ke", _font(72), WHITE, W)
    elif kind == "story":  # WhatsApp status / IG story 1080x1920
        W, H = 1080, 1920; img = Image.new("RGB", (W, H), DARK); d = ImageDraw.Draw(img)
        if v.cover and os.path.exists(v.cover.path):
            try:
                cv = Image.open(v.cover.path).convert("RGB"); r = max(W / cv.width, 900 / cv.height); cv = cv.resize((int(cv.width * r) + 1, int(cv.height * r) + 1)); x = (cv.width - W) // 2; img.paste(cv.crop((x, 0, x + W, 900)), (0, 0))
                band = Image.new("RGBA", (W, 300), (29, 29, 31, 200)); img.paste(band, (0, 600), band)
            except Exception: pass
        logo = _logo(v, 180)
        if logo: img.paste(logo, (60, 660), logo)
        x = 270 if logo else 60
        _put(d, (x, 690), v.brand_name, W - x - 60, 84, WHITE); _put(d, (x, 800), tag, W - x - 60, 44, ORANGE, False)
        _center(d, 980, "See our services & prices", _font(60), WHITE, W); q = _qr(url, 620); img.paste(q, ((W - 620) // 2, 1080))
        _center(d, 1740, "Scan or tap the link · book online", _font(40, False), (200, 200, 200), W); _center(d, 1820, "beautyflow.co.ke", _font(40), ORANGE, W)
    elif kind == "square":  # square social post 1080x1080
        W, H = 1080, 1080; img = Image.new("RGB", (W, H), WHITE); d = ImageDraw.Draw(img)
        if v.cover and os.path.exists(v.cover.path):
            try:
                cv = Image.open(v.cover.path).convert("RGB"); r = max(W / cv.width, 560 / cv.height); cv = cv.resize((int(cv.width * r) + 1, int(cv.height * r) + 1)); x = (cv.width - W) // 2; img.paste(cv.crop((x, 0, x + W, 560)), (0, 0))
            except Exception: pass
        logo = _logo(v, 140)
        if logo: img.paste(logo, (60, 590), logo)
        x = 230 if logo else 60
        _put(d, (x, 600), v.brand_name, W - x - 60, 66, DARK); _put(d, (x, 690), tag, W - x - 60, 36, (90, 90, 90), False)
        q = _qr(url, 240); img.paste(q, (60, 770))  # own row: text sits to its right, never under it
        _put(d, (340, 800), "Services, prices & online booking", W - 340 - 60, 44, RED); _put(d, (340, 870), "Scan the code or find us on beautyflow.co.ke", W - 340 - 60, 32, (90, 90, 90), False)
        d.rectangle([0, H - 50, W, H], fill=RED)
    else:
        from django.http import Http404
        raise Http404
    resp = HttpResponse(_png(img), content_type="image/png"); resp["Content-Disposition"] = f'attachment; filename="{v.slug}-{kind}.png"'; return resp
