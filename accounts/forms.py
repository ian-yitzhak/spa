from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils.text import slugify

from vendors.models import Vendor

from .models import User

INPUT = "w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-primary focus:ring-primary focus:outline-none"


class VendorSignupForm(UserCreationForm):
    """The short version: who you are, what the place is called, how to reach you. The rest is the profile page."""
    name = forms.CharField(label="Your name", max_length=120)
    brand_name = forms.CharField(label="Brand / business name", max_length=120)
    phone = forms.CharField(label="Phone / WhatsApp", max_length=20)
    agree = forms.BooleanField(label="I agree to the Terms of use and Privacy policy", error_messages={"required": "You must agree to the terms to create an account."})

    class Meta:
        model = User
        fields = ("name", "brand_name", "email", "phone", "password1", "password2", "agree")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, f in self.fields.items():
            if name != "agree":
                f.widget.attrs.setdefault("class", INPUT)
        self.fields["agree"].widget.attrs["class"] = "h-4 w-4 rounded border-gray-300 text-primary"
        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""
        self.fields["password2"].label = "Confirm password"

    def clean_phone(self):
        from vendors.forms import clean_kenyan_mobile
        return clean_kenyan_mobile(self.cleaned_data.get("phone"), "phone number")

    def clean_brand_name(self):
        name = self.cleaned_data["brand_name"]
        if Vendor.objects.filter(slug=slugify(name)).exists():
            raise forms.ValidationError("That business name is already taken.")
        return name

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["name"]
        user.phone = self.cleaned_data["phone"]
        user.role = User.Role.VENDOR
        user.email_verified = False
        from django.utils import timezone
        user.terms_accepted_at = timezone.now()
        if commit:
            user.save()
            Vendor.objects.create(
                owner=user,
                brand_name=self.cleaned_data["brand_name"],
                email=user.email,
                phone=user.phone,
                whatsapp=user.phone,
                is_published=False,        # goes public once the profile is filled in
            )
        return user


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", INPUT)


class CodeForm(forms.Form):
    code = forms.CharField(
        label="6-digit code", min_length=6, max_length=6,
        widget=forms.TextInput(attrs={
            "class": INPUT + " text-center text-2xl tracking-[0.5em] font-semibold",
            "inputmode": "numeric", "autocomplete": "one-time-code", "autofocus": True, "placeholder": "••••••",
        }),
    )

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if not code.isdigit():
            raise forms.ValidationError("Enter the 6 digits from your email.")
        return code


class ForgotForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": INPUT, "placeholder": "you@example.com", "autofocus": True}))


class SetPasswordForm(forms.Form):
    password1 = forms.CharField(label="New password", widget=forms.PasswordInput(attrs={"class": INPUT}))
    password2 = forms.CharField(label="Confirm new password", widget=forms.PasswordInput(attrs={"class": INPUT}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        from django.contrib.auth.password_validation import validate_password
        c = super().clean()
        if c.get("password1") and c.get("password2"):
            if c["password1"] != c["password2"]:
                self.add_error("password2", "Passwords don't match.")
            else:
                validate_password(c["password1"], self.user)
        return c


class ChangePasswordForm(SetPasswordForm):
    current = forms.CharField(label="Current password", widget=forms.PasswordInput(attrs={"class": INPUT}))
    field_order = ["current", "password1", "password2"]

    def clean_current(self):
        if not self.user.check_password(self.cleaned_data["current"]):
            raise forms.ValidationError("Current password is wrong.")
        return self.cleaned_data["current"]
