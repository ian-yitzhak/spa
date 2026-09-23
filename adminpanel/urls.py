from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="ap_index"),
    path("vendors/", views.vendors, name="ap_vendors"),
    path("vendors/<uuid:pk>/", views.vendor_detail, name="ap_vendor"),
    path("vendors/<uuid:pk>/<str:action>/", views.vendor_action, name="ap_vendor_action"),
    path("admins/", views.admins, name="ap_admins"),
    path("admins/new/", views.admin_form, name="ap_admin_new"),
    path("admins/<int:pk>/", views.admin_form, name="ap_admin_edit"),
    path("admins/<int:pk>/delete/", views.admin_delete, name="ap_admin_delete"),
    path("inquiries/", views.inquiries, name="ap_inquiries"),
    path("reviews/", views.reviews, name="ap_reviews"),
    path("reviews/<uuid:pk>/<str:action>/", views.review_action, name="ap_review_action"),
    path("payments/", views.payments, name="ap_payments"),
    path("sales/", views.sales, name="ap_sales"),
    path("backups/", views.backups, name="ap_backups"),
    path("settings/", views.settings_view, name="ap_settings"),
    path("security/", views.security, name="ap_security"),
]
