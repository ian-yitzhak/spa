import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models, transaction
from django.db.models import Max, Sum
from django.utils import timezone

from vendors.models import MenuItem, Vendor

CENTS = Decimal("0.01")


def _money(x):
    return Decimal(x or 0).quantize(CENTS, rounding=ROUND_HALF_UP)


class Commission(models.TextChoices):
    PERCENT = "percent", "Percentage of the service"
    FIXED = "fixed", "Fixed amount per service"


def rate_label(kind, value):
    v = Decimal(value or 0)
    shown = f"{v:,.0f}" if v == v.to_integral() else f"{v:,.2f}"
    return f"{shown}%" if kind == Commission.PERCENT else f"KES {shown}"


class Staff(models.Model):
    """Someone who works for one business. Staff do the services and earn commission; cashiers take payments."""
    class Role(models.TextChoices):
        STAFF = "staff", "Staff"
        CASHIER = "cashier", "Cashier"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="staff")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_profile")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STAFF)
    branch = models.ForeignKey("pos.Branch", on_delete=models.SET_NULL, null=True, blank=True, related_name="staff")
    job_title = models.CharField("Job title", max_length=60, blank=True, help_text='e.g. "Senior stylist", "Nail tech"')
    hired_on = models.DateField("Start date", null=True, blank=True)
    commission_type = models.CharField("Commission", max_length=8, choices=Commission.choices, default=Commission.PERCENT)
    commission_value = models.DecimalField("Rate", max_digits=10, decimal_places=2, default=0,
                                           help_text="Percent (e.g. 30) or KES per service (e.g. 200)")
    services = models.ManyToManyField(MenuItem, through="StaffService", blank=True, related_name="staff")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__first_name"]
        verbose_name_plural = "staff"

    def __str__(self):
        return f"{self.name} @ {self.vendor}"

    @property
    def name(self):
        return self.user.first_name or self.user.email

    @property
    def is_cashier(self):
        return self.role == self.Role.CASHIER

    @property
    def rate_label(self):
        return rate_label(self.commission_type, self.commission_value)

    def rate_for(self, item):
        """(type, value) this person earns on a service: their own rate for it, else their default."""
        link = self.service_links.filter(service=item).first() if item is not None else None
        if link and link.has_own_rate:
            return link.commission_type, link.commission_value
        return self.commission_type, self.commission_value

    def commission_on(self, item, amount, qty=1):
        kind, value = self.rate_for(item)
        if kind == Commission.FIXED:
            return _money(Decimal(value or 0) * qty)
        return _money(Decimal(amount or 0) * Decimal(value or 0) / 100)

    def earned_lines(self):
        """Every paid service this person did."""
        return OrderItem.objects.filter(staff=self, order__paid_at__isnull=False).exclude(order__status=Order.Status.CANCELLED)

    def unpaid_lines(self):
        return self.earned_lines().filter(payout__isnull=True)

    def balance(self):
        return self.unpaid_lines().aggregate(t=Sum("commission"))["t"] or Decimal("0")


