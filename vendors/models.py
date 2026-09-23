import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Avg
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.text import slugify
from django_ckeditor_5.fields import CKEditor5Field

from .counties import COUNTY_CHOICES


class SiteSettings(models.Model):
    """Singleton: admin-controlled plan pricing and free-tier limits."""

    premium_fee = models.DecimalField("Premium fee (KES, per month)", max_digits=10, decimal_places=2, default=1000)
    pos_fee = models.DecimalField("POS module fee (KES, per month)", max_digits=10, decimal_places=2, default=1500)
    affiliate_fee = models.DecimalField("Affiliate reward per qualified sign-up (KES)", max_digits=10, decimal_places=2, default=20)
    free_menu_limit = models.PositiveIntegerField("Free plan: max services", default=10)
    free_photo_limit = models.PositiveIntegerField("Free plan: max gallery photos", default=3)
    payment_instructions = models.TextField(
        default="Pay by card or M-Pesa through Paystack. Your plan is switched on (or extended by a month) as soon as the payment clears."
    )
    branches_open = models.BooleanField("Branches open to all vendors", default=False,
                                        help_text="Off: only vendors already switched on can use multiple branches.")
    support_whatsapp = models.CharField(max_length=20, default="254717183416")
    support_email = models.EmailField(default="beauty@isoftke.com")

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def __str__(self):
        return "Site settings"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


BUSINESS_TYPES = [
    # value, singular label, singular slug, plural label, plural slug, schema.org type
    ("salon", "Salon", "salon", "Salons", "salons", "BeautySalon"),
    ("spa", "Spa", "spa", "Spas", "spas", "DaySpa"),
    ("barber", "Barber", "barber", "Barbers", "barbers", "HairSalon"),
    ("nails", "Nail studio", "nail-studio", "Nail studios", "nail-studios", "NailSalon"),
    ("makeup", "Makeup artist", "makeup-artist", "Makeup artists", "makeup-artists", "BeautySalon"),
    ("massage", "Massage", "massage", "Massage therapists", "massage", "HealthAndBeautyBusiness"),
    ("beauty_shop", "Beauty shop", "beauty-shop", "Beauty shops", "beauty-shops", "HealthAndBeautyBusiness"),
    ("wellness", "Wellness", "wellness", "Wellness centres", "wellness-centres", "HealthAndBeautyBusiness"),
]
ALL_TYPES = ("all", "Beauty & wellness", "beauty", "Beauty & wellness", "beauty", "HealthAndBeautyBusiness")  # the umbrella directory
BT = {row[0]: row for row in BUSINESS_TYPES}
BT_BY_PLURAL_SLUG = {row[4]: row for row in BUSINESS_TYPES}
BT_BY_SINGULAR_SLUG = {row[2]: row for row in BUSINESS_TYPES}


class Tag(models.Model):
    """A service or speciality a business offers: braids, gel nails, deep tissue massage… Powers the directory pages."""
    class Kind(models.TextChoices):
        DISH = "dish", "Service"
        CUISINE = "cuisine", "Speciality"
        MEAL = "meal", "Occasion"
        MENU = "menu", "Service type"

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.DISH)
    description = models.TextField(blank=True, help_text="Optional intro shown on the tag page")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.slug = self.slug or slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("service_tag", args=[self.slug])


class Location(models.Model):
    """County or town/area with at least one vendor. Created automatically from vendor addresses."""
    class Kind(models.TextChoices):
        COUNTY = "county", "County"
        AREA = "area", "Town / area"

    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    county = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="areas")
    intro = models.TextField(blank=True, help_text="Optional unique intro for this location page")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name if self.kind == self.Kind.COUNTY else f"{self.name}, {self.county.name if self.county else ''}"

    @classmethod
    def ensure(cls, county_name, area_name=""):
        county = None
        if county_name:
            county, _ = cls.objects.get_or_create(slug=slugify(county_name), defaults={"name": county_name, "kind": cls.Kind.COUNTY})
        area = None
        if area_name and county:
            aslug = slugify(area_name)
            if aslug == county.slug:
                return county, county
            area, _ = cls.objects.get_or_create(slug=aslug, defaults={"name": area_name.strip(), "kind": cls.Kind.AREA, "county": county})
        return county, area

    def get_absolute_url(self):
        return reverse("places_in", args=[ALL_TYPES[4], self.slug])


