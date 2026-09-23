"""Cloudflare Turnstile verification + simple per-IP rate limiting for public forms."""
import logging
from functools import wraps

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import render

log = logging.getLogger(__name__)
SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return (xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")) or "0.0.0.0"


def turnstile_ok(request):
    """True if the request carries a valid Turnstile token (or Turnstile is not configured)."""
    if not settings.TURNSTILE_SECRET_KEY:
        return True
    token = request.POST.get("cf-turnstile-response") or request.headers.get("X-Turnstile-Token", "")
    if not token:
        return False
    try:
        r = requests.post(SITEVERIFY, data={"secret": settings.TURNSTILE_SECRET_KEY, "response": token, "remoteip": client_ip(request)}, timeout=8)
        data = r.json()
    except Exception:
        log.exception("Turnstile siteverify failed")
        return False
    if not data.get("success"):
        log.info("Turnstile rejected: %s", data.get("error-codes"))
    return bool(data.get("success"))


def rate_limited(request, key, limit, window_seconds):
    """Increment a per-IP counter; True when over the limit."""
    k = f"rl:{key}:{client_ip(request)}"
    try:
        n = cache.get(k, 0) + 1
        cache.set(k, n, window_seconds) if n == 1 else cache.incr(k)
    except Exception:
        return False
    return n > limit


def protect(key, limit, window_seconds, require_turnstile=True):
    """Decorator for POST views: rate limit + Turnstile. Human-readable error via HTMX-aware response."""
    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method == "POST":
                if rate_limited(request, key, limit, window_seconds):
                    return _reject(request, "Too many attempts. Please wait a few minutes and try again.", 429)
                if require_turnstile and not turnstile_ok(request):
                    return _reject(request, "Please complete the “I'm human” check and try again.", 400)
            return view(request, *args, **kwargs)
        return wrapper
    return deco


def _reject(request, message, status):
    if getattr(request, "htmx", False):
        return HttpResponse(f'<div class="rounded-lg bg-red-50 p-3 text-sm text-red-700">{message}</div>', status=200)
    return render(request, "vendors/blocked.html", {"message": message}, status=status)
