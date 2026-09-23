from django import forms

from accounts.models import User
from vendors.forms import INPUT, StyledForm
from vendors.models import SiteSettings, Vendor


class AdminUserForm(StyledForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False,
                               help_text="Leave blank to keep the current password.")

    class Meta:
        model = User
        fields = ["first_name", "email", "phone", "password", "is_active"]
        labels = {"first_name": "Name"}

    def clean_password(self):
        pw = self.cleaned_data.get("password")
        if not self.instance.pk and not pw:
            raise forms.ValidationError("Password is required for a new admin.")
        return pw

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email
        user.role = User.Role.ADMIN
        user.is_staff = True
        user.email_verified = True
        if self.cleaned_data["password"]:
            user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class VendorAdminForm(StyledForm):
    """Admin edit of a vendor + its owner account."""
    owner_name = forms.CharField(label="Owner name", max_length=120)
    owner_email = forms.EmailField(label="Owner email")
    owner_phone = forms.CharField(label="Owner phone", max_length=20)
    new_password = forms.CharField(widget=forms.PasswordInput, required=False, label="Reset password",
                                   help_text="Leave blank to keep.")

    class Meta:
        model = Vendor
        fields = ["brand_name", "plan", "premium_expires_at", "pos_expires_at", "is_approved", "is_published", "town", "phone", "whatsapp", "email"]
        widgets = {"premium_expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                   "pos_expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        o = self.instance.owner
        self.fields["owner_name"].initial = o.first_name
        self.fields["owner_email"].initial = o.email
        self.fields["owner_phone"].initial = o.phone

    def clean_owner_email(self):
        email = self.cleaned_data["owner_email"]
        if User.objects.filter(email=email).exclude(pk=self.instance.owner_id).exists():
            raise forms.ValidationError("Another account already uses this email.")
        return email

    def save(self, commit=True):
        v = super().save(commit=commit)
        o = v.owner
        o.first_name = self.cleaned_data["owner_name"]
        o.email = o.username = self.cleaned_data["owner_email"]
        o.phone = self.cleaned_data["owner_phone"]
        if self.cleaned_data["new_password"]:
            o.set_password(self.cleaned_data["new_password"])
        o.save()
        return v


class SiteSettingsForm(StyledForm):
    class Meta:
        model = SiteSettings
        fields = ["premium_fee", "pos_fee", "affiliate_fee", "free_menu_limit", "free_photo_limit", "branches_open",
                  "payment_instructions", "support_whatsapp", "support_email"]
        widgets = {"payment_instructions": forms.Textarea(attrs={"rows": 4})}


class ManualActivationForm(forms.Form):
    PERIODS = [(1, "1 month"), (3, "3 months"), (6, "6 months"), (12, "12 months")]
    product = forms.ChoiceField(choices=[("premium", "Premium listing"), ("pos", "POS module")])
    branch = forms.ChoiceField(required=False, label="Branch (POS only)", help_text="Which outlet this month is for.")
    months = forms.TypedChoiceField(choices=PERIODS, coerce=int, initial=1, label="Period")
    until = forms.DateField(required=False, label="…or set exact expiry date", widget=forms.DateInput(attrs={"type": "date"}),
                            help_text="Overrides the period if filled.")
    amount = forms.DecimalField(required=False, max_digits=10, decimal_places=2, label="Amount received (KES)", help_text="Leave blank to use the standard fee × period.")
    note = forms.CharField(required=False, max_length=200, widget=forms.TextInput(attrs={"placeholder": "e.g. M-Pesa QAB12XYZ received 13 Sep, or free trial"}))

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        branches = list(vendor.branches.filter(is_active=True)) if vendor is not None else []
        if len(branches) > 1:
            self.fields["branch"].choices = [(str(b.pk), f"{b.name}{f' · {b.location}' if b.location else ''}") for b in branches]
        else:
            del self.fields["branch"]
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", INPUT)