class VendorQuerySet(models.QuerySet):
    def live(self):
        return self.filter(is_published=True, is_approved=True)

    def for_cards(self):
        """Everything a vendor card needs without per-row queries (rating + open-now)."""
        from django.db.models import Q
        return self.prefetch_related("hours").annotate(
            avg_rating=Avg("reviews__stars", filter=Q(reviews__is_approved=True, reviews__verified_at__isnull=False)))


class Vendor(models.Model):
    objects = VendorQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class Plan(models.TextChoices):
        FREE = "free", "Free"
        PREMIUM = "premium", "Premium"

    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vendor")
    brand_name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    business_type = models.CharField(max_length=12, choices=[(r[0], r[1]) for r in BUSINESS_TYPES], default="salon")
    tags = models.ManyToManyField(Tag, blank=True, related_name="vendors", verbose_name="Services & specialities")
    logo = models.ImageField(upload_to="logos/", blank=True)
    cover = models.ImageField(upload_to="covers/", blank=True)
    tagline = models.CharField(max_length=160, blank=True)
    about = CKEditor5Field(blank=True)

    # contacts
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField("WhatsApp number (e.g. 2547XXXXXXXX)", max_length=20, blank=True)

    # location
    county = models.CharField(max_length=40, choices=COUNTY_CHOICES, blank=True)
    town = models.CharField("Town / area", max_length=80, blank=True)
    county_loc = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="county_vendors", editable=False)
    area_loc = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="area_vendors", editable=False)
    address = models.CharField(max_length=200, blank=True)
    map_link = models.URLField("Google Maps link", blank=True)
    branches_enabled = models.BooleanField("Multiple branches", default=False,
                                           help_text="Turn on to run more than one outlet under this account.")
    accepts_bookings = models.BooleanField("Take online bookings", default=True)
    home_service = models.BooleanField("Offers home / mobile service", default=False)

    plan = models.CharField(max_length=10, choices=Plan.choices, default=Plan.FREE)
    premium_paid_at = models.DateTimeField("Last premium payment", null=True, blank=True)
    premium_expires_at = models.DateTimeField("Premium expires", null=True, blank=True)
    pos_expires_at = models.DateTimeField("POS module expires", null=True, blank=True)
    is_published = models.BooleanField(default=True)
    is_approved = models.BooleanField("Approved by admin", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-plan", "brand_name"]

    def __str__(self):
        return self.brand_name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.brand_name) or "vendor"
            slug, i = base, 2
            while Vendor.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, i = f"{base}-{i}", i + 1
            self.slug = slug
        self.county_loc, self.area_loc = Location.ensure(self.county, self.town)
        from .sanitize import clean_html
        self.about = clean_html(self.about)
        first_save = self._state.adding
        super().save(*args, **kwargs)
        if first_save:
            self.main_branch()          # a new business starts with its main branch ready

    def get_absolute_url(self):
        return reverse("vendor_detail", args=[self.type_slug, self.slug])

    @property
    def type_row(self):
        return BT.get(self.business_type, BT["salon"])

    @property
    def type_slug(self):
        return self.type_row[2]

    @property
    def type_plural_slug(self):
        return self.type_row[4]

    @property
    def type_label(self):
        return self.type_row[1]

    @property
    def schema_type(self):
        return self.type_row[5]

    @property
    def seo_title(self):
        loc = self.town or self.county
        return f"{self.brand_name} — services & prices{f' in {loc}' if loc else ''} | BeautyFlow"

    @cached_property
    def seo_description(self):
        bits = [self.tagline] if self.tagline else []
        loc = ", ".join(x for x in [self.town, self.county] if x)
        bits.append(f"{self.type_label} in {loc}." if loc else f"{self.type_label} in Kenya.")
        names = [] if self.menu_locked else list(self.items.filter(is_available=True).values_list("name", flat=True)[:5])
        if names:
            bits.append("Services include " + ", ".join(names) + ".")
        bits.append("See prices and book online.")
        return " ".join(bits)[:300]

    @property
    def is_premium(self):
        """Premium is a monthly subscription. Paying for POS includes it at no extra cost."""
        if self.pos_active:
            return True
        if self.plan != self.Plan.PREMIUM:
            return False
        return self.premium_expires_at is None or self.premium_expires_at >= timezone.now()

    @property
    def subscription_expired(self):
        """Had Premium, but it has lapsed and not been renewed. An active POS keeps the listing open."""
        if self.pos_active:
            return False
        return self.plan == self.Plan.PREMIUM and self.premium_expires_at is not None and self.premium_expires_at < timezone.now()

    @property
    def menu_locked(self):
        """Public menu is hidden until the vendor renews."""
        return self.subscription_expired

    @property
    def premium_days_left(self):
        if self.pos_active and (self.premium_expires_at is None or self.premium_expires_at < timezone.now()):
            return max((self.pos_expires_at - timezone.now()).days, 0)      # included with POS
        if not self.is_premium or not self.premium_expires_at:
            return None
        return max((self.premium_expires_at - timezone.now()).days, 0)

    # ── POS module (separate monthly subscription)
    @property
    def pos_active(self):
        return self.pos_expires_at is not None and self.pos_expires_at >= timezone.now()

    @property
    def pos_expired(self):
        return self.pos_expires_at is not None and self.pos_expires_at < timezone.now()

    @property
    def pos_days_left(self):
        return max((self.pos_expires_at - timezone.now()).days, 0) if self.pos_active else None

    def sync_pos_expiry(self):
        """Vendor-level POS expiry mirrors the furthest active branch, so existing checks keep working."""
        from django.db.models import Max
        far = self.branches.aggregate(m=Max("pos_expires_at"))["m"]
        if far != self.pos_expires_at:
            self.pos_expires_at = far
            Vendor.objects.filter(pk=self.pk).update(pos_expires_at=far)

    @property
    def can_use_branches(self):
        """The Branches page is open to this vendor: either switched on for them, or open to everyone."""
        return self.branches_enabled or SiteSettings.get().branches_open

    def main_branch(self):
        """Every business has one outlet from the day it signs up; created on demand if it is missing."""
        b = self.branches.filter(is_main=True).first() or self.branches.first()
        if b is None and self.pk:
            from pos.models import Branch
            b = Branch.objects.create(vendor=self, name="Main branch", location=(self.town or "")[:80],
                                      is_main=True, pos_expires_at=self.pos_expires_at)
        return b

    def extend_pos(self, months=1, branch=None):
        """A month of POS is bought per branch. The vendor's own expiry mirrors the furthest branch."""
        b = branch or self.main_branch()
        if b is not None:
            b.extend_pos(months)
            self.refresh_from_db(fields=["pos_expires_at"])
            return
        now = timezone.now()
        base = self.pos_expires_at if (self.pos_expires_at and self.pos_expires_at > now) else now
        self.pos_expires_at = base + timedelta(days=30 * months)
        self.save(update_fields=["pos_expires_at"])

    def extend_premium(self, months=1):
        """Record a monthly payment: extend from current expiry if still active, else from now."""
        now = timezone.now()
        base = self.premium_expires_at if (self.plan == self.Plan.PREMIUM and self.premium_expires_at and self.premium_expires_at > now) else now
        self.plan = self.Plan.PREMIUM
        self.premium_paid_at = now
        self.premium_expires_at = base + timedelta(days=30 * months)
        self.save(update_fields=["plan", "premium_paid_at", "premium_expires_at"])

    @staticmethod
    def normalize_msisdn(raw):
        """07xx / 01xx / 2547xx / +2547xx / 7xx → 2547xx (empty if not a Kenyan mobile)."""
        d = "".join(c for c in (raw or "") if c.isdigit())
        if d.startswith("0") and len(d) == 10:
            d = "254" + d[1:]
        elif len(d) == 9 and d[0] in "17":
            d = "254" + d
        return d if (len(d) == 12 and d.startswith("254") and d[3] in "17") else ""

    @property
    def whatsapp_msisdn(self):
        return self.normalize_msisdn(self.whatsapp)

    @property
    def whatsapp_link(self):
        d = self.whatsapp_msisdn
        return f"https://wa.me/{d}" if d else ""

    @property
    def is_open_now(self):
        """True/False from opening hours; None when hours are not set. One query, or none when hours are prefetched."""
        now = timezone.localtime()
        hours = list(self.hours.all())
        if not any(x.opens for x in hours):
            return None
        h = next((x for x in hours if x.day == now.weekday()), None)
        if h is None or h.closed or not h.opens or not h.closes:
            return False
        t = now.time()
        return h.opens <= t < h.closes if h.opens <= h.closes else (t >= h.opens or t < h.closes)

    @property
    def is_live(self):
        return self.is_published and self.is_approved

    # What a listing needs before it is worth showing the public. (field label, weight, test)
    PROFILE_CHECKS = [
        ("County and town", 20, lambda v: bool(v.county and v.town)),
        ("Phone or WhatsApp", 10, lambda v: bool(v.phone or v.whatsapp)),
        ("Business logo", 20, lambda v: bool(v.logo)),
        ("Cover photo", 10, lambda v: bool(v.cover)),
        ("A line about the business", 10, lambda v: bool(v.tagline or v.about)),
        ("Opening hours", 10, lambda v: v.hours.exclude(opens=None).exists()),
        ("At least one service", 20, lambda v: v.items.exists()),
    ]
    # Without these the page would be useless, so they decide whether it goes live.
    REQUIRED_FOR_PUBLIC = {"County and town", "Phone or WhatsApp", "Business logo", "At least one service"}

    def profile_progress(self):
        """(score out of 100, done labels, missing labels) — drives the dashboard meter."""
        done, missing, score = [], [], 0
        for label, weight, test in self.PROFILE_CHECKS:
            if test(self):
                done.append(label)
                score += weight
            else:
                missing.append(label)
        return score, done, missing

    @property
    def profile_score(self):
        return self.profile_progress()[0]

    def missing_for_public(self):
        return [m for m in self.profile_progress()[2] if m in self.REQUIRED_FOR_PUBLIC]

    def maybe_publish(self):
        """Go live once the essentials are in. Never takes a live listing down."""
        if self.is_published or self.missing_for_public():
            return False
        Vendor.objects.filter(pk=self.pk).update(is_published=True)
        self.is_published = True
        return True

    def rating(self):
        if not hasattr(self, "avg_rating"):  # else annotated by Vendor.objects.for_cards()
            self.avg_rating = self.reviews.filter(is_approved=True, verified_at__isnull=False).aggregate(a=Avg("stars"))["a"]
        return self.avg_rating or 0

    def review_count(self):
        return self.reviews.filter(is_approved=True, verified_at__isnull=False).count()

    # plan limits
    def can_add_item(self):
        return self.is_premium or self.items.count() < SiteSettings.get().free_menu_limit

    def can_add_photo(self):
        return self.is_premium or self.photos.count() < SiteSettings.get().free_photo_limit