class StaffService(models.Model):
    """A service this person does. Leave the rate blank to use their default commission."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="service_links")
    service = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name="staff_links")
    commission_type = models.CharField(max_length=8, choices=Commission.choices, blank=True)
    commission_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ["staff", "service"]
        ordering = ["service__name"]

    @property
    def has_own_rate(self):
        return bool(self.commission_type) and self.commission_value is not None

    @property
    def rate_label(self):
        if self.has_own_rate:
            return rate_label(self.commission_type, self.commission_value)
        return self.staff.rate_label


class Branch(models.Model):
    """A physical outlet. Every vendor has a main branch; extra branches are paid for separately."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField("Branch name", max_length=40, default="Main branch")
    location = models.CharField("Location", max_length=80, blank=True)
    is_main = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    pos_expires_at = models.DateTimeField("POS expires", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_main", "name"]
        unique_together = ["vendor", "name"]
        verbose_name_plural = "branches"

    def __str__(self):
        return f"{self.name}{f' · {self.location}' if self.location else ''}"

    @property
    def pos_active(self):
        return self.pos_expires_at is not None and self.pos_expires_at >= timezone.now()

    @property
    def pos_expired(self):
        return self.pos_expires_at is not None and self.pos_expires_at < timezone.now()

    @property
    def days_left(self):
        if not self.pos_active:
            return 0
        return max((self.pos_expires_at - timezone.now()).days, 0)

    pos_days_left = days_left

    def extend_pos(self, months=1):
        from datetime import timedelta
        now = timezone.now()
        base = self.pos_expires_at if (self.pos_expires_at and self.pos_expires_at > now) else now
        self.pos_expires_at = base + timedelta(days=30 * months)
        self.save(update_fields=["pos_expires_at"])
        self.vendor.sync_pos_expiry()


class BranchPrice(models.Model):
    """What this branch charges for a service. No row means it charges the business price."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="prices")
    item = models.ForeignKey("vendors.MenuItem", on_delete=models.CASCADE, related_name="branch_prices")
    net_price = models.DecimalField("Price (KES)", max_digits=10, decimal_places=2,
                                    help_text="Entered the same way as the service: VAT included, or net if the service adds VAT.")
    price = models.DecimalField("Public price (KES)", max_digits=10, decimal_places=2, editable=False, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["branch", "item"]
        ordering = ["item__name"]

    def __str__(self):
        return f"{self.item.name} @ {self.branch.name}: KES {self.price}"

    def save(self, *args, **kwargs):
        from vendors.models import VAT_RATE
        base = Decimal(self.net_price or 0)
        self.price = (base * (1 + VAT_RATE)).quantize(CENTS) if self.item.vat_mode == "add" else base
        super().save(*args, **kwargs)


class StaffShift(models.Model):
    """When someone is on the rota. The owner plans it; staff see their own on their dashboard."""
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        WORKED = "worked", "Worked"
        ABSENT = "absent", "Absent"
        LEAVE = "leave", "On leave"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="staff_shifts")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="staff_shifts")
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="shifts")
    date = models.DateField()
    starts = models.TimeField()
    ends = models.TimeField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PLANNED)
    note = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "starts"]
        indexes = [models.Index(fields=["vendor", "date"])]

    def __str__(self):
        return f"{self.staff.name} · {self.date:%a %d %b} {self.starts:%H:%M}–{self.ends:%H:%M}"

    @property
    def hours(self):
        from datetime import datetime
        a, b = datetime.combine(self.date, self.starts), datetime.combine(self.date, self.ends)
        mins = (b - a).total_seconds() / 60
        if mins < 0:
            mins += 24 * 60
        return round(mins / 60, 1)


CODE_CHARS = "ACDEFGHJKLMNPQRSTUVWXYZ2345679"  # no 0/O/1/I/B/8 — people read these out on the phone


def new_order_code(vendor_id, length=6):
    """Random receipt number, unique within the vendor."""
    import secrets
    for _ in range(20):
        code = "".join(secrets.choice(CODE_CHARS) for _ in range(length))
        if not Order.objects.filter(vendor_id=vendor_id, code=code).exists():
            return code
    return "".join(secrets.choice(CODE_CHARS) for _ in range(length + 2))


class Order(models.Model):
    """One client's visit: the services they had, who did them, and how they paid."""
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"          # being built on the POS screen
        OPEN = "open", "In service"       # client is in the chair, pays later
        DONE = "done", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        MPESA = "mpesa", "M-Pesa"
        CARD = "card", "Card"
        SPLIT = "split", "M-Pesa & cash"

    class Source(models.TextChoices):
        POS = "pos", "Walk-in"
        BOOKING = "booking", "Booking"

    class Discount(models.TextChoices):
        PERCENT = "percent", "%"
        AMOUNT = "amount", "KES"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="orders")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders", db_index=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.POS, db_index=True)
    customer_name = models.CharField("Client", max_length=80, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True, db_index=True)
    number = models.PositiveIntegerField(default=0)          # internal per-vendor sequence, set when placed
    code = models.CharField("Receipt no.", max_length=10, blank=True, db_index=True)
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="+", help_text="Who rang up the sale")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    notes = models.CharField(max_length=200, blank=True)

    gross = models.DecimalField(max_digits=12, decimal_places=2, default=0)       # before the sale discount
    discount_type = models.CharField(max_length=8, choices=Discount.choices, blank=True)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)    # KES taken off
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)    # net of VAT
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    payment_method = models.CharField(max_length=10, choices=Method.choices, blank=True)
    payment_ref = models.CharField("Transaction ref", max_length=60, blank=True)
    payer_name = models.CharField("Paid by (name)", max_length=80, blank=True)
    amount_tendered = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    paid_mpesa = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_cash = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True)

    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconcile_note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    placed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["vendor", "status"]), models.Index(fields=["vendor", "paid_at"])]

    def __str__(self):
        return f"Sale #{self.ref} ({self.get_status_display()})"

    @property
    def ref(self):
        return self.code or str(self.number or "—")

    @property
    def is_paid(self):
        return self.paid_at is not None

    @property
    def label(self):
        return self.customer_name or "Walk-in"

    @property
    def received(self):
        if self.payment_method == self.Method.SPLIT:
            return (self.paid_mpesa or 0) + (self.paid_cash or 0)
        return self.amount_tendered

    @property
    def change_due(self):
        got = self.received
        if got is None:
            return Decimal("0")
        return max(Decimal(got) - self.total, Decimal("0"))

    def save(self, *args, **kwargs):
        if self.branch_id is None and self.vendor_id:      # never leave a sale outside a branch
            self.branch = self.vendor.main_branch()
            if self.branch_id and kwargs.get("update_fields"):
                kwargs["update_fields"] = list(kwargs["update_fields"]) + ["branch"]
        super().save(*args, **kwargs)

    def recalc(self):
        """Totals from the lines, then the sale discount off the top. VAT shrinks with the discount."""
        agg = self.items.aggregate(g=Sum("line_total"), t=Sum("line_tax"))
        gross, tax = _money(agg["g"]), _money(agg["t"])
        if self.discount_type == self.Discount.PERCENT:
            off = _money(gross * min(Decimal(self.discount_value or 0), Decimal(100)) / 100)
        elif self.discount_type == self.Discount.AMOUNT:
            off = min(_money(self.discount_value), gross)
        else:
            off = Decimal("0")
        total = gross - off
        tax = _money(tax * total / gross) if gross else Decimal("0")
        self.gross, self.discount, self.total, self.tax, self.subtotal = gross, off, total, tax, total - tax
        self.save(update_fields=["gross", "discount", "total", "tax", "subtotal", "updated_at"])

    def place(self):
        """Draft → open: give it a receipt number for this vendor."""
        with transaction.atomic():
            Vendor.objects.select_for_update().get(pk=self.vendor_id)
            last = Order.objects.filter(vendor=self.vendor, number__gt=0).aggregate(m=Max("number"))["m"] or 0
            self.number = last + 1
            if not self.code:
                self.code = new_order_code(self.vendor_id)
            self.status = self.Status.OPEN
            self.placed_at = timezone.now()
            self.save(update_fields=["number", "code", "status", "placed_at", "updated_at"])

    def settle_commissions(self):
        """What each staff member earned on this sale. Worked out on what the client actually paid,
        so a sale discount comes off everyone's share. Lines already paid out are never touched."""
        share = (self.total / self.gross) if self.gross else Decimal("0")
        for line in self.items.select_related("staff", "menu_item").filter(payout__isnull=True):
            earned = line.staff.commission_on(line.menu_item, line.line_total * share, line.qty) if line.staff_id else Decimal("0")
            if earned != line.commission:
                OrderItem.objects.filter(pk=line.pk).update(commission=earned)

    def mark_paid(self, method, ref="", tendered=None, payer_name="", by=None):
        if self.status == self.Status.DRAFT:
            self.place()
        self.payment_method, self.payment_ref, self.payer_name = method, ref[:60], payer_name[:80]
        self.amount_tendered = tendered
        self.paid_at = timezone.now()
        self.status = self.Status.DONE
        if by is not None and self.cashier_id is None:
            self.cashier = by
        self.save(update_fields=["payment_method", "payment_ref", "payer_name", "amount_tendered", "paid_at", "status",
                                 "cashier", "updated_at"])
        self.settle_commissions()
        if self.customer_phone:
            from vendors.models import Customer
            Customer.touch(self.vendor, self.customer_phone, self.customer_name, amount=self.total, order=True)


