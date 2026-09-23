"""Ask Paystack about every unfinished checkout from the last day and apply the result. Run every few minutes."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from payments import paystack
from payments.models import Payment
from payments.views import settle


class Command(BaseCommand):
    help = "Reconcile unfinished Paystack payments"

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timezone.timedelta(hours=24)
        qs = Payment.objects.exclude(state__in=[Payment.State.COMPLETE, Payment.State.FAILED]) \
                            .filter(source=Payment.Source.PAYSTACK, created_at__gte=cutoff).select_related("vendor")
        n = 0
        for p in qs:
            before = p.state
            settle(p, paystack.verify(p.api_ref))
            p.refresh_from_db()
            if p.state != before:
                n += 1
                self.stdout.write(f"{p.api_ref}: {p.state}")
        self.stdout.write(f"checked {qs.count()}, changed {n}")