STANDARD_MENU_TYPES = [
    "Hair", "Braids & locs", "Barbering", "Nails", "Lashes & brows", "Makeup", "Facials & skin care", "Waxing & threading",
    "Massage", "Body treatments", "Spa packages", "Bridal", "Men's grooming", "Kids", "Wellness", "Products",
]


class MenuCategory(models.Model):
    """Service group: Hair, Nails, Massage, Facials…"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=60)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "service categories"
        unique_together = ["vendor", "name"]

    def __str__(self):
        return self.name


VAT_RATE = Decimal("0.16")


DISCOUNT_CHOICES = [("", "No discount"), ("percent", "Percent off"), ("amount", "KES off")]


class MenuItem(models.Model):
    """A service on the price list (the model keeps its old name; everything the user sees says "service")."""
    class Vat(models.TextChoices):
        INCLUDED = "incl", "Price includes VAT"
        ADD = "add", "Add 16% VAT on top"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="items")
    category = models.ForeignKey(MenuCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="items")
    name = models.CharField(max_length=120)
    image = models.ImageField(upload_to="services/", blank=True)
    net_price = models.DecimalField("Price (KES)", max_digits=10, decimal_places=2, null=True, blank=True,
                                    help_text="The price you enter. Choose below whether VAT is already included.")
    vat_mode = models.CharField("VAT", max_length=4, choices=Vat.choices, default=Vat.INCLUDED)
    duration_min = models.PositiveSmallIntegerField("Duration (minutes)", default=60)
    discount_type = models.CharField("Discount", max_length=8, choices=DISCOUNT_CHOICES, blank=True)
    discount_value = models.DecimalField("Discount amount", max_digits=10, decimal_places=2, default=0,
                                         help_text="Percent off (e.g. 20) or KES off (e.g. 500)")
    discount_ends = models.DateField("Discount ends", null=True, blank=True, help_text="Leave blank to keep it running")
    price_on_request = models.BooleanField("Price on request", default=False,
                                           help_text="No fixed price — clients ask for a quote (bridal, events, home visits).")
    price = models.DecimalField("Public price (KES)", max_digits=10, decimal_places=2, editable=False, default=0)
    description = CKEditor5Field(blank=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category__order", "name"]
        indexes = [models.Index(fields=["vendor", "is_available"], name="menuitem_vendor_avail_idx")]

    def __str__(self):
        return f"{self.name} — {'price on request' if self.price_on_request else f'KES {self.price}'}"

    def save(self, *args, **kwargs):
        # Public price is always the final amount; VAT maths never shows on the public page.
        if self.price_on_request:
            self.net_price = Decimal("0")
        if self.net_price is None:
            self.net_price = self.price
        base = Decimal(self.net_price)
        self.price = (base * (1 + VAT_RATE)).quantize(Decimal("0.01")) if self.vat_mode == self.Vat.ADD else base
        self._drop_menu_cache()
        from .sanitize import clean_html
        self.description = clean_html(self.description)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._drop_menu_cache()
        return super().delete(*args, **kwargs)

    def _drop_menu_cache(self):
        from django.core.cache import cache
        cache.delete_many([f"jsonld_menu:{self.vendor_id}", "home_seo_block"])

    @property
    def duration_label(self):
        h, m = divmod(self.duration_min or 0, 60)
        return " ".join(x for x in [f"{h} hr" if h else "", f"{m} min" if m else ""] if x) or "—"

    @property
    def discount_live(self):
        """The discount is on today."""
        if not self.discount_type or not self.discount_value:
            return False
        return self.discount_ends is None or self.discount_ends >= timezone.localdate()

    def apply_discount(self, amount):
        amount = Decimal(amount or 0)
        if not self.discount_live:
            return amount
        if self.discount_type == "percent":
            off = amount * min(Decimal(self.discount_value), Decimal(100)) / 100
        else:
            off = min(Decimal(self.discount_value), amount)
        return (amount - off).quantize(Decimal("0.01"))

    @property
    def sale_price(self):
        """What the client pays today, after the service's own discount."""
        return self.apply_discount(self.price)

    @property
    def discount_label(self):
        if not self.discount_live:
            return ""
        v = self.discount_value
        return f"{v:,.0f}% off" if self.discount_type == "percent" else f"KES {v:,.0f} off"

    def branch_price(self, branch=None):
        """The override row for this branch, or None when it charges the business price."""
        if branch is None or self.price_on_request:
            return None
        from pos.models import BranchPrice
        return BranchPrice.objects.filter(branch=branch, item=self).first()

    def list_price_at(self, branch=None):
        """This branch's price before any discount."""
        row = self.branch_price(branch)
        return row.price if row else self.price

    def price_at(self, branch=None):
        """What this branch charges today, discount included."""
        return self.apply_discount(self.list_price_at(branch))

    def vat_at(self, branch=None):
        """VAT inside price_at. Either way the charged price carries VAT, so it is 16/116 of it."""
        gross = self.price_at(branch)
        return (gross - gross / (1 + VAT_RATE)).quantize(Decimal("0.01"))

    @property
    def vat_amount(self):
        """VAT inside the public price. 'add' = price minus the net entered; 'incl' = 16/116 of the price."""
        if self.vat_mode == self.Vat.ADD:
            return self.price - Decimal(self.net_price or 0)
        return (self.price - (self.price / (1 + VAT_RATE))).quantize(Decimal("0.01"))


