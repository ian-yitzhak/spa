from django import forms
from django.contrib.auth.password_validation import validate_password

from accounts.models import User
from vendors.forms import INPUT, clean_kenyan_mobile

from .models import Affiliate


class AffiliateForm(forms.Form):
    """Admin creates/edits an affiliate: name, phone, email, password."""
    first_name = forms.CharField(label="Name", max_length=120)
    email = forms.EmailField()
    phone = forms.CharField(label="Phone / M-Pesa number", max_length=20)
    password = forms.CharField(widget=forms.PasswordInput, required=False)
    notes = forms.CharField(required=False, max_length=200)

    def __init__(self, *args, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        if instance:
            u = instance.user
            self.fields["first_name"].initial, self.fields["email"].initial, self.fields["phone"].initial, self.fields["notes"].initial = u.first_name, u.email, u.phone, instance.notes
            self.fields["password"].help_text = "Leave blank to keep the current password."
        else:
            self.fields["password"].required = True
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", INPUT)

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

    def save(self):
        d = self.cleaned_data
        u = self.instance.user if self.instance else User(role=User.Role.AFFILIATE, email_verified=True)
        u.first_name, u.email, u.username, u.phone, u.role = d["first_name"], d["email"], d["email"], d["phone"], User.Role.AFFILIATE
        if d.get("password"):
            u.set_password(d["password"])
        u.save()
        aff = self.instance or Affiliate(user=u)
        aff.notes = d.get("notes", "")
        aff.mpesa_number = d["phone"]
        aff.save()
        return aff


class AffiliateProfileForm(forms.Form):
    first_name = forms.CharField(label="Name", max_length=120)
    phone = forms.CharField(label="Phone", max_length=20)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", INPUT)

    def clean_phone(self):
        return clean_kenyan_mobile(self.cleaned_data["phone"], "phone number")



class PayoutForm(forms.ModelForm):
    class Meta:
        model = Affiliate
        fields = ["payout_method", "mpesa_number", "mpesa_name", "bank_name", "bank_account_name", "bank_account_number", "bank_branch"]
        widgets = {"payout_method": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for n, f in self.fields.items():
            if n != "payout_method":
                f.widget.attrs.setdefault("class", INPUT)

    def clean_mpesa_number(self):
        v = self.cleaned_data.get("mpesa_number")
        return clean_kenyan_mobile(v, "M-Pesa number") if v else v

    def clean(self):
        c = super().clean()
        if c.get("payout_method") == "mpesa":
            if not c.get("mpesa_number"):
                self.add_error("mpesa_number", "Enter the M-Pesa number to pay you on.")
            if not c.get("mpesa_name"):
                self.add_error("mpesa_name", "Enter the name registered on that M-Pesa line.")
        else:
            for n in ("bank_name", "bank_account_name", "bank_account_number"):
                if not c.get(n):
                    self.add_error(n, "Required for bank payouts.")
        return c
