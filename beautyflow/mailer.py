"""Send one-time codes from the dedicated OTP mailbox (reviews@…), everything else from the main one."""
from django.conf import settings
from django.core.mail import get_connection, send_mail


def otp_connection():
    if not settings.OTP_EMAIL_HOST_USER or "console" in settings.EMAIL_BACKEND or "locmem" in settings.EMAIL_BACKEND:
        return None  # default backend/connection
    return get_connection(host=settings.OTP_EMAIL_HOST, port=settings.EMAIL_PORT, username=settings.OTP_EMAIL_HOST_USER,
                          password=settings.OTP_EMAIL_HOST_PASSWORD, use_ssl=settings.EMAIL_USE_SSL, use_tls=settings.EMAIL_USE_TLS,
                          timeout=settings.EMAIL_TIMEOUT)


def send_otp_mail(subject, body, to):
    return send_mail(subject, body, settings.OTP_FROM_EMAIL, to, connection=otp_connection(), fail_silently=False)
