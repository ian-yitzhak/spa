"""Branded A4 menu PDF: logo, business info, opening hours, a few photos, menu grouped by type, QR to the online menu.
Free plan gets a diagonal BEAUTYFLOW watermark on every page; Premium is clean."""
import io
import os

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

RED, DARK, GREY, LIGHT = colors.HexColor("#B0426C"), colors.HexColor("#221A1F"), colors.HexColor("#6b7280"), colors.HexColor("#f3f4f6")
W, H = A4
M = 16 * mm


def profile_gaps(vendor):
    """What's missing before a menu PDF makes sense. Empty list = ready."""
    gaps = []
    if not vendor.logo:
        gaps.append("business logo")
    if not (vendor.phone or vendor.whatsapp):
        gaps.append("phone or WhatsApp number")
    if not (vendor.town or vendor.county):
        gaps.append("location (county & town)")
    if not vendor.hours.exclude(opens=None).exists():
        gaps.append("opening hours")
    if not vendor.items.filter(is_available=True).exists():
        gaps.append("at least one menu item")
    return gaps


def _img(path, box_w, box_h):
    """Return (ImageReader, w, h) fitted inside box, or None."""
    try:
        from reportlab.lib.utils import ImageReader
        from PIL import Image
        im = Image.open(path); im.thumbnail((int(box_w * 4), int(box_h * 4)))
        r = min(box_w / im.width, box_h / im.height); return ImageReader(im.convert("RGB")), im.width * r, im.height * r
    except Exception:
        return None


def _watermark(c):
    c.saveState(); c.setFont("Helvetica-Bold", 46); c.setFillColor(colors.Color(0.9, 0.22, 0.27, alpha=0.05))
    c.translate(W / 2, H / 2); c.rotate(35)
    for dy in (-300, -150, 0, 150, 300):
        c.drawCentredString(0, dy, "BEAUTYFLOW   ·   BEAUTYFLOW")
    c.restoreState()


def _footer(c, vendor, page, watermark, menu_url):
    c.setFillColor(LIGHT); c.rect(0, 0, W, 14 * mm, fill=1, stroke=0)
    c.setFillColor(RED); c.rect(0, 14 * mm, W, 1.2 * mm, fill=1, stroke=0)
    c.setFillColor(colors.black); c.setFont("Helvetica", 8)
    c.drawString(M, 5.5 * mm, "Powered by BeautyFlow · www.beautyflow.co.ke")
    c.drawRightString(W - M, 5.5 * mm, f"Page {page}")
    if watermark:
        _watermark(c)


