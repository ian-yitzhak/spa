"""Welcome email at sign-up and a nudge on day 7 for vendors who have not bought Premium or POS.
Run daily (systemd timer). Each email is logged once per vendor, so re-running is safe.
--to me@example.com sends a sample of both to that address without touching the logs."""
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from payments.models import Payment, ReminderLog
from vendors.models import SiteSettings, Vendor


def _ctx(vendor, kind, site):
    return {"kind": kind, "name": vendor.owner.first_name or "there", "brand": vendor.brand_name,
            "url": vendor.get_absolute_url(), "site_url": settings.SITE_URL,
            "support_whatsapp": site.support_whatsapp, "pos_fee": f"KES {site.pos_fee:,.0f}"}


SUBJECTS = {"welcome": "Welcome to BeautyFlow — your digital menu is ready",
            "day7": "Get more from BeautyFlow: QR menus, online orders and POS"}


def _send(vendor, kind, site):
    ctx = _ctx(vendor, kind, site)
    send_mail(SUBJECTS[kind], render_to_string("vendors/onboarding.txt", ctx), settings.DEFAULT_FROM_EMAIL,
              [vendor.owner.email], html_message=render_to_string("vendors/onboarding.html", ctx), fail_silently=False)


class Command(BaseCommand):
    help = "Send the welcome email and the day-7 nudge to vendors who have not upgraded"

    def add_arguments(self, parser):
        parser.add_argument("--to", help="Send a sample of both emails to this address and stop")

    def handle(self, *args, **opts):
        site = SiteSettings.get()
        if opts.get("to"):
            vendor = Vendor.objects.select_related("owner").order_by("-created_at").first()
            for kind in ("welcome", "day7"):
                ctx = _ctx(vendor, kind, site)
                send_mail(f"[sample] {SUBJECTS[kind]}", render_to_string("vendors/onboarding.txt", ctx),
                          settings.DEFAULT_FROM_EMAIL, [opts["to"]],
                          html_message=render_to_string("vendors/onboarding.html", ctx), fail_silently=False)
                self.stdout.write(f"sample '{kind}' sent to {opts['to']}")
            return

        now, sent = timezone.now(), 0
        for v in Vendor.objects.select_related("owner").filter(owner__email_verified=True):
            # welcome, as soon as the account is verified
            if not ReminderLog.objects.filter(vendor=v, product=Payment.Product.PREMIUM, kind="welcome").exists():
                try:
                    _send(v, "welcome", site)
                    ReminderLog.objects.create(vendor=v, product=Payment.Product.PREMIUM, kind="welcome", expires_at=now)
                    sent += 1
                except Exception as e:                      # a bad address must not stop the rest
                    self.stderr.write(f"{v.owner.email}: {e}")
                continue
            # day 7, only if they are still on the free plan
            if v.created_at > now - timedelta(days=7) or v.is_premium or v.pos_active:
                continue
            if ReminderLog.objects.filter(vendor=v, product=Payment.Product.PREMIUM, kind="day7").exists():
                continue
            try:
                _send(v, "day7", site)
                ReminderLog.objects.create(vendor=v, product=Payment.Product.PREMIUM, kind="day7", expires_at=now)
                sent += 1
            except Exception as e:
                self.stderr.write(f"{v.owner.email}: {e}")
        self.stdout.write(f"onboarding emails sent: {sent}")
