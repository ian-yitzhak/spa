"""Thin Paystack client: start a checkout, verify it, and check webhook signatures."""
import hashlib
import hmac
import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)
API = "https://api.paystack.co"


class PaystackError(Exception):
    pass


def _headers():
    return {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}", "Content-Type": "application/json"}


def configured():
    return bool(settings.PAYSTACK_SECRET_KEY and settings.PAYSTACK_PUBLIC_KEY)


def initialize(*, email, amount, reference, callback_url, metadata=None):
    """Start a checkout. Returns the URL to send the customer to. Amounts go to Paystack in cents."""
    if not configured():
        raise PaystackError("Online payments are not set up yet. Contact support to pay.")
    body = {"email": email, "amount": int(round(float(amount) * 100)), "currency": "KES", "reference": reference,
            "callback_url": callback_url, "metadata": metadata or {}, "channels": ["card", "mobile_money"]}
    try:
        r = requests.post(f"{API}/transaction/initialize", json=body, headers=_headers(), timeout=30)
    except requests.RequestException as e:
        log.exception("Paystack initialize network error")
        raise PaystackError("Could not reach the payment provider. Try again.") from e
    data = _json(r)
    if r.status_code >= 400 or not data.get("status"):
        log.error("Paystack initialize %s: %s", r.status_code, r.text[:500])
        raise PaystackError(data.get("message") or "The payment could not be started. Try again.")
    url = (data.get("data") or {}).get("authorization_url")
    if not url:
        raise PaystackError("The payment provider did not return a checkout link.")
    return url, data


def verify(reference):
    """What Paystack says about a payment: {"state", "amount" (KES), "currency", "channel", "raw"}. None if unreachable."""
    try:
        r = requests.get(f"{API}/transaction/verify/{reference}", headers=_headers(), timeout=20)
    except requests.RequestException as e:
        log.warning("Paystack verify failed for %s: %s", reference, e)
        return None
    data = _json(r)
    if r.status_code == 404 or not data.get("status"):
        return {"state": "FAILED" if r.status_code == 404 else None, "amount": 0, "currency": "", "channel": "",
                "gateway_response": data.get("message", ""), "raw": data}
    d = data.get("data") or {}
    state = {"success": "COMPLETE", "failed": "FAILED", "abandoned": "PENDING", "reversed": "FAILED",
             "ongoing": "PROCESSING", "pending": "PROCESSING", "processing": "PROCESSING"}.get(d.get("status"), "PENDING")
    return {"state": state, "amount": (d.get("amount") or 0) / 100, "currency": d.get("currency", ""),
            "channel": d.get("channel", ""), "gateway_response": d.get("gateway_response") or "", "raw": data}


def signature_ok(body, signature):
    """Paystack signs every webhook with HMAC-SHA512 of the raw body, keyed with the secret key."""
    if not settings.PAYSTACK_SECRET_KEY or not signature:
        return False
    expected = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


def _json(r):
    try:
        return r.json()
    except ValueError:
        return {}
