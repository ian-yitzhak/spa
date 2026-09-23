import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from vendors.models import Vendor


class Payment(models.Model):
    """One Paystack checkout (card or M-Pesa) for a subscription period, or an admin-recorded payment."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class State(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETE = "COMPLETE", "Complete"
        FAILED = "FAILED", "Failed"

    class Product(models.TextChoices):
        PREMIUM = "premium", "Premium listing"
        POS = "pos", "POS module"

    class Source(models.TextChoices):
        PAYSTACK = "paystack", "Paystack"
        MANUAL = "manual", "Manual (admin)"

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="payments")
    branch = models.ForeignKey("pos.Branch", on_delete=models.SET_NULL, null=True, blank=True, related_name="payments",
                               help_text="For POS payments: the branch this month was bought for")
    product = models.CharField(max_length=10, choices=Product.choices, default=Product.PREMIUM)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.PAYSTACK)
    note = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="recorded_payments")
    months = models.PositiveSmallIntegerField(default=1)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    phone = models.CharField(max_length=15, blank=True)
    api_ref = models.CharField("Reference", max_length=80, unique=True)
    state = models.CharField(max_length=12, choices=State.choices, default=State.PENDING)
    failed_reason = models.CharField(max_length=255, blank=True)
    channel = models.CharField(max_length=20, blank=True, help_text="card, mobile_money…")
    applied_at = models.DateTimeField(null=True, blank=True, help_text="When Premium was extended for this payment")
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.vendor} · KES {self.amount} · {self.state}"

    @property
    def expires_at(self):
        if self.product != self.Product.POS:
            return self.vendor.premium_expires_at
        return self.branch.pos_expires_at if self.branch_id else self.vendor.pos_expires_at

    @property
    def is_terminal(self):
        return self.state in (self.State.COMPLETE, self.State.FAILED)

    @property
    def is_stale(self):
        """Checkout left for over an hour — treat as abandoned in the UI."""
        return not self.is_terminal and timezone.now() - self.created_at > timezone.timedelta(hours=1)

    def apply_state(self, state, payload=None):
        """Idempotently record a state from Paystack; on COMPLETE extend the subscription exactly once.
        Row-locked so the webhook, the callback and the reconciler can never double-apply."""
        from django.db import transaction
        state = (state or "").upper()
        if state not in self.State.values:
            return False
        with transaction.atomic():
            locked = Payment.objects.select_for_update().select_related("vendor", "branch").get(pk=self.pk)
            if locked.state == self.State.COMPLETE:
                return False  # already applied; never double-extend
            update = ["state", "updated_at", "raw"]
            locked.state = state
            if payload:
                locked.raw = payload.get("raw", payload)
                locked.failed_reason = (payload.get("failed_reason") or (payload.get("gateway_response") if state == self.State.FAILED else "") or "")[:255]
                locked.channel = (payload.get("channel") or locked.channel or "")[:20]
                update += ["failed_reason", "channel"]
            if state == self.State.COMPLETE and locked.applied_at is None:
                if locked.product == self.Product.POS:
                    locked.vendor.extend_pos(locked.months, branch=locked.branch)
                else:
                    locked.vendor.extend_premium(locked.months)
                locked.applied_at = timezone.now()
                update.append("applied_at")
            locked.save(update_fields=update)
        self.refresh_from_db()
        if state == self.State.COMPLETE:
            from .emails import send_receipt
            send_receipt(self)
        return True

    @classmethod
    def record_manual(cls, vendor, product, months, admin_user, note="", amount=None, until=None, branch=None):
        """Admin activation: creates an auditable COMPLETE payment and extends the subscription.
        If `until` is given the expiry is set to that exact date instead of adding months."""
        from vendors.models import SiteSettings
        site = SiteSettings.get()
        fee = site.pos_fee if product == cls.Product.POS else site.premium_fee
        p = cls.objects.create(vendor=vendor, branch=branch, product=product, months=months or 1, amount=amount if amount is not None else fee * (months or 1),
                               phone="", api_ref=f"manual-{product}-{uuid.uuid4().hex[:12]}",
                               source=cls.Source.MANUAL, note=note[:200], recorded_by=admin_user, state=cls.State.COMPLETE, applied_at=timezone.now())
        if until:
            if product == cls.Product.POS:
                b = branch or vendor.main_branch()
                if b is not None:
                    b.pos_expires_at = until
                    b.save(update_fields=["pos_expires_at"])
                    vendor.sync_pos_expiry()
                else:
                    vendor.pos_expires_at = until
                    vendor.save(update_fields=["pos_expires_at"])
            else:
                vendor.plan = vendor.Plan.PREMIUM
                vendor.premium_paid_at = timezone.now()
                vendor.premium_expires_at = until
                vendor.save(update_fields=["plan", "premium_paid_at", "premium_expires_at"])
        elif product == cls.Product.POS:
            vendor.extend_pos(months, branch=branch)
        else:
            vendor.extend_premium(months)
        from .emails import send_receipt
        send_receipt(p)
        return p

    @classmethod
    def pending_for(cls, vendor, product, minutes=10, branch=None):
        """A checkout started in the last few minutes for this vendor/product/branch."""
        extra = {"branch": branch} if branch is not None else {}
        return cls.objects.filter(vendor=vendor, product=product, source=cls.Source.PAYSTACK, **extra,
                                  state__in=[cls.State.PENDING, cls.State.PROCESSING],
                                  created_at__gte=timezone.now() - timezone.timedelta(minutes=minutes)).order_by("-created_at").first()


class ReminderLog(models.Model):
    """One row per reminder sent, so a vendor never gets the same reminder twice for the same period."""
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="reminders")
    branch = models.ForeignKey("pos.Branch", on_delete=models.CASCADE, null=True, blank=True, related_name="reminders")
    product = models.CharField(max_length=10, choices=Payment.Product.choices)
    kind = models.CharField(max_length=10)  # 7d, 1d, expired
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["vendor", "branch", "product", "kind", "expires_at"]