def build_menu_pdf(vendor, menu_url, watermark=True):
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A4); c.setTitle(f"{vendor.brand_name} menu")
    page = 1
    # ── Cover band
    c.setFillColor(DARK); c.rect(0, H - 62 * mm, W, 62 * mm, fill=1, stroke=0)
    # subtle curves: two translucent circles in the header + an orange arc accent
    c.saveState(); clip = c.beginPath(); clip.rect(0, H - 62 * mm, W, 62 * mm); c.clipPath(clip, stroke=0)
    c.setFillColor(colors.Color(1, 1, 1, alpha=0.05)); c.circle(W - 40 * mm, H - 8 * mm, 46 * mm, fill=1, stroke=0)
    c.setFillColor(colors.Color(0.96, 0.64, 0.38, alpha=0.16)); c.circle(W * 0.45, H - 64 * mm, 26 * mm, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#E8B4C4")); c.setLineWidth(1.4); c.arc(-30 * mm, H - 80 * mm, 70 * mm, H - 52 * mm, 5, 70); c.restoreState()
    # white page below header starts with a rounded top edge
    c.setFillColor(colors.white); c.roundRect(-5 * mm, H - 66 * mm, W + 10 * mm, 8 * mm, 4 * mm, fill=1, stroke=0)
    x = M; y_top = H - 12 * mm
    logo = _img(vendor.logo.path, 34 * mm, 34 * mm) if vendor.logo and os.path.exists(vendor.logo.path) else None
    if logo:
        c.setFillColor(colors.white); c.roundRect(x - 2, y_top - 36 * mm, logo[1] + 4, logo[2] + 4, 3 * mm, fill=1, stroke=0)
        c.drawImage(logo[0], x, y_top - 36 * mm + 2, logo[1], logo[2], mask="auto"); x += logo[1] + 8 * mm
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 26); c.drawString(x, y_top - 10 * mm, vendor.brand_name[:34])
    c.setFillColor(colors.HexColor("#E8B4C4")); c.setFont("Helvetica", 12); c.drawString(x, y_top - 17 * mm, (vendor.tagline or vendor.type_label)[:70])
    c.setFillColor(colors.white); c.setFont("Helvetica", 9.5)
    line = y_top - 25 * mm
    contact = " · ".join(v for v in [f"Tel {vendor.phone}" if vendor.phone else "", f"WhatsApp {vendor.whatsapp}" if vendor.whatsapp and vendor.whatsapp != vendor.phone else "", ", ".join(v for v in [vendor.address, vendor.town, vendor.county] if v)] if v)
    c.drawString(x, line, contact[:110]); line -= 5 * mm
    if vendor.delivers:
        c.drawString(x, line, "Delivery available"); line -= 5 * mm
    # QR (top right)
    qr = qrcode.make(menu_url, box_size=6, border=1).convert("RGB"); from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(qr), W - M - 28 * mm, H - 44 * mm, 28 * mm, 28 * mm)
    c.setFont("Helvetica", 7); c.setFillColor(colors.white); c.drawCentredString(W - M - 14 * mm, H - 48 * mm, "Scan for menu & orders")
    # ── Menu
    y = H - 74 * mm
    c.setFillColor(RED); c.setFont("Helvetica-Bold", 16); c.drawString(M, y, "Menu")
    c.setStrokeColor(RED); c.setLineWidth(1.2); c.line(M, y - 2 * mm, M + 14 * mm, y - 2 * mm); y -= 9 * mm
    cats = list(vendor.categories.all()) + [None]
    blocks = []
    for cat in cats:
        items = list(vendor.items.filter(is_available=True, category=cat).order_by("name"))
        if items:
            blocks.append((cat.name if cat else "Other", items, 7 * mm + len(items) * 6.2 * mm + 3 * mm))
    gap = 8 * mm; col_w = (W - 2 * M - gap) / 2; bottom = 22 * mm
    # split blocks into two balanced columns by height
    total = sum(b[2] for b in blocks); left, right, acc = [], [], 0.0
    for b in blocks:
        (left if acc < total / 2 else right).append(b); acc += b[2] if acc < total / 2 else 0
    if blocks and not right and len(left) > 1:  # always use both columns when we can
        right = [left.pop()]
    y_start = y; y_cols = [y_start, y_start]; col_x = [M, M + col_w + gap]
    def new_page():
        nonlocal page, y_cols
        _footer(c, vendor, page, watermark, menu_url); c.showPage(); page += 1
        c.setFillColor(DARK); c.setFont("Helvetica-Bold", 12); c.drawString(M, H - M, f"{vendor.brand_name} — menu (continued)")
        y_cols = [H - M - 10 * mm, H - M - 10 * mm]
    def draw_block(col, name, items):
        nonlocal y_cols
        cx = col_x[col]; y = y_cols[col]
        if y - 7 * mm < bottom:
            new_page(); y = y_cols[col]
        c.setFillColor(DARK); c.setFont("Helvetica-Bold", 11.5); c.drawString(cx, y, name.upper()); y -= 6.5 * mm
        for it in items:
            if y < bottom:
                y_cols[col] = y; new_page(); y = y_cols[col]
            c.setFont("Helvetica", 9.5); c.setFillColor(DARK); nm = it.name[:38]; c.drawString(cx, y, nm)
            price = "On request" if it.price_on_request else f"{it.price:,.0f}"; c.setFont("Helvetica-Bold", 9.5); c.drawRightString(cx + col_w, y, price)
            nw = c.stringWidth(nm, "Helvetica", 9.5); pw = c.stringWidth(price, "Helvetica-Bold", 9.5)
            c.setStrokeColor(colors.HexColor("#d1d5db")); c.setDash(1, 2); c.line(cx + nw + 2 * mm, y + 1, cx + col_w - pw - 2 * mm, y + 1); c.setDash()
            y -= 6.2 * mm
        y_cols[col] = y - 3 * mm
    for name, items, _h in left:
        draw_block(0, name, items)
    for name, items, _h in right:
        draw_block(1, name, items)
    y = min(y_cols); col = 0
    # ── Opening hours + photos (after the menu), on a soft rounded panel
    y = y - 4 * mm
    hours = list(vendor.hours.order_by("day")) if vendor.hours.exclude(opens=None).exists() else []
    photos = [p for p in vendor.photos.all()[:3] if os.path.exists(p.image.path)]
    panel_h = 44 * mm
    if y - panel_h < 22 * mm:
        new_page(); y = H - M - 12 * mm
    c.setFillColor(LIGHT); c.roundRect(M, y - panel_h, W - 2 * M, panel_h, 4 * mm, fill=1, stroke=0)
    if hours:
        c.setFillColor(DARK); c.setFont("Helvetica-Bold", 10); c.drawString(M + 6 * mm, y - 8 * mm, "Opening hours"); yy = y - 14 * mm
        c.setFont("Helvetica", 8.5)
        for h in hours:
            txt = "Closed" if (h.closed or not h.opens) else ("Open 24 hours" if h.all_day else f"{h.opens:%H:%M} – {h.closes:%H:%M}")
            c.setFillColor(GREY); c.drawString(M + 6 * mm, yy, h.get_day_display()); c.setFillColor(DARK); c.drawString(M + 30 * mm, yy, txt); yy -= 4.1 * mm
    px = M + 70 * mm
    for p in photos:
        im = _img(p.image.path, 34 * mm, 30 * mm)
        if im:
            c.saveState(); pth = c.beginPath(); pth.roundRect(px, y - 38 * mm, 34 * mm, 30 * mm, 3 * mm); c.clipPath(pth, stroke=0)
            c.drawImage(im[0], px, y - 38 * mm, 34 * mm, 30 * mm, mask="auto"); c.restoreState(); px += 38 * mm
    _footer(c, vendor, page, watermark, menu_url); c.showPage(); c.save()
    return buf.getvalue()
