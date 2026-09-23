import secrets
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Count, Q, Sum
from django.utils import timezone

from vendors.models import Vendor


def _code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
    return "".join(secrets.choice(alphabet) for _ in range(8))


class Affiliate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="affiliate")
    code = models.CharField(max_length=12, unique=True, default=_code, editable=False)
    is_active = models.BooleanField(default=True)
    class Payout(models.TextChoices):
        MPESA = "mpesa", "M-Pesa"
        BANK = "bank", "Bank transfer"

    payout_method = models.CharField(max_length=10, choices=Payout.choices, default=Payout.MPESA)
    mpesa_number = models.CharField("M-Pesa number", max_length=20, blank=True)
    mpesa_name = models.CharField("Name registered on M-Pesa", max_length=80, blank=True)
    bank_name = models.CharField(max_length=80, blank=True)
    bank_account_name = models.CharField(max_length=80, blank=True)
    bank_account_number = models.CharField(max_length=40, blank=True)
    bank_branch = models.CharField(max_length=80, blank=True)
    notes = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.first_name or self.user.email} ({self.code})"

    @property
    def payout_summary(self):
        if self.payout_method == self.Payout.BANK and self.bank_account_number:
            return f"{self.bank_name} · {self.bank_account_name} · {self.bank_account_number}"
        if self.mpesa_number:
            return f"M-Pesa {self.mpesa_number}{' · ' + self.mpesa_name if self.mpesa_name else ''}"
        return ""

    @property
    def has_payout_details(self):
        return bool(self.payout_summary)

    def link(self, request=None):
        path = f"/join/{self.code}/"
        return request.build_absolute_uri(path) if request else settings.SITE_URL + path

    def stats(self):
        agg = self.referrals.aggregate(
            signups=Count("id"), qualified=Count("id", filter=Q(status__in=["qualified", "paid"])),
            unpaid=Sum("amount", filter=Q(status="qualified")), paid=Sum("amount", filter=Q(status="paid")),
            flagged=Count("id", filter=Q(flagged=True)))
        return {k: (v or 0) for k, v in agg.items()}


class Referral(models.Model):
    """One referred vendor. Earns the reward once the vendor verifies email AND uploads their first product."""
    class Status(models.TextChoices):
        PENDING = "pending", "Signed up"
        QUALIFIED = "qualified", "Qualified (unpaid)"
        PAID = "paid", "Paid"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    affiliate = models.ForeignKey(Affiliate, on_delete=models.CASCADE, related_name="referrals")
    vendor = models.OneToOneField(Vendor, on_delete=models.CASCADE, related_name="referral")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=20)
    signup_ip = models.GenericIPAddressField(null=True, blank=True)
    flagged = models.BooleanField(default=False)
    flag_reason = models.CharField(max_length=200, blank=True)
    qualified_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_ref = models.CharField("Payment reference", max_length=80, blank=True)
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.vendor} via {self.affiliate.code} [{self.status}]"

    @classmethod
    def attach(cls, vendor, code, request=None):
        """Create the referral at sign-up. Returns None if the code is invalid or it looks like self-referral."""
        from vendors.security import client_ip
        from vendors.models import SiteSettings
        aff = Affiliate.objects.filter(code=code, is_active=True).select_related("user").first()
        if not aff or hasattr(vendor, "referral"):
            return None
        ip = client_ip(request) if request else None
        flagged, reason = False, ""
        if vendor.owner.email.lower() == aff.user.email.lower():
            return None  # cannot refer yourself
        if ip and cls.objects.filter(affiliate=aff, signup_ip=ip).exists():
            flagged, reason = True, "Same IP as another sign-up from this affiliate"
        if vendor.owner.phone and vendor.owner.phone == aff.user.phone:
            flagged, reason = True, "Same phone number as the affiliate"
        return cls.objects.create(affiliate=aff, vendor=vendor, amount=SiteSettings.get().affiliate_fee, signup_ip=ip, flagged=flagged, flag_reason=reason)

    def check_qualified(self):
        """Pending → qualified once the vendor is verified and has at least one menu item."""
        if self.status == self.Status.PENDING and self.vendor.owner.email_verified and self.vendor.items.exists():
            self.status = self.Status.QUALIFIED
            self.qualified_at = timezone.now()
            self.save(update_fields=["status", "qualified_at"])
            return True
        return False
