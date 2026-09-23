from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from accounts.models import User
from vendors.forms import INPUT, clean_kenyan_mobile

from .models import Booking, Branch, Commission, Expense, Staff, StaffPayout, StaffShift

CHECK = "h-4 w-4 rounded border-gray-300 text-primary"


def _style(form):
    for f in form.fields.values():
        if isinstance(f.widget, forms.CheckboxInput):
            f.widget.attrs.setdefault("class", CHECK)
        elif not isinstance(f.widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)):
            f.widget.attrs.setdefault("class", INPUT)


class StaffForm(forms.Form):
    """Create/edit a team member: who they are, their login, and what they earn.
    The services they do (and any rate of their own on each) come in from the service rows on the same page."""
    first_name = forms.CharField(label="Full name", max_length=120)
    role = forms.ChoiceField(label="Role", choices=[("staff", "Staff"), ("cashier", "Cashier")], initial="staff")
    job_title = forms.CharField(label="Job title", max_length=60, required=False,
                                widget=forms.TextInput(attrs={"placeholder": "e.g. Stylist"}))
    branch = forms.ModelChoiceField(label="Branch", queryset=Branch.objects.none(), required=False)
    email = forms.EmailField(label="Login email")
    phone = forms.CharField(max_length=20)
    password = forms.CharField(widget=forms.PasswordInput, required=False)
    hired_on = forms.DateField(label="Start date", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    commission_type = forms.ChoiceField(label="Commission", choices=Commission.choices, initial=Commission.PERCENT)
    commission_value = forms.DecimalField(label="Rate", min_value=0, max_digits=10, decimal_places=2, initial=0,
                                          widget=forms.NumberInput(attrs={"step": "any", "inputmode": "decimal"}))

    def __init__(self, *args, instance=None, vendor=None, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance              # the Staff row, or None for a new person
        self.vendor = vendor
        if vendor is not None:
            branches = vendor.branches.filter(is_active=True)
            self.fields["branch"].queryset = branches
            if not vendor.can_use_branches or len(branches) < 2:
                del self.fields["branch"]
            else:
                self.fields["branch"].empty_label = None
                self.fields["branch"].initial = branch or vendor.main_branch()
        if instance:
            u = instance.user
            self.initial.update({"first_name": u.first_name, "email": u.email, "phone": u.phone, "role": instance.role,
                                 "job_title": instance.job_title, "hired_on": instance.hired_on,
                                 "commission_type": instance.commission_type, "commission_value": instance.commission_value})
            if "branch" in self.fields and instance.branch_id:
                self.initial["branch"] = instance.branch_id
            self.fields["password"].help_text = "Leave blank to keep the current password."
        else:
            self.fields["password"].required = True
        _style(self)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        qs = User.objects.filter(email__iexact=email)
        if self.instance:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_phone(self):
        return clean_kenyan_mobile(self.cleaned_data["phone"], "phone number")

    def clean_password(self):
        pw = self.cleaned_data.get("password")
        if pw:
            validate_password(pw)
        return pw

    def clean(self):
        d = super().clean()
        if d.get("commission_type") == Commission.PERCENT and (d.get("commission_value") or 0) > 100:
            self.add_error("commission_value", "A percentage can't be more than 100.")
        return d

    def save(self, vendor):
        d = self.cleaned_data
        st = self.instance
        u = st.user if st else User(role=User.Role.TEAM, email_verified=True)
        u.first_name, u.email, u.username, u.phone = d["first_name"], d["email"], d["email"], d["phone"]
        u.role = User.Role.TEAM
        if d.get("password"):
            u.set_password(d["password"])
        u.save()
        if st is None:
            st = Staff(user=u, vendor=vendor, branch=vendor.main_branch())
        st.role = d["role"]
        st.branch = d.get("branch") or st.branch or vendor.main_branch()
        for f in ("job_title", "hired_on", "commission_type", "commission_value"):
            setattr(st, f, d.get(f) if d.get(f) is not None else getattr(st, f))
        st.save()
        return st


def save_staff_services(staff, post, services):
    """Service rows on the staff form: tick = they do it; a rate typed in overrides their default for that service."""
    from decimal import Decimal, InvalidOperation
    from .models import StaffService
    keep = set()
    for item in services:
        if post.get(f"svc:{item.pk}") != "on":
            continue
        keep.add(item.pk)
        kind = post.get(f"svc_type:{item.pk}") or ""
        raw = (post.get(f"svc_rate:{item.pk}") or "").strip()
        try:
            value = Decimal(raw) if raw else None
        except InvalidOperation:
            value = None
        if value is not None and (value < 0 or (kind == Commission.PERCENT and value > 100)):
            value = None
        if kind not in Commission.values or value is None:
            kind, value = "", None
        StaffService.objects.update_or_create(staff=staff, service=item,
                                              defaults={"commission_type": kind, "commission_value": value})
    staff.service_links.exclude(service_id__in=keep).delete()


class _ServicesField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name} — KES {obj.sale_price:,.0f} · {obj.duration_label}"


class BookingForm(forms.ModelForm):
    """Owner or cashier putting an appointment in the book: one or more services."""
    services = _ServicesField(queryset=None, widget=forms.CheckboxSelectMultiple,
                              error_messages={"required": "Pick at least one service."})

    class Meta:
        model = Booking
        fields = ["staff", "date", "time", "duration_min", "name", "phone", "email", "source", "note"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "time": forms.TimeInput(attrs={"type": "time"}),
                   "duration_min": forms.NumberInput(attrs={"min": 5, "step": 5}),
                   "note": forms.TextInput(attrs={"placeholder": "Hair length, colour, allergies…"})}
        labels = {"duration_min": "Minutes (blank = add up the services)"}

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.vendor = vendor
        self.fields["services"].queryset = vendor.items.filter(is_available=True, price_on_request=False).order_by("category__order", "name")
        if self.instance.pk:
            self.initial.setdefault("services", [l.service_id for l in self.instance.items.all() if l.service_id])
        self.fields["staff"].queryset = vendor.staff.filter(is_active=True, role=Staff.Role.STAFF).select_related("user")
        self.fields["staff"].label_from_instance = lambda s: s.name + (f" · {s.job_title}" if s.job_title else "")
        self.fields["staff"].empty_label = "Anyone available"
        self.fields["duration_min"].required = False
        _style(self)

    def clean_phone(self):
        return clean_kenyan_mobile(self.cleaned_data["phone"], "phone number")

    def clean(self):
        d = super().clean()
        staff, services = d.get("staff"), list(d.get("services") or [])
        if staff and services and staff.service_links.exists():
            missing = [s.name for s in services if not staff.service_links.filter(service=s).exists()]
            if missing:
                self.add_error("staff", f"{staff.name} doesn't do {', '.join(missing)}. Pick someone else or anyone available.")
        return d

    def save(self, commit=True):
        b = super().save(commit=commit)
        if commit:
            services = list(self.cleaned_data["services"])
            b.set_services(services)
            if self.cleaned_data.get("duration_min"):
                b.duration_min = self.cleaned_data["duration_min"]
                b.save(update_fields=["duration_min"])
        return b


class PublicBookingForm(forms.ModelForm):
    """A client booking from the public page. The services come from the booking cart on the page."""
    services = forms.ModelMultipleChoiceField(queryset=None, widget=forms.MultipleHiddenInput,
                                              error_messages={"required": "Add at least one service to your booking."})

    class Meta:
        model = Booking
        fields = ["date", "time", "name", "phone", "note"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "time": forms.TimeInput(attrs={"type": "time"}),
                   "note": forms.TextInput(attrs={"placeholder": "Anything we should know? Hair length, allergies…"})}
        labels = {"name": "Your name", "note": "Note (optional)"}

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.vendor = vendor
        self.fields["services"].queryset = vendor.items.filter(is_available=True, price_on_request=False)
        _style(self)

    def clean_phone(self):
        return clean_kenyan_mobile(self.cleaned_data["phone"], "phone number")

    def clean_date(self):
        d = self.cleaned_data["date"]
        if d < timezone.localdate():
            raise forms.ValidationError("Pick today or a future date.")
        return d


class StaffShiftForm(forms.ModelForm):
    class Meta:
        model = StaffShift
        fields = ["staff", "date", "starts", "ends", "status", "note"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "starts": forms.TimeInput(attrs={"type": "time"}),
                   "ends": forms.TimeInput(attrs={"type": "time"}), "note": forms.TextInput(attrs={"placeholder": "Optional"})}
        labels = {"starts": "From", "ends": "To"}

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["staff"].queryset = vendor.staff.filter(is_active=True).select_related("user")
        self.fields["staff"].label_from_instance = lambda s: s.name
        self.fields["staff"].label = "Who"
        _style(self)


class PayoutForm(forms.Form):
    method = forms.ChoiceField(choices=StaffPayout.Method.choices, initial=StaffPayout.Method.MPESA)
    reference = forms.CharField(label="M-Pesa / bank ref", max_length=60, required=False)
    bonus = forms.DecimalField(label="Bonus / tips", min_value=0, required=False, initial=0,
                               widget=forms.NumberInput(attrs={"step": "any", "inputmode": "decimal"}))
    deduction = forms.DecimalField(label="Deductions / advances", min_value=0, required=False, initial=0,
                                   widget=forms.NumberInput(attrs={"step": "any", "inputmode": "decimal"}))
    note = forms.CharField(max_length=200, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["date", "category", "description", "amount", "paid_via", "reference"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "amount": forms.NumberInput(attrs={"step": "1", "min": "0", "inputmode": "decimal"}),
                   "description": forms.TextInput(attrs={"placeholder": "e.g. Braiding hair and relaxer from the wholesaler"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)
