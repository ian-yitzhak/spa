from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from adminpanel.audit import log_event
from adminpanel.views import admin_required
from vendors.models import SiteSettings
from vendors.paging import paginate

from .forms import AffiliateForm, AffiliateProfileForm, PayoutForm
from .models import Affiliate, Referral

REF_COOKIE = "bf_ref"


# ── Public: referral link ─────────────────────────────────────────────

def join(request, code):
    """Referral landing: remember the code for 30 days, go to sign-up."""
    aff = Affiliate.objects.filter(code=code.upper(), is_active=True).first()
    resp = redirect("signup")
    if aff:
        resp.set_cookie(REF_COOKIE, aff.code, max_age=30 * 24 * 3600, samesite="Lax", secure=request.is_secure(), httponly=True)
    return resp


# ── Affiliate area ────────────────────────────────────────────────────

def affiliate_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        aff = getattr(request.user, "affiliate", None)
        if aff is None or not request.user.is_affiliate or not aff.is_active:
            messages.error(request, "This area is for affiliates.")
            return redirect("home")
        request.affiliate = aff
        return view(request, *args, **kwargs)
    return wrapper


@affiliate_required
def home(request):
    aff = request.affiliate
    st = aff.stats()
    recent = aff.referrals.select_related("vendor")[:8]
    return render(request, "affiliates/home.html", {"aff": aff, "st": st, "recent": recent, "link": aff.link(request), "fee": SiteSettings.get().affiliate_fee})


@affiliate_required
def signups(request):
    aff = request.affiliate
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    qs = aff.referrals.select_related("vendor", "vendor__owner")
    if q:
        qs = qs.filter(Q(vendor__brand_name__icontains=q) | Q(vendor__owner__first_name__icontains=q) | Q(vendor__town__icontains=q))
    if status in Referral.Status.values:
        qs = qs.filter(status=status)
    page, qs_prefix = paginate(request, qs, 25)
    return render(request, "affiliates/signups.html", {"aff": aff, "refs": page, "page": page, "qs": qs_prefix, "q": q, "status": status, "statuses": Referral.Status.choices})


@affiliate_required
def profile(request):
    aff = request.affiliate
    u = request.user
    form = AffiliateProfileForm(request.POST or None, initial={"first_name": u.first_name, "phone": u.phone})
    if request.method == "POST" and form.is_valid():
        u.first_name, u.phone = form.cleaned_data["first_name"], form.cleaned_data["phone"]
        u.save(update_fields=["first_name", "phone"])
        messages.success(request, "Profile saved.")
        return redirect("aff_profile")
    return render(request, "affiliates/profile.html", {"aff": aff, "form": form, "link": aff.link(request)})


@affiliate_required
def payout(request):
    aff = request.affiliate
    form = PayoutForm(request.POST or None, instance=aff)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_event(request.user, "affiliate_payout_details", aff.payout_summary, request)
        messages.success(request, "Payment details saved.")
        return redirect("aff_payout")
    return render(request, "affiliates/payout.html", {"aff": aff, "form": form})


# ── Admin ─────────────────────────────────────────────────────────────

@admin_required
def admin_list(request):
    q = request.GET.get("q", "").strip()
    qs = Affiliate.objects.select_related("user").annotate(
        n_signups=Count("referrals", distinct=True),
        n_qualified=Count("referrals", filter=Q(referrals__status__in=["qualified", "paid"]), distinct=True),
        unpaid=Sum("referrals__amount", filter=Q(referrals__status="qualified")),
        paid=Sum("referrals__amount", filter=Q(referrals__status="paid")))
    if q:
        qs = qs.filter(Q(user__first_name__icontains=q) | Q(user__email__icontains=q) | Q(user__phone__icontains=q) | Q(code__icontains=q))
    form = AffiliateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        aff = form.save()
        log_event(request.user, "affiliate_create", f"{aff.user.email} {aff.code}", request)
        messages.success(request, f"Affiliate created. Referral link: {aff.link(request)}")
        return redirect("ap_affiliates")
    page, qs_prefix = paginate(request, qs, 25)
    totals = Referral.objects.aggregate(unpaid=Sum("amount", filter=Q(status="qualified")), paid=Sum("amount", filter=Q(status="paid")), pending=Count("id", filter=Q(status="pending")))
    return render(request, "adminpanel/affiliates.html", {"affiliates": page, "page": page, "qs": qs_prefix, "q": q, "form": form, "totals": totals})