class OrderItem(models.Model):
    """One service on a sale, and the staff member who did it."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="sold")
    staff = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name="lines")
    name = models.CharField(max_length=120)
    list_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)   # before the service's own discount
    unit_net = models.DecimalField(max_digits=10, decimal_places=2)
    unit_tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    qty = models.PositiveIntegerField(default=1)
    line_net = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payout = models.ForeignKey("pos.StaffPayout", on_delete=models.SET_NULL, null=True, blank=True, related_name="lines")

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        self.line_net = self.unit_net * self.qty
        self.line_tax = self.unit_tax * self.qty
        self.line_total = self.unit_price * self.qty
        super().save(*args, **kwargs)

    @property
    def discounted(self):
        return bool(self.list_price) and self.list_price > self.unit_price

    @classmethod
    def add(cls, order, menu_item, qty=1, staff=None):
        """A service goes on the ticket. The same service by the same person just adds one."""
        line = order.items.filter(menu_item=menu_item, staff=staff).first()
        if line:
            line.qty += qty
            line.save()
        else:
            gross, vat = menu_item.price_at(order.branch), menu_item.vat_at(order.branch)
            line = cls.objects.create(order=order, menu_item=menu_item, staff=staff, name=menu_item.name,
                                      list_price=menu_item.list_price_at(order.branch), unit_net=gross - vat,
                                      unit_tax=vat, unit_price=gross, qty=qty)
        order.recalc()
        return line


class StaffPayout(models.Model):
    """The owner paying someone their commission. Covers the lines linked to it, plus any bonus or deduction."""
    class Method(models.TextChoices):
        MPESA = "mpesa", "M-Pesa"
        CASH = "cash", "Cash"
        BANK = "bank", "Bank transfer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="payouts")
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="payouts")
    number = models.PositiveIntegerField(default=0)
    period_from = models.DateField(null=True, blank=True)
    period_to = models.DateField(null=True, blank=True)
    services_count = models.PositiveIntegerField(default=0)
    sales_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bonus = models.DecimalField("Bonus / tips", max_digits=12, decimal_places=2, default=0)
    deduction = models.DecimalField("Deductions / advances", max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField("Paid", max_digits=12, decimal_places=2, default=0)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.MPESA)
    reference = models.CharField("M-Pesa / bank ref", max_length=60, blank=True)
    note = models.CharField(max_length=200, blank=True)
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    paid_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-paid_at"]

    def __str__(self):
        return f"Payout #{self.number} · {self.staff.name} · KES {self.amount:,.0f}"

    @classmethod
    def pay(cls, staff, line_ids, by, method, reference="", note="", bonus=0, deduction=0):
        """Mark these unpaid lines as paid in one payout. Returns None when there is nothing to pay."""
        bonus, deduction = _money(bonus), _money(deduction)
        with transaction.atomic():
            Vendor.objects.select_for_update().get(pk=staff.vendor_id)
            lines = staff.unpaid_lines().filter(pk__in=list(line_ids))
            agg = lines.aggregate(c=Sum("commission"), v=Sum("line_total"), n=Sum("qty"),
                                  a=models.Min("order__paid_at"), b=Max("order__paid_at"))
            if not agg["n"] and not bonus:
                return None
            commission = _money(agg["c"])
            last = cls.objects.filter(vendor_id=staff.vendor_id).aggregate(m=Max("number"))["m"] or 0
            p = cls.objects.create(
                vendor_id=staff.vendor_id, staff=staff, number=last + 1, services_count=agg["n"] or 0,
                period_from=timezone.localtime(agg["a"]).date() if agg["a"] else None,
                period_to=timezone.localtime(agg["b"]).date() if agg["b"] else None,
                sales_value=_money(agg["v"]), commission=commission, bonus=bonus, deduction=deduction,
                amount=max(commission + bonus - deduction, Decimal("0")), method=method,
                reference=reference[:60], note=note[:200], paid_by=by)
            OrderItem.objects.filter(pk__in=list(lines.values_list("pk", flat=True))).update(payout=p)
        return p


class Booking(models.Model):
    """A client's appointment: one or more services, optionally with a named staff member."""
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        CONFIRMED = "confirmed", "Confirmed"
        DONE = "done", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No-show"

    class Source(models.TextChoices):
        ONLINE = "online", "Online"
        PHONE = "phone", "Phone / WhatsApp"
        WALK_IN = "walk_in", "Walk-in"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="bookings")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="bookings")
    staff = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name="bookings",
                              help_text="Leave blank for anyone available")
    name = models.CharField("Client name", max_length=80)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    date = models.DateField()
    time = models.TimeField()
    duration_min = models.PositiveSmallIntegerField("Minutes", default=60)
    note = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.ONLINE)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    order = models.OneToOneField(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="booking")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "time"]
        indexes = [models.Index(fields=["vendor", "date"])]

    def __str__(self):
        return f"{self.name} · {self.date} {self.time:%H:%M}"

    @property
    def ends_at(self):
        from datetime import datetime, timedelta
        return (datetime.combine(self.date, self.time) + timedelta(minutes=self.duration_min or 0)).time()

    @property
    def is_open(self):
        return self.status in (self.Status.REQUESTED, self.Status.CONFIRMED)

    @property
    def lines(self):
        return list(self.items.all())

    @property
    def services_label(self):
        names = [l.name for l in self.lines]
        return ", ".join(names) if names else "—"

    @property
    def total(self):
        return sum((l.price for l in self.lines), Decimal("0"))

    def set_services(self, services):
        """Replace what's booked. The appointment runs as long as all the services together."""
        self.items.all().delete()
        for i, svc in enumerate(services):
            BookingItem.objects.create(booking=self, service=svc, name=svc.name, price=svc.sale_price,
                                       duration_min=svc.duration_min or 0, position=i)
        self.duration_min = sum(s.duration_min or 0 for s in services) or 60
        self.save(update_fields=["duration_min"])

    @property
    def wa_confirm_link(self):
        from urllib.parse import quote
        what = self.services_label if self.lines else "your appointment"
        who = f" with {self.staff.name}" if self.staff else ""
        msg = (f"Hi {self.name}, {what}{who} at {self.vendor.brand_name} on {self.date:%a %d %b} at "
               f"{self.time:%H:%M} is confirmed. See you then!")
        return f"https://wa.me/{Vendor.normalize_msisdn(self.phone)}?text={quote(msg)}"


