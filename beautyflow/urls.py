from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("ckeditor5/", include("django_ckeditor_5.urls")),
    path("admin/", include("adminpanel.urls")),
    path("", include("payments.urls")),
    path("pos/", include("pos.urls")),
    path("", include("affiliates.urls")),
    path("r/<uuid:pk>/", __import__("pos.views", fromlist=["public_receipt"]).public_receipt, name="pos_public_receipt"),
    path("r/<uuid:pk>/pdf/", __import__("pos.views", fromlist=["public_receipt_pdf"]).public_receipt_pdf, name="pos_public_receipt_pdf"),
    path("", include("accounts.urls")),
    path("", include("vendors.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "BeautyFlow (raw DB admin)"

handler404 = "vendors.views.page_not_found"
handler500 = "vendors.views.server_error"
