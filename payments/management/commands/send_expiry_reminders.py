"""Email vendors 7 days before, 1 day before, and on the day their Premium or POS subscription lapses.
Run daily (systemd timer). Safe to re-run: each reminder is logged and never repeated."""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from payments.models import Payment, ReminderLog
from vendors.models import SiteSettings, Vendor


class Command(BaseCommand):
    help = "Send subscription expiry reminders"

    def handle(self, *args, **opts):
        site = SiteSettings.get()
        today = timezone.localdate()
        sent = 0
        for v in Vendor.objects.filter(is_published=True).select_related("owner").prefetch_related("branches"):
            # Premium is one subscription for the business; POS is one per branch.
            rounds = [(Payment.Product.PREMIUM, v.premium_expires_at if v.plan == v.Plan.PREMIUM else None, site.premium_fee, None)]
            rounds += [(Payment.Product.POS, b.pos_expires_at, site.pos_fee, b) for b in v.branches.filter(is_active=True)]
            for product, expires, fee, branch in rounds:
                if not expires:
                    continue
                days = (timezone.localtime(expires).date() - today).days
                kind = {7: "7d", 1: "1d", 0: "expired"}.get(days) or ("expired" if days == -1 else None)
                if not kind or ReminderLog.objects.filter(vendor=v, branch=branch, product=product, kind=kind, expires_at=expires).exists():
                    continue
                label = "POS module" if product == Payment.Product.POS else "Premium listing"
                if branch is not None and v.branches_enabled:
                    label = f"POS module at {branch.name}"
                ctx = {"vendor": v, "branch": branch, "label": label, "days": days, "kind": kind, "expires": expires, "fee": fee,
                       "site": site, "site_url": settings.SITE_URL,
                       "renew_url": (f"{settings.SITE_URL}/pos/branches/" if (branch is not None and v.branches_enabled)
                                     else (f"{settings.SITE_URL}/pos/" if product == Payment.Product.POS else f"{settings.SITE_URL}/dashboard/upgrade/"))}
                subject = {"7d": f"Your {label} on BeautyFlow ends in 7 days",
                           "1d": f"Reminder: your {label} ends tomorrow",
                           "expired": f"Your {label} on BeautyFlow has expired"}[kind]
                try:
                    send_mail(subject, render_to_string("payments/reminder.txt", ctx), settings.DEFAULT_FROM_EMAIL, [v.owner.email],
                              html_message=render_to_string("payments/reminder.html", ctx), fail_silently=False)
                    ReminderLog.objects.create(vendor=v, branch=branch, product=product, kind=kind, expires_at=expires)
                    sent += 1
                    self.stdout.write(f"{v.brand_name}: {label} {kind}")
                except Exception as e:  # keep going for other vendors
                    self.stderr.write(f"{v.brand_name}: failed ({e})")
        self.stdout.write(f"sent {sent}")
