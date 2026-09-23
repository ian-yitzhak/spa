import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        VENDOR = "vendor", "Vendor"
        TEAM = "team", "Team member"
        AFFILIATE = "affiliate", "Affiliate"

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.VENDOR)
    email_verified = models.BooleanField(default=False)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    @property
    def is_vendor(self):
        return self.role == self.Role.VENDOR

    @property
    def is_affiliate(self):
        return self.role == self.Role.AFFILIATE

    @property
    def is_team(self):
        """Staff or cashier at a business (the Staff row says which)."""
        return self.role == self.Role.TEAM

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    def __str__(self):
        return self.get_full_name() or self.email


class OneTimeCode(models.Model):
    """6-digit code emailed for email verification or login OTP."""

    class Purpose(models.TextChoices):
        VERIFY = "verify", "Email verification"
        LOGIN = "login", "Login OTP"
        RESET = "reset", "Password reset"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="codes")
    purpose = models.CharField(max_length=10, choices=Purpose.choices)
    code = models.CharField(max_length=6)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_purpose_display()} for {self.user}"

    @classmethod
    def issue(cls, user, purpose):
        """Invalidate older codes for this purpose and create a fresh one."""
        cls.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(used_at=timezone.now())
        return cls.objects.create(
            user=user, purpose=purpose,
            code=f"{secrets.randbelow(1_000_000):06d}",
            expires_at=timezone.now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
        )

    @classmethod
    def verify(cls, user, purpose, code):
        """Return True and consume the code if it matches; False otherwise."""
        otp = cls.objects.filter(user=user, purpose=purpose, used_at__isnull=True).first()
        if otp is None or otp.expires_at < timezone.now() or otp.attempts >= settings.OTP_MAX_ATTEMPTS:
            return False
        if not secrets.compare_digest(otp.code, (code or "").strip()):
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            return False
        otp.used_at = timezone.now()
        otp.save(update_fields=["used_at"])
        return True

    @classmethod
    def can_resend(cls, user, purpose, cooldown_seconds=60):
        last = cls.objects.filter(user=user, purpose=purpose).first()
        return last is None or (timezone.now() - last.created_at).total_seconds() >= cooldown_seconds
