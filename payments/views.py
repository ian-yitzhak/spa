import json
import logging
import secrets
import time
from decimal import Decimal

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from vendors.models import SiteSettings
from vendors.views import vendor_required

from . import paystack
from .models import Payment

log = logging.getLogger(__name__)


def settle(p, res):
    """Apply what Paystack reported, refusing a "success" that paid less than we asked for or in another currency."""
    if not res or not res.get("state"):
        return
    if res["state"] == Payment.State.COMPLETE:
        paid = Decimal(str(res.get("amount") or 0))
        if res.get("currency") != "KES" or paid + Decimal("0.5") < p.amount:
            from adminpanel.audit import log_event
            log_event(None, "payment_amount_mismatch", f"{p.api_ref}: paid {res.get('currency')} {paid}, expected KES {p.amount}")
            p.apply_state(Payment.State.FAILED, {**res, "failed_reason": f"Received {res.get('currency')} {paid}, expected KES {p.amount}. Contact support."})
            return
        p.apply_state(Payment.State.COMPLETE, res)
    elif res["state"] == Payment.State.FAILED:
        p.apply_state(Payment.State.FAILED, res)
    elif res["state"] != p.state and res["state"] in Payment.State.values:
        p.state = res["state"]
        p.save(update_fields=["state"])


# ── Business: pay for a plan ───────────────────────────────────────────

@vendor_required
@require_POST
def start(request):
    """Start a Paystack checkout (card or M-Pesa) and send the browser there."""
    v = request.vendor
    site = SiteSettings.get()
    product = request.POST.get("product") if request.POST.get("product") in Payment.Product.values else Payment.Product.PREMIUM
    months = int(request.POST.get("months") or 1) if (request.POST.get("months") or "1").isdigit() else 1
    months = months if months in (1, 3, 6, 12) else 1
    unit = site.pos_fee if product == Payment.Product.POS else site.premium_fee
    fee = unit * months
    branch = None
    if product == Payment.Product.POS:
        branch = v.branches.filter(pk=request.POST.get("branch")).first() or v.main_branch()
    ctx = {"vendor": v, "site": site, "product": product, "fee": fee, "months": months, "branch": branch}
    days_left = branch.pos_days_left if branch is not None else (v.pos_days_left if product == Payment.Product.POS else v.premium_days_left)
    if days_left is not None and days_left > 20 and request.POST.get("confirm_extend") != "yes":
        ctx["error"] = (f"Your {'POS' if product == 'pos' else 'Premium'} plan is still active for {days_left} more days. "
                        f"Tick “I understand this adds {30 * months} more days” to pay early.")
        ctx["needs_confirm"] = True
        return render(request, "payments/_pay_form.html", ctx)
    ref = f"bf-{product}-{str(v.pk)[:8]}-{int(time.time())}-{secrets.token_hex(3)}"
    p = Payment.objects.create(vendor=v, branch=branch, product=product, months=months, amount=fee, api_ref=ref)
    try:
        url, raw = paystack.initialize(email=v.owner.email, amount=fee, reference=ref,
                                       callback_url=request.build_absolute_uri(reverse("pay_callback")),
                                       metadata={"vendor": str(v.pk), "product": product, "months": months,
                                                 "branch": str(branch.pk) if branch else ""})
    except paystack.PaystackError as e:
        p.apply_state(Payment.State.FAILED, {"failed_reason": str(e)})
        ctx["error"] = str(e)
        return render(request, "payments/_pay_form.html", ctx)
    p.raw = raw
    p.save(update_fields=["raw"])
    if request.htmx:
        # Open Paystack's popup over this page; the full checkout page is only the fallback.
        return render(request, "payments/_popup.html", {**ctx, "payment": p, "checkout_url": url,
                                                        "access_code": (raw.get("data") or {}).get("access_code", ""),
                                                        "done_url": reverse("pay_callback")})
    return redirect(url)


@vendor_required
def callback(request):
    """Paystack sends the browser back here. Never trust the redirect: ask Paystack what happened."""
    ref = request.GET.get("reference") or request.GET.get("trxref") or ""
    p = get_object_or_404(Payment, api_ref=ref, vendor=request.vendor)
    if not p.is_terminal:
        settle(p, paystack.verify(ref))
        p.refresh_from_db()
    return render(request, "payments/result.html", {"vendor": request.vendor, "payment": p, "site": SiteSettings.get()})


@vendor_required
def status(request, pk):
    """Polled by the result page while Paystack still says processing."""
    p = get_object_or_404(Payment, pk=pk, vendor=request.vendor)
    if not p.is_terminal:
        settle(p, paystack.verify(p.api_ref))
        p.refresh_from_db()
    return render(request, "payments/_status.html", {"vendor": request.vendor, "payment": p})


# ── Paystack webhook ───────────────────────────────────────────────────

@csrf_exempt
@require_POST
def paystack_webhook(request):
    if not paystack.signature_ok(request.body, request.headers.get("X-Paystack-Signature", "")):
        return HttpResponse(status=401)
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"ok": True})
    event, data = body.get("event", ""), body.get("data") or {}
    ref = data.get("reference")
    p = Payment.objects.filter(api_ref=ref).select_related("vendor").first() if ref else None
    if p is None:
        log.info("Paystack webhook %s for unknown reference %s", event, ref)
        return JsonResponse({"ok": True})
    if event == "charge.success" and not p.is_terminal:
        settle(p, paystack.verify(ref))          # the webhook is only a nudge; verify is the source of truth
    return JsonResponse({"ok": True})
