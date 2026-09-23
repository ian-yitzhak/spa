"""Advanta / QuickSMS. Best-effort: never raises; dry-run (log only) when keys are missing."""
import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)
ENDPOINT = "https://quicksms.advantasms.com/api/services/sendotp"


def send_sms(phone, message):
    from vendors.models import Vendor
    msisdn = Vendor.normalize_msisdn(phone)
    if not msisdn:
        return False
    key, pid, code = settings.ADVANTA_API_KEY, settings.ADVANTA_PARTNER_ID, settings.ADVANTA_SHORTCODE
    if not (key and pid and code):
        log.info("SMS dry-run to +%s: %s", msisdn, message)
        return False
    try:
        r = requests.post(ENDPOINT, json={"apikey": key, "partnerID": pid, "shortcode": code, "mobile": f"+{msisdn}", "message": message[:460]}, timeout=10)
        ok = r.status_code < 400
        if not ok:
            log.warning("SMS failed %s: %s", r.status_code, r.text[:200])
        return ok
    except Exception:
        log.exception("SMS error")
        return False
