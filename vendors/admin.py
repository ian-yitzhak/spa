from django.contrib import admin
from django.utils import timezone

from .models import Inquiry, MenuCategory, MenuItem, Offer, OpeningHours, Photo, Review, SiteSettings, Vendor


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class MenuItemInline(admin.TabularInline):
    model = MenuItem
    extra = 0
    fields = ("name", "category", "price", "is_available")


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("brand_name", "owner", "phone", "town", "plan", "premium_expires_at", "is_approved", "is_published", "created_at")
    list_filter = ("plan", "is_approved", "is_published")
    search_fields = ("brand_name", "owner__email", "phone", "town")
    prepopulated_fields = {"slug": ("brand_name",)}
    actions = ["make_premium", "make_free", "approve"]
    inlines = [MenuItemInline]

    @admin.action(description="Premium: add 1 month (payment received)")
    def make_premium(self, request, queryset):
        for v in queryset:
            v.extend_premium()

    @admin.action(description="Downgrade to Free")
    def make_free(self, request, queryset):
        queryset.update(plan=Vendor.Plan.FREE)

    @admin.action(description="Approve vendors")
    def approve(self, request, queryset):
        queryset.update(is_approved=True)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("name", "vendor", "category", "price", "is_available")
    list_filter = ("vendor",)
    search_fields = ("name", "vendor__brand_name")


@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "vendor", "phone", "is_read", "created_at")
    list_filter = ("kind", "is_read")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("vendor", "name", "stars", "is_approved", "created_at")
    list_filter = ("stars", "is_approved")
    actions = ["approve", "hide"]

    @admin.action(description="Approve")
    def approve(self, request, queryset):
        queryset.update(is_approved=True)

    @admin.action(description="Hide")
    def hide(self, request, queryset):
        queryset.update(is_approved=False)


admin.site.register(MenuCategory)
admin.site.register(Photo)
admin.site.register(OpeningHours)
admin.site.register(Offer)
