from django import forms
from django.core.validators import FileExtensionValidator
from django.forms import inlineformset_factory

from .models import Inquiry, MenuCategory, MenuItem, Offer, OpeningHours, Photo, Review, Vendor

INPUT = "w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-primary focus:ring-primary focus:outline-none"


MAX_IMAGE_MB = 5


def _check_images(form):
    for name, f in form.fields.items():
        if isinstance(f, forms.ImageField):
            up = form.cleaned_data.get(name)
            if up and hasattr(up, "size"):
                if up.size > MAX_IMAGE_MB * 1024 * 1024:
                    form.add_error(name, f"Image must be under {MAX_IMAGE_MB} MB.")
                ext = (getattr(up, "name", "") or "").rsplit(".", 1)[-1].lower()
                if hasattr(up, "content_type") and ext not in ALLOWED_IMAGE_EXT:
                    form.add_error(name, "Use a JPG, PNG or WebP image.")


ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "webp"}
IMAGE_EXT_VALIDATOR = FileExtensionValidator(sorted(ALLOWED_IMAGE_EXT), message="Use a JPG, PNG or WebP image.")


class StyledForm(forms.ModelForm):
    def clean(self):
        cleaned = super().clean()
        _check_images(self)
        return cleaned

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, f in self.fields.items():
            if isinstance(f, forms.ImageField):
                f.validators = [v for v in f.validators if getattr(v, "__name__", "") != "validate_image_file_extension" and v is not IMAGE_EXT_VALIDATOR] + [IMAGE_EXT_VALIDATOR]
            w = f.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "h-4 w-4 rounded border-gray-300 text-primary")
            elif "ck" not in (w.attrs.get("class") or ""):
                w.attrs.setdefault("class", INPUT)


def clean_kenyan_mobile(value, label="number"):
    from .models import Vendor
    if not value:
        return value
    d = Vendor.normalize_msisdn(value)
    if not d:
        raise forms.ValidationError(f"Enter a valid Kenyan mobile {label}, e.g. 0712 345 678, 0112 345 678 or +254712345678.")
    return "0" + d[3:]  # store as 07XX / 01XX


class VendorProfileForm(StyledForm):
    LOCKED = ("brand_name", "email")  # changing these changes the public URL / login identity — admin only

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.LOCKED:
            self.fields[name].disabled = True
            self.fields[name].help_text = "Contact support to change this."
            self.fields[name].widget.attrs["class"] = INPUT + " bg-gray-100 text-gray-500 cursor-not-allowed"
        self.fields["email"].label = "Business email"
        self.fields["tagline"].help_text = "One line that appears in Google results, e.g. “Knotless braids & gel nails in Kilimani”."
        self.fields["town"].help_text = "Neighbourhood or town, e.g. Westlands, Kilimani, Nyali. Used for “salons in …” pages."

    def clean_phone(self):
        return clean_kenyan_mobile(self.cleaned_data.get("phone"), "phone number")

    def clean_whatsapp(self):
        return clean_kenyan_mobile(self.cleaned_data.get("whatsapp"), "WhatsApp number")

    class Meta:
        model = Vendor
        fields = ["brand_name", "business_type", "tagline", "logo", "cover", "about", "email", "phone", "whatsapp",
                  "county", "town", "address", "map_link", "home_service", "accepts_bookings", "is_published"]
        widgets = {"logo": forms.FileInput(attrs={"accept": "image/*"}), "cover": forms.FileInput(attrs={"accept": "image/*"})}



class MenuCategoryForm(StyledForm):
    class Meta:
        model = MenuCategory
        fields = ["name", "order"]