class BookingItem(models.Model):
    """One service on a booking. Name and price are kept as booked, even if the service changes later."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="items")
    service = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="booking_items")
    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    duration_min = models.PositiveSmallIntegerField(default=0)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return self.name


class Expense(models.Model):
    """Business expense recorded by the owner; feeds the profit & loss report."""
    class Category(models.TextChoices):
        PRODUCTS = "products", "Products & supplies"
        RENT = "rent", "Rent"
        SALARIES = "salaries", "Salaries & wages"
        UTILITIES = "utilities", "Utilities (power, water)"
        TRANSPORT = "transport", "Transport"
        MARKETING = "marketing", "Marketing"
        EQUIPMENT = "equipment", "Equipment & repairs"
        LICENCES = "licences", "Licences & fees"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="expenses")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses")
    date = models.DateField(default=timezone.localdate)
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.PRODUCTS)
    description = models.CharField(max_length=160)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_via = models.CharField(max_length=10, choices=Order.Method.choices, default=Order.Method.CASH)
    reference = models.CharField("Receipt / M-Pesa ref", max_length=60, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["vendor", "date"])]

    def __str__(self):
        return f"{self.date} {self.description} KES {self.amount}"


class InsightReport(models.Model):
    """Cached insights per vendor (one per generation). Newest is shown; regeneration is rate-limited."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="insight_reports")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True, related_name="insight_reports",
                               help_text="Blank means the whole business")
    days = models.PositiveSmallIntegerField(default=30)
    report = models.JSONField()
    snapshot = models.JSONField(default=dict)
    engine = models.CharField(max_length=40, default="rules")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class InsightQuestion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="insight_questions")
    asked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    question = models.CharField(max_length=600)
    answer = models.TextField()
    engine = models.CharField(max_length=40, default="rules")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
