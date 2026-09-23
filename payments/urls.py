from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/pay/", views.start, name="pay_start"),
    path("dashboard/pay/done/", views.callback, name="pay_callback"),
    path("dashboard/pay/<uuid:pk>/status/", views.status, name="pay_status"),
    path("webhooks/paystack/", views.paystack_webhook, name="paystack_webhook"),
]
