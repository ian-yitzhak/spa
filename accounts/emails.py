import logging

from django.conf import settings

from beautyflow.mailer import send_otp_mail

from .models import OneTimeCode

log = logging.getLogger(__name__)


def _deliver(subject, body, email, purpose):
    try:
        send_otp_mail(subject, body, [email])
    except Exception:
        log.exception("Failed to send %s code to %s", purpose, email)


def send_code(user, purpose, background=True):
    """Issue and email a code. The SMTP round trip takes about a second, so by default it happens
    off the request and the code page opens straight away."""
    otp = OneTimeCode.issue(user, purpose)
    if purpose == OneTimeCode.Purpose.VERIFY:
        subject = f"{otp.code} is your BeautyFlow verification code"
        intro = "Thanks for joining BeautyFlow. Enter this code to verify your email address:"
    elif purpose == OneTimeCode.Purpose.RESET:
        subject = f"{otp.code} is your BeautyFlow password reset code"
        intro = "Use this code to set a new password for your BeautyFlow account:"
    else:
        subject = f"{otp.code} is your BeautyFlow login code"
        intro = "Use this code to finish logging in to BeautyFlow:"
    body = (
        f"Hi {user.first_name or user.email},\n\n{intro}\n\n    {otp.code}\n\n"
        f"It expires in {settings.OTP_EXPIRY_MINUTES} minutes. If you didn't request this, you can ignore this email.\n\n"
        f"— BeautyFlow · {settings.SITE_URL}"
    )
    if background:
        import threading
        threading.Thread(target=_deliver, args=(subject, body, user.email, purpose), daemon=True).start()
        return otp
    try:
        send_otp_mail(subject, body, [user.email])
    except Exception:
        log.exception("Failed to send %s code to %s", purpose, user.email)
        return None
    return otp
