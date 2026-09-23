from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("created_at", "vendor", "amount", "state", "api_ref", "channel", "applied_at")
    list_filter = ("state",)
    search_fields = ("vendor__brand_name", "api_ref")
    readonly_fields = ("raw",)
