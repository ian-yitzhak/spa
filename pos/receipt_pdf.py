"""Thermal-style receipt PDF (80mm wide) with the vendor's logo."""
from io import BytesIO

from reportlab.lib.pagesizes import mm
from reportlab.lib.units import mm as MM
from reportlab.pdfgen import canvas


def build_receipt_pdf(order, public_url):
    v = order.vendor
    items = list(order.items.select_related("staff__user"))
    width = 80 * MM
    height = (105 + 10 * len(items) + (12 if (order.amount_tendered or order.change_due) else 0)) * MM
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    y = height - 8 * MM
    x0, x1 = 5 * MM, width - 5 * MM

    def line(text, size=9, bold=False, align="left", dy=5):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        if align == "center":
            c.drawCentredString(width / 2, y, text)
        elif align == "right":
            c.drawRightString(x1, y, text)
        else:
            c.drawString(x0, y, text)
        y -= dy * MM

    def row(left, right, bold=False, size=9):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x0, y, left[:34])
        c.drawRightString(x1, y, right)
        y -= 5 * MM

    def dashes():
        nonlocal y
        c.setDash(1, 2); c.line(x0, y + 2 * MM, x1, y + 2 * MM); c.setDash(); y -= 2 * MM

    if v.logo:
        try:
            c.drawImage(v.logo.path, width / 2 - 8 * MM, y - 12 * MM, 16 * MM, 16 * MM, preserveAspectRatio=True, mask="auto")
            y -= 15 * MM
        except Exception:
            pass
    line(v.brand_name, 12, True, "center", 6)
    addr = ", ".join(x for x in [v.address, v.town] if x)
    if addr:
        line(addr, 8, align="center", dy=4)
    if v.phone:
        line(f"Tel {v.phone}", 8, align="center", dy=5)
    dashes()
    row("Bill" if not order.paid_at else "Receipt", f"#{order.ref}", True)
    row("Date", (order.paid_at or order.placed_at or order.created_at).strftime("%d %b %Y %H:%M"))
    if order.reconciled_at:
        row("Corrected", order.reconciled_at.strftime("%d %b %H:%M"))
    if order.payment_method == "split":
        row("M-Pesa", f"{order.paid_mpesa:,.2f}")
        row("Cash", f"{order.paid_cash:,.2f}")
    if order.customer_name:
        row("Client", order.customer_name)
    dashes()
    for it in items:
        row(f"{it.qty} x {it.name}", f"{it.line_total:,.2f}")
        if it.staff_id:
            line(f"   by {it.staff.name}", 7, dy=4)
    dashes()
    if order.discount:
        row("Before discount", f"{order.gross:,.2f}")
        row("Discount", f"-{order.discount:,.2f}")
    row("Subtotal", f"{order.subtotal:,.2f}")
    row("VAT (16%)", f"{order.tax:,.2f}")
    row("Total", f"KES {order.total:,.2f}", True, 11)
    if order.is_paid:
        row("Paid via", f"{order.get_payment_method_display()}{' ' + order.payment_ref if order.payment_ref else ''}")
        if order.payer_name:
            row("Paid by", order.payer_name)
        if order.amount_tendered:
            row("Tendered", f"{order.amount_tendered:,.2f}")
            row("Change", f"{order.change_due:,.2f}")
        elif order.change_due:
            row("Received", f"{order.received:,.2f}")
            row("Change", f"{order.change_due:,.2f}", True)
    else:
        line("Not paid", 10, True, "center")
        line("Awaiting payment", 8, align="center", dy=4)
    dashes()
    line("Thank you! Karibu tena.", 8, align="center", dy=4)
    line("Powered by BeautyFlow · " + public_url.replace("https://", ""), 6, align="center", dy=4)
    c.showPage(); c.save()
    return buf.getvalue()