class Photo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="gallery/")
    caption = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.caption or f"Photo {self.pk}"


class OpeningHours(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    DAYS = [(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"), (4, "Friday"), (5, "Saturday"), (6, "Sunday")]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="hours")
    day = models.PositiveSmallIntegerField(choices=DAYS)
    opens = models.TimeField(null=True, blank=True)
    closes = models.TimeField(null=True, blank=True)
    closed = models.BooleanField(default=False)

    class Meta:
        ordering = ["day"]
        unique_together = ["vendor", "day"]
        verbose_name_plural = "opening hours"

    @property
    def all_day(self):
        """00:00 to 23:59 (or 00:00) means the place never closes that day."""
        return bool(self.opens and self.closes and self.opens.hour == 0 and self.opens.minute == 0
                    and (self.closes.hour == 23 and self.closes.minute >= 59 or self.closes.hour == 0 and self.closes.minute == 0))

    def __str__(self):
        return self.get_day_display()


class Offer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="offers")
    title = models.CharField(max_length=120)
    details = models.TextField(blank=True)
    image = models.ImageField(upload_to="offers/", blank=True)
    starts = models.DateField(null=True, blank=True)
    ends = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def status(self):
        """paused / scheduled / expired / live — what the customer actually sees right now."""
        today = timezone.localdate()
        if not self.is_active:
            return "paused"
        if self.starts and self.starts > today:
            return "scheduled"
        if self.ends and self.ends < today:
            return "expired"
        return "live"


class Inquiry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class Kind(models.TextChoices):
        INQUIRY = "inquiry", "Question"
        QUOTE = "quote", "Quote request"

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        CONVERTED = "converted", "Booked"
        CLOSED = "closed", "Closed"

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="inquiries")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.INQUIRY)
    name = models.CharField(max_length=80)
    phone = models.CharField(max_length=20)
    message = models.TextField(blank=True)
    item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Service")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW, db_index=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def wa_link(self):
        d = Vendor.normalize_msisdn(self.phone)
        return f"https://wa.me/{d}" if d else ""

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "inquiries"

    def __str__(self):
        return f"{self.get_kind_display()} from {self.name}"


