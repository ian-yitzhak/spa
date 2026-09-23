from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LogoutView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .emails import send_code
from .forms import ChangePasswordForm, CodeForm, ForgotForm, LoginForm, SetPasswordForm, VendorSignupForm
from .models import OneTimeCode, User
from vendors.security import protect

PENDING_KEY = "pending_user_id"     # user awaiting email verification or login OTP
PENDING_PURPOSE = "pending_purpose"

TRUST_COOKIE = "bf_td"            # "this device already passed a code" — signed, HttpOnly
TRUST_DAYS = 28


def _trust_value(user):
    """Bound to the account and its current password, so a password change drops every trusted device."""
    import hashlib
    return f"{user.pk}:{hashlib.sha256(user.password.encode()).hexdigest()[:16]}"


def _device_trusted(request, user):
    """Has this browser passed a code for this account in the last 28 days?"""
    raw = request.COOKIES.get(TRUST_COOKIE)
    if not raw:
        return False
    from django.core import signing
    try:
        value = signing.loads(raw, salt="beautyflow.trusted-device", max_age=TRUST_DAYS * 86400)
    except signing.BadSignature:
        return False
    return value == _trust_value(user)


def _remember_device(response, user):
    from django.conf import settings as dj
    from django.core import signing
    response.set_cookie(TRUST_COOKIE, signing.dumps(_trust_value(user), salt="beautyflow.trusted-device"),
                        max_age=TRUST_DAYS * 86400, httponly=True, secure=not dj.DEBUG, samesite="Lax")
    return response


def _post_login_url(user):
    if user.is_admin_role:
        return reverse("ap_index")
    if getattr(user, "is_team", False):
        return reverse("pos_me")
    if getattr(user, "is_affiliate", False):
        return reverse("aff_home")
    return reverse("dashboard")


def _start_challenge(request, user, purpose):
    """Park the user id in the session and send the code; the email goes out behind the request."""
    request.session[PENDING_KEY] = user.pk
    request.session[PENDING_PURPOSE] = purpose
    send_code(user, purpose)
    return redirect("verify_email" if purpose == OneTimeCode.Purpose.VERIFY else "login_otp")


def _pending_user(request, purpose):
    uid = request.session.get(PENDING_KEY)
    if not uid or request.session.get(PENDING_PURPOSE) != purpose:
        return None
    return User.objects.filter(pk=uid, is_active=True).first()


def _finish_login(request, user):
    for k in (PENDING_KEY, PENDING_PURPOSE):
        request.session.pop(k, None)
    login(request, user)
    request.session.set_expiry(None)  # use SESSION_COOKIE_AGE (60 days)
    resp = redirect(request.session.pop("next", None) or _post_login_url(user))
    return _remember_device(resp, user)   # password alone gets them in for the next 28 days


# ── Sign up → verify email ────────────────────────────────────────────

@protect("signup", 5, 3600)
def signup(request):
    if request.user.is_authenticated:
        return redirect(_post_login_url(request.user))
    if request.GET.get("ref"):
        request.session["ref_code"] = request.GET["ref"][:12].upper()
    form = VendorSignupForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        code = request.COOKIES.get("bf_ref") or request.session.pop("ref_code", None)
        if code:
            from affiliates.models import Referral
            Referral.attach(user.vendor, code, request)
        return _start_challenge(request, user, OneTimeCode.Purpose.VERIFY)
    return render(request, "accounts/signup.html", {"form": form})


@protect("otp", 10, 600, require_turnstile=False)
def verify_email(request):
    user = _pending_user(request, OneTimeCode.Purpose.VERIFY)
    if user is None:
        return redirect("login")
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if OneTimeCode.verify(user, OneTimeCode.Purpose.VERIFY, form.cleaned_data["code"]):
            user.email_verified = True
            user.save(update_fields=["email_verified"])
            ref = getattr(getattr(user, "vendor", None), "referral", None)
            if ref:
                ref.check_qualified()
            if getattr(user, "vendor", None) and user.phone:
                from beautyflow.sms import send_sms
                send_sms(user.phone, f"Welcome to BeautyFlow, {user.first_name or 'there'}! Your business {user.vendor.brand_name} is live. Add your menu & photos: beautyflow.co.ke/dashboard/ — help: WhatsApp 0717183416")
            messages.success(request, "Email verified. Welcome to BeautyFlow — set up your business profile.")
            return _finish_login(request, user)
        form.add_error("code", "That code is wrong or has expired.")
    return render(request, "accounts/code.html", {
        "form": form, "email": user.email, "title": "Verify your email",
        "lead": "We sent a 6-digit code to", "resend_url": reverse("resend_code"),
    })


# ── Log in → OTP ──────────────────────────────────────────────────────

def _lock_key(email):
    return f"lock:{(email or '').strip().lower()}"


