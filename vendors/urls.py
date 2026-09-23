from django.urls import path, re_path

from django.contrib.sitemaps.views import sitemap

from . import client_views, kit_views, seo_views, views
from .models import ALL_TYPES, BUSINESS_TYPES

PLURAL = "|".join([ALL_TYPES[4]] + [r[4] for r in BUSINESS_TYPES])
SINGULAR = "|".join(r[2] for r in BUSINESS_TYPES)

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("deals/", views.deals, name="deals"),
    path("about/", views.about, name="about"),
    path("features/", views.features, name="features"),
    path("pricing/", views.pricing, name="pricing"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/profile/", views.profile, name="dashboard_profile"),
    path("dashboard/hours/", views.hours, name="dashboard_hours"),
    path("dashboard/menu/", views.menu, name="dashboard_menu"),
    path("dashboard/menu/new/", views.item_form, name="item_new"),
    path("dashboard/menu/menu.pdf", views.menu_pdf, name="menu_pdf"),
    path("dashboard/menu/<uuid:pk>/", views.item_form, name="item_edit"),
    path("dashboard/menu/<uuid:pk>/delete/", views.item_delete, name="item_delete"),
    path("dashboard/menu/<uuid:pk>/toggle/", views.item_toggle, name="item_toggle"),
    path("dashboard/menu/category/<uuid:pk>/delete/", views.category_delete, name="category_delete"),
    path("dashboard/gallery/", views.gallery, name="dashboard_gallery"),
    path("dashboard/gallery/<uuid:pk>/delete/", views.photo_delete, name="photo_delete"),
    path("dashboard/offers/", views.offers, name="dashboard_offers"),
    path("dashboard/offers/<uuid:pk>/edit/", views.offers, name="offer_edit"),
    path("dashboard/offers/<uuid:pk>/delete/", views.offer_delete, name="offer_delete"),
    path("dashboard/offers/<uuid:pk>/toggle/", views.offer_toggle, name="offer_toggle"),
    path("dashboard/reviews/", views.reviews, name="dashboard_reviews"),
    path("dashboard/upgrade/", views.upgrade, name="dashboard_upgrade"),
    path("dashboard/share/", views.share, name="dashboard_share"),
    path("dashboard/customers/", client_views.customers, name="dashboard_customers"),
    path("dashboard/customers/export.csv", client_views.customers_export, name="customers_export"),
    path("dashboard/inquiries/", client_views.inquiries, name="dashboard_inquiries"),
    path("dashboard/inquiries/<uuid:pk>/<str:action>/", client_views.inquiry_action, name="inquiry_action"),
    path("dashboard/inquiries/new-count/", client_views.inquiry_new_count, name="inquiry_new_count"),
    path("m/<str:token>/", views.menu_by_token, name="menu_by_token"),
    path("dashboard/kit/", kit_views.kit, name="dashboard_kit"),
    path("dashboard/kit/<slug:kind>.png", kit_views.kit_image, name="kit_image"),
    path("dashboard/payments/", views.payments_page, name="dashboard_payments"),
    # SEO directory
    path("sitemap.xml", sitemap, {"sitemaps": seo_views.SITEMAPS}, name="sitemap"),
    path("healthz/", seo_views.healthz, name="healthz"),
    path("robots.txt", seo_views.robots, name="robots"),
    path("services/", seo_views.services_index, name="services_index"),
    path("services/<slug:tag_slug>/", seo_views.service_tag, name="service_tag"),
    path("services/<slug:tag_slug>/<slug:loc_slug>/", seo_views.service_tag, name="service_tag_in"),
    path("price-lists/", seo_views.price_lists, name="price_lists"),
    path("for-business/<slug:page>/", seo_views.owner_page, name="owner_page"),
    re_path(rf"^(?P<type_plural>{PLURAL})/$", seo_views.types_index, name="types_index"),
    re_path(rf"^(?P<type_plural>{PLURAL})/(?P<loc_slug>[-a-z0-9]+)/$", seo_views.places_in, name="places_in"),
    # Vendor pages (canonical: /restaurant/<slug>/)
    re_path(rf"^(?P<type_slug>{SINGULAR})/(?P<slug>[-\w]+)/$", views.vendor_detail, name="vendor_detail"),
    re_path(rf"^(?P<type_slug>{SINGULAR})/(?P<slug>[-\w]+)/menu/$", views.vendor_menu_only, name="vendor_menu_only"),
    re_path(rf"^(?P<type_slug>{SINGULAR})/(?P<slug>[-\w]+)/qr/$", views.vendor_qr_card, name="vendor_qr_card"),
    re_path(rf"^(?P<type_slug>{SINGULAR})/(?P<slug>[-\w]+)/qr\.png$", views.vendor_qr_png, name="vendor_qr_png"),
    re_path(rf"^(?P<type_slug>{SINGULAR})/(?P<slug>[-\w]+)/og\.jpg$", views.vendor_og_image, name="vendor_og_image"),
    re_path(rf"^(?P<type_slug>{SINGULAR})/(?P<slug>[-\w]+)/contact/$", views.reveal_contact, name="reveal_contact"),
    re_path(rf"^(?P<type_slug>{SINGULAR})/(?P<slug>[-\w]+)/inquire/$", client_views.inquire, name="menu_inquire"),
    re_path(rf"^(?P<type_slug>{SINGULAR})/(?P<slug>[-\w]+)/ask/$", views.vendor_faq, name="vendor_faq"),
    re_path(rf"^(?P<type_slug>{SINGULAR})/(?P<slug>[-\w]+)/reserve/$", client_views.reserve, name="reserve"),
    re_path(rf"^(?P<type_slug>{SINGULAR})/(?P<slug>[-\w]+)/review/$", views.add_review, name="add_review"),
    re_path(rf"^(?P<type_slug>{SINGULAR})/(?P<slug>[-\w]+)/review/(?P<pk>[0-9a-f-]{{36}})/verify/$", views.verify_review, name="verify_review"),
    path("<slug:slug>/", seo_views.vendor_redirect, name="vendor_legacy"),
]
