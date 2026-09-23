from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from accounts.models import User
from vendors.forms import INPUT, IMAGE_EXT_VALIDATOR, clean_kenyan_mobile

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
    role = forms.ChoiceField(label="Role", choices=[("staff", "Staff — does services, earns commission, sees their own sales"),
                                                    ("cashier", "Cashier — runs the POS, takes payments, sees reports")],
                             initial="staff", widget=forms.RadioSelect)
    job_title = forms.CharField(label="Job title", max_length=60, required=False,
                                widget=forms.TextInput(attrs={"placeholder": "e.g. Senior stylist, Nail tech, Therapist"}))
    branch = forms.ModelChoiceField(label="Branch", queryset=Branch.objects.none(), required=False,
                                    help_text="Everything they do is filed under this branch.")
    email = forms.EmailField(label="Login email")
    phone = forms.CharField(max_length=20)
    password = forms.CharField(widget=forms.PasswordInput, required=False)
    national_id = forms.CharField(label="ID number", max_length=20, required=False)
    hired_on = forms.DateField(label="Start date", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    payout_phone = forms.CharField(label="M-Pesa number for pay", max_length=20, required=False,
                                   help_text="Leave blank to use their phone number.")
    commission_type = forms.ChoiceField(label="Commission", choices=Commission.choices, initial=Commission.PERCENT)
    commission_value = forms.DecimalField(label="Default rate", min_value=0, max_digits=10, decimal_places=2, initial=0,
                                          help_text="Percent of each service (e.g. 30) or KES per service (e.g. 200). "
                                                    "You can set a different rate on any service below.",
                                          widget=forms.NumberInput(attrs={"step": "any", "inputmode": "decimal"}))
    photo = forms.ImageField(required=False, validators=[IMAGE_EXT_VALIDATOR], widget=forms.FileInput(attrs={"accept": "image/*"}))
    bio = forms.CharField(label="Short bio", max_length=200, required=False,
                          widget=forms.TextInput(attrs={"placeholder": "Shown on your public page, e.g. 8 years in braids and locs"}))
    show_on_site = forms.BooleanField(label="Show on the public page", required=False, initial=True)

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
                                 "job_title": instance.job_title, "national_id": instance.national_id,
                                 "hired_on": instance.hired_on, "payout_phone": instance.payout_phone,
                                 "commission_type": instance.commission_type, "commission_value": instance.commission_value,
                                 "bio": instance.bio, "show_on_site": instance.show_on_site})
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

    def clean_payout_phone(self):
        return clean_kenyan_mobile(self.cleaned_data.get("payout_phone"), "M-Pesa number")

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
        for f in ("job_title", "national_id", "hired_on", "payout_phone", "commission_type", "commission_value", "bio"):
            setattr(st, f, d.get(f) if d.get(f) is not None else getattr(st, f))
        st.show_on_site = bool(d.get("show_on_site"))
        if d.get("photo"):
            st.photo = d["photo"]
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


class BookingForm(forms.ModelForm):
    """Owner, cashier or staff putting an appointment in the book."""
    class Meta:
        model = Booking
        fields = ["service", "staff", "date", "time", "duration_min", "name", "phone", "email", "source", "note"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "time": forms.TimeInput(attrs={"type": "time"}),
                   "duration_min": forms.NumberInput(attrs={"min": 5, "step": 5}),
                   "note": forms.TextInput(attrs={"placeholder": "Hair length, colour, allergies…"})}

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.vendor = vendor
        self.fields["service"].queryset = vendor.items.filter(is_available=True).order_by("name")
        self.fields["service"].required = True
        self.fields["staff"].queryset = vendor.staff.filter(is_active=True, role=Staff.Role.STAFF).select_related("user")
        self.fields["staff"].label_from_instance = lambda s: s.name + (f" · {s.job_title}" if s.job_title else "")
        self.fields["staff"].empty_label = "Anyone available"
        self.fields["duration_min"].required = False
        _style(self)

    def clean_phone(self):
        return clean_kenyan_mobile(self.cleaned_data["phone"], "phone number")

    def clean(self):
        d = super().clean()
        if not d.get("duration_min") and d.get("service"):
            d["duration_min"] = d["service"].duration_min
        staff, service = d.get("staff"), d.get("service")
        if staff and service and staff.service_links.exists() and not staff.service_links.filter(service=service).exists():
            self.add_error("staff", f"{staff.name} doesn't do {service.name}. Pick someone else or anyone available.")
        return d


class PublicBookingForm(forms.ModelForm):
    """A client booking from the public page."""
    class Meta:
        model = Booking
        fields = ["service", "staff", "date", "time", "name", "phone", "note"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "time": forms.TimeInput(attrs={"type": "time"}),
                   "note": forms.TextInput(attrs={"placeholder": "Anything we should know? Hair length, allergies…"})}
        labels = {"name": "Your name", "staff": "With", "note": "Note (optional)"}

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.vendor = vendor
        self.fields["service"].queryset = vendor.items.filter(is_available=True).order_by("category__order", "name")
        self.fields["service"].required = True
        self.fields["staff"].queryset = vendor.staff.filter(is_active=True, role=Staff.Role.STAFF, show_on_site=True).select_related("user")
        self.fields["staff"].label_from_instance = lambda s: s.name
        self.fields["staff"].empty_label = "Anyone available"
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