@protect("login", 10, 600)
def login_view(request):
    from django.conf import settings as dj
    from django.core.cache import cache
    if request.user.is_authenticated:
        return redirect(_post_login_url(request.user))
    email = request.POST.get("username", "")
    if request.method == "POST" and cache.get(_lock_key(email), 0) >= dj.LOGIN_LOCKOUT_ATTEMPTS:
        messages.error(request, f"Too many failed attempts. This account is locked for {dj.LOGIN_LOCKOUT_MINUTES} minutes.")
        return render(request, "accounts/login.html", {"form": LoginForm(request)})
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and not form.is_valid():
        k = _lock_key(email)
        n = cache.get(k, 0) + 1
        cache.set(k, n, dj.LOGIN_LOCKOUT_MINUTES * 60)
        if n >= dj.LOGIN_LOCKOUT_ATTEMPTS:
            from adminpanel.audit import log_event
            log_event(None, "login_locked", f"{email} locked after {n} failed attempts", request)
    if request.method == "POST" and form.is_valid():
        cache.delete(_lock_key(email))
        user = form.get_user()
        if request.GET.get("next"):
            request.session["next"] = request.GET["next"]
        if not user.email_verified:
            messages.info(request, "Please verify your email address first.")
            return _start_challenge(request, user, OneTimeCode.Purpose.VERIFY)
        if _device_trusted(request, user):
            return _finish_login(request, user)          # already verified on this device this week
        return _start_challenge(request, user, OneTimeCode.Purpose.LOGIN)
    return render(request, "accounts/login.html", {"form": form})


@protect("otp", 10, 600, require_turnstile=False)
def login_otp(request):
    user = _pending_user(request, OneTimeCode.Purpose.LOGIN)
    if user is None:
        return redirect("login")
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if OneTimeCode.verify(user, OneTimeCode.Purpose.LOGIN, form.cleaned_data["code"]):
            return _finish_login(request, user)
        form.add_error("code", "That code is wrong or has expired.")
    return render(request, "accounts/code.html", {
        "form": form, "email": user.email, "title": "Enter your login code",
        "lead": "For your security, we emailed a 6-digit code to", "resend_url": reverse("resend_code"),
    })


@require_POST
@protect("resend", 5, 600, require_turnstile=False)
def resend_code(request):
    purpose = request.session.get(PENDING_PURPOSE)
    user = _pending_user(request, purpose) if purpose else None
    if user is None:
        return redirect("login")
    if OneTimeCode.can_resend(user, purpose):
        # they asked for it, so wait for the send and tell them the truth
        if send_code(user, purpose, background=False):
            messages.success(request, f"A new code was sent to {user.email}.")
        else:
            messages.error(request, "We couldn't send the email right now. Please try again shortly.")
    else:
        messages.warning(request, "Please wait a minute before requesting another code.")
    return redirect({"verify": "verify_email", "reset": "reset_password"}.get(purpose, "login_otp"))


# ── Forgot / reset password ───────────────────────────────────────────

@protect("forgot", 5, 3600)
def forgot_password(request):
    form = ForgotForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.filter(email__iexact=form.cleaned_data["email"], is_active=True).first()
        if user:
            request.session[PENDING_KEY] = user.pk
            request.session[PENDING_PURPOSE] = OneTimeCode.Purpose.RESET
            send_code(user, OneTimeCode.Purpose.RESET)
        # Same response whether or not the email exists (no account enumeration)
        return render(request, "accounts/forgot_sent.html", {"email": form.cleaned_data["email"]})
    return render(request, "accounts/forgot.html", {"form": form})


@protect("otp", 10, 600, require_turnstile=False)
def reset_password(request):
    user = _pending_user(request, OneTimeCode.Purpose.RESET)
    if user is None:
        return redirect("forgot_password")
    code_form = CodeForm(request.POST or None)
    pw_form = SetPasswordForm(request.POST or None, user=user)
    if request.method == "POST" and code_form.is_valid() and pw_form.is_valid():
        if OneTimeCode.verify(user, OneTimeCode.Purpose.RESET, code_form.cleaned_data["code"]):
            user.set_password(pw_form.cleaned_data["password1"])
            user.email_verified = True
            user.save(update_fields=["password", "email_verified"])
            messages.success(request, "Password updated. You're now logged in.")
            return _finish_login(request, user)
        code_form.add_error("code", "That code is wrong or has expired.")
    return render(request, "accounts/reset.html", {"code_form": code_form, "pw_form": pw_form, "email": user.email})


@login_required
def change_password(request):
    form = ChangePasswordForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        request.user.set_password(form.cleaned_data["password1"])
        request.user.save(update_fields=["password"])
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, request.user)  # stay logged in
        messages.success(request, "Password changed.")
        return redirect("change_password")
    tpl = "dashboard/password.html" if getattr(request.user, "is_vendor", False) and hasattr(request.user, "vendor") else "accounts/password_plain.html"
    ctx = {"form": form}
    if tpl.startswith("dashboard"):
        ctx["vendor"] = request.user.vendor
    return render(request, tpl, ctx)


class UserLogoutView(LogoutView):
    pass