class MenuItemForm(StyledForm):
    class Meta:
        model = MenuItem
        fields = ["name", "category", "net_price", "vat_mode", "duration_min", "discount_value", "discount_ends",
                  "price_on_request", "image", "description", "is_available"]
        widgets = {"vat_mode": forms.RadioSelect, "discount_ends": forms.DateInput(attrs={"type": "date"}),
                   "duration_min": forms.NumberInput(attrs={"min": "5", "step": "5", "inputmode": "numeric"})}

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = MenuCategory.objects.filter(vendor=vendor)
        self.fields["category"].label = "Category (Hair, Nails, Massage…)"
        self.fields["name"].label = "Service"
        self.fields["name"].widget.attrs["placeholder"] = "e.g. Knotless braids — mid-back"
        self.fields["discount_value"].required = False
        self.fields["discount_value"].label = "Discount (KES off)"
        self.fields["discount_value"].help_text = "Leave at 0 for no discount."
        self.fields["discount_ends"].help_text = "Optional. The discount stops after this date."
        self.fields["discount_value"].widget.attrs.update({"min": "0", "step": "any", "inputmode": "decimal"})
        self.fields["net_price"].required = False
        self.fields["net_price"].widget.attrs.update({"min": "0", "step": "1", "inputmode": "numeric"})
        self.fields["vat_mode"].widget.attrs["class"] = "h-4 w-4 text-primary"
        self.fields["price_on_request"].label = "Price on request — clients ask for a quote instead"

    def clean(self):
        data = super().clean()
        if "net_price" in self.fields and not data.get("price_on_request") and data.get("net_price") in (None, ""):
            self.add_error("net_price", "Enter a price, or tick “Price on request”.")
        if data.get("discount_value") in (None, ""):
            data["discount_value"] = 0
        price = data.get("net_price") or 0
        if data["discount_value"] and price and data["discount_value"] >= price:
            self.add_error("discount_value", "The discount must be less than the price.")
        # a discount is always KES off; no amount means no discount
        self.instance.discount_type = "amount" if data["discount_value"] else ""
        return data


class PhotoForm(StyledForm):
    class Meta:
        model = Photo
        fields = ["image", "caption"]


class OfferForm(StyledForm):
    class Meta:
        model = Offer
        fields = ["title", "details", "image", "starts", "ends", "is_active"]
        labels = {"title": "Offer", "details": "Details", "image": "Photo (optional)", "starts": "Starts (optional)", "ends": "Ends (optional)", "is_active": "Show this offer"}
        widgets = {"starts": forms.DateInput(attrs={"type": "date"}), "ends": forms.DateInput(attrs={"type": "date"}), "image": forms.FileInput(),
                   "title": forms.TextInput(attrs={"placeholder": "e.g. Mid-week glow — 20% off facials, Tue–Thu"}),
                   "details": forms.Textarea(attrs={"rows": 3, "placeholder": "What's included, days it applies, any conditions…"})}

    def clean(self):
        data = super().clean()
        if data.get("starts") and data.get("ends") and data["ends"] < data["starts"]:
            self.add_error("ends", "End date must be after the start date.")
        return data


class HoursForm(StyledForm):
    class Meta:
        model = OpeningHours
        fields = ["day", "opens", "closes", "closed"]
        widgets = {"opens": forms.TimeInput(attrs={"type": "time"}), "closes": forms.TimeInput(attrs={"type": "time"}),
                   "day": forms.HiddenInput()}


HoursFormSet = inlineformset_factory(Vendor, OpeningHours, form=HoursForm, extra=0, can_delete=False)


class InquiryForm(StyledForm):
    class Meta:
        model = Inquiry
        fields = ["kind", "name", "phone", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 3, "placeholder": "Which service, and what would you like to know?"})}


class ReviewForm(StyledForm):
    class Meta:
        model = Review
        fields = ["name", "email", "stars", "comment"]
        widgets = {"comment": forms.Textarea(attrs={"rows": 3})}
        labels = {"stars": "Rating", "email": "Email"}

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class ReviewCodeForm(forms.Form):
    code = forms.CharField(min_length=6, max_length=6, widget=forms.TextInput(attrs={"class": INPUT + " text-center text-xl tracking-[0.4em]", "inputmode": "numeric", "autocomplete": "one-time-code", "placeholder": "••••••"}))