class Review(models.Model):
    """One review per email address per business, confirmed with an emailed code."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="reviews")
    name = models.CharField(max_length=80)
    email = models.EmailField(db_index=True)
    stars = models.PositiveSmallIntegerField(choices=[(i, f"{i} star{'s' if i > 1 else ''}") for i in range(1, 6)])
    comment = models.TextField(blank=True)
    is_approved = models.BooleanField(default=True)   # admin can hide
    verified_at = models.DateTimeField(null=True, blank=True)
    code = models.CharField(max_length=6, blank=True)
    code_expires = models.DateTimeField(null=True, blank=True)
    code_attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ["vendor", "email"]

    @property
    def is_live(self):
        return self.is_approved and self.verified_at is not None

    def issue_code(self):
        import secrets
        self.code = f"{secrets.randbelow(1_000_000):06d}"
        self.code_expires = timezone.now() + timedelta(minutes=15)
        self.code_attempts = 0
        self.save(update_fields=["code", "code_expires", "code_attempts"])
        return self.code

    def check_code(self, code):
        import secrets
        if not self.code or not self.code_expires or self.code_expires < timezone.now() or self.code_attempts >= 5:
            return False
        if not secrets.compare_digest(self.code, (code or "").strip()):
            self.code_attempts += 1
            self.save(update_fields=["code_attempts"])
            return False
        self.verified_at = timezone.now()
        self.code = ""
        self.save(update_fields=["verified_at", "code"])
        return True

    def __str__(self):
        return f"{self.stars}★ by {self.name}"


class Customer(models.Model):
    """A business's client, keyed by phone — built automatically from sales, bookings and inquiries."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="customers")
    phone = models.CharField(max_length=15)  # 2547XXXXXXXX
    name = models.CharField(max_length=80, blank=True)
    orders_count = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    opt_out = models.BooleanField(default=False)

    class Meta:
        unique_together = ["vendor", "phone"]
        ordering = ["-last_seen"]

    def __str__(self):
        return f"{self.name or self.phone} @ {self.vendor}"

    @property
    def wa_link(self):
        return f"https://wa.me/{self.phone}"

    @classmethod
    def touch(cls, vendor, phone, name="", amount=None, order=False):
        msisdn = Vendor.normalize_msisdn(phone)
        if not msisdn:
            return None
        c, _ = cls.objects.get_or_create(vendor=vendor, phone=msisdn, defaults={"name": name[:80]})
        if name and not c.name:
            c.name = name[:80]
        if order:
            c.orders_count += 1
            if amount:
                c.total_spent += amount
        c.save()
        return c