@admin_required
def admin_detail(request, pk):
    aff = get_object_or_404(Affiliate.objects.select_related("user"), pk=pk)
    form = AffiliateForm(request.POST or None, instance=aff) if request.POST.get("_form") == "edit" else AffiliateForm(instance=aff)
    if request.method == "POST" and request.POST.get("_form") == "edit" and form.is_valid():
        form.save()
        log_event(request.user, "affiliate_edit", aff.user.email, request)
        messages.success(request, "Affiliate updated.")
        return redirect("ap_affiliate", pk=aff.pk)
    if request.method == "POST" and request.POST.get("_form") == "toggle":
        aff.is_active = not aff.is_active
        aff.save(update_fields=["is_active"])
        aff.user.is_active = aff.is_active
        aff.user.save(update_fields=["is_active"])
        log_event(request.user, "affiliate_toggle", f"{aff.user.email} active={aff.is_active}", request)
        return redirect("ap_affiliate", pk=aff.pk)
    refs = aff.referrals.select_related("vendor", "vendor__owner")
    page, qs_prefix = paginate(request, refs, 50)
    return render(request, "adminpanel/affiliate_detail.html", {"aff": aff, "form": form, "st": aff.stats(), "refs": page, "page": page, "qs": qs_prefix, "link": aff.link(request)})


@admin_required
def admin_referrals(request):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    aff_id = request.GET.get("affiliate", "")
    qs = Referral.objects.select_related("affiliate__user", "vendor", "vendor__owner")
    if q:
        qs = qs.filter(Q(vendor__brand_name__icontains=q) | Q(vendor__owner__email__icontains=q) | Q(affiliate__code__icontains=q) | Q(affiliate__user__first_name__icontains=q) | Q(paid_ref__icontains=q))
    if status in Referral.Status.values:
        qs = qs.filter(status=status)
    if status == "flagged":
        qs = qs.filter(flagged=True)
    if aff_id:
        qs = qs.filter(affiliate_id=aff_id)
    page, qs_prefix = paginate(request, qs, 50)
    return render(request, "adminpanel/referrals.html", {"refs": page, "page": page, "qs": qs_prefix, "q": q, "status": status, "aff_id": aff_id,
                                                          "statuses": Referral.Status.choices, "affiliates": Affiliate.objects.select_related("user").order_by("user__first_name")})


@admin_required
@require_POST
def admin_bulk(request):
    """Bulk actions on selected referrals: mark paid (with reference), reject, or re-check qualification."""
    ids = request.POST.getlist("ids")
    action = request.POST.get("action")
    ref = (request.POST.get("paid_ref") or "").strip()[:80]
    qs = Referral.objects.filter(pk__in=ids)
    n = 0
    if action == "paid":
        if not ref:
            messages.error(request, "Enter the payment reference (e.g. M-Pesa code) to mark as paid.")
            return redirect(request.META.get("HTTP_REFERER") or "ap_referrals")
        n = qs.filter(status=Referral.Status.QUALIFIED).update(status=Referral.Status.PAID, paid_at=timezone.now(), paid_ref=ref, paid_by=request.user)
        log_event(request.user, "affiliate_bulk_paid", f"{n} referrals paid, ref {ref}", request)
        messages.success(request, f"{n} referral{'s' if n != 1 else ''} marked as paid (ref {ref}).")
    elif action == "reject":
        n = qs.exclude(status=Referral.Status.PAID).update(status=Referral.Status.REJECTED)
        log_event(request.user, "affiliate_bulk_reject", f"{n} referrals rejected", request)
        messages.success(request, f"{n} referral{'s' if n != 1 else ''} rejected.")
    elif action == "recheck":
        for r in qs.select_related("vendor__owner"):
            n += bool(r.check_qualified())
        messages.success(request, f"{n} referral{'s' if n != 1 else ''} newly qualified.")
    return redirect(request.META.get("HTTP_REFERER") or "ap_referrals")
