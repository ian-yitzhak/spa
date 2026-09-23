import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from vendors.models import SiteSettings

log = logging.getLogger(__name__)


def send_receipt(payment):
    """Email a payment receipt to the vendor owner. Never raises."""
    v = payment.vendor
    to = [v.owner.email]
    if v.email and v.email != v.owner.email:
        to.append(v.email)
    ctx = {"p": payment, "vendor": v, "site": SiteSettings.get(), "site_url": settings.SITE_URL}
    subject = f"Receipt: KES {payment.amount:.0f} {payment.get_product_display()} payment — BeautyFlow"
    try:
        send_mail(subject, render_to_string("payments/receipt.txt", ctx), settings.DEFAULT_FROM_EMAIL, to,
                  html_message=render_to_string("payments/receipt.html", ctx), fail_silently=False)
    except Exception:
        log.exception("Receipt email failed for payment %s", payment.pk)
