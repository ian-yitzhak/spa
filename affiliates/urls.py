from django.urls import path

from . import views

urlpatterns = [
    path("join/<str:code>/", views.join, name="aff_join"),
    path("affiliate/", views.home, name="aff_home"),
    path("affiliate/signups/", views.signups, name="aff_signups"),
    path("affiliate/profile/", views.profile, name="aff_profile"),
    path("affiliate/payment-details/", views.payout, name="aff_payout"),
    path("admin/affiliates/", views.admin_list, name="ap_affiliates"),
    path("admin/affiliates/<uuid:pk>/", views.admin_detail, name="ap_affiliate"),
    path("admin/referrals/", views.admin_referrals, name="ap_referrals"),
    path("admin/referrals/bulk/", views.admin_bulk, name="ap_referrals_bulk"),
]
