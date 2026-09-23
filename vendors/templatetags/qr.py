import io

import qrcode
import qrcode.image.svg
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def qr_svg(data, size=120):
    """Inline SVG QR code for `data`."""
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode()
    svg = svg.replace("<svg", f'<svg style="width:{size}px;height:{size}px" role="img" aria-label="QR code"', 1)
    # strip xml declaration
    return mark_safe(svg[svg.index("<svg"):])
