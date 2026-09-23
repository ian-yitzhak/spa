from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from payments.models import Payment
from vendors.models import Inquiry, Review, SiteSettings, Vendor
from vendors.paging import paginate

from .audit import log_event
from .forms import AdminUserForm, ManualActivationForm, SiteSettingsForm, VendorAdminForm
from .models import AuditLog


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin_role:
            messages.error(request, "Admins only.")
            return redirect("dashboard")
        return view(request, *args, **kwargs)
    return wrapper


@admin_required
def index(request):
    vendors = Vendor.objects.all()
    week_ago = timezone.now() - timezone.timedelta(days=7)
    return render(request, "adminpanel/index.html", {
        "total": vendors.count(),
        "premium": vendors.filter(plan=Vendor.Plan.PREMIUM, premium_expires_at__gte=timezone.now()).count(),
        "expiring": vendors.filter(plan=Vendor.Plan.PREMIUM, premium_expires_at__gte=timezone.now(),
                                   premium_expires_at__lte=timezone.now() + timezone.timedelta(days=7)).count(),
        "expired": vendors.filter(plan=Vendor.Plan.PREMIUM, premium_expires_at__lt=timezone.now()).count(),
        "pending": vendors.filter(is_approved=False).count(),
        "new_week": vendors.filter(created_at__gte=week_ago).count(),
        "inquiries": Inquiry.objects.count(),
        "reviews": Review.objects.count(),
        "recent": vendors.select_related("owner").order_by("-created_at")[:8],
        "revenue_month": Payment.objects.filter(state=Payment.State.COMPLETE, applied_at__gte=timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)).aggregate(s=Sum("amount"))["s"] or 0,
        "revenue_total": Payment.objects.filter(state=Payment.State.COMPLETE).aggregate(s=Sum("amount"))["s"] or 0,
        **_pos_volume(),
        "site": SiteSettings.get(),
    })


@admin_required
def backups(request):
    """Read-only view of the nightly backups (names, sizes, dates — never the contents)."""
    import json
    from pathlib import Path
    path = Path(settings.BASE_DIR) / "backups.json"
    data, groups = {}, {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except ValueError:
            data = {}
    mine = [r for r in data.get("files", []) if r.get("product") == "beautyflow"]   # only this product
    for r in mine:
        r["mb"] = round(r["bytes"] / 1048576, 1)
        groups.setdefault(r["product"], []).append(r)
    for rows in groups.values():
        rows.sort(key=lambda r: r["when"], reverse=True)
    return render(request, "adminpanel/backups.html", {
        "generated": data.get("generated"), "keep_days": data.get("keep_days", 30),
        "total_mb": round(sum(r["bytes"] for r in mine) / 1048576),
        "groups": sorted(groups.items()), "count": len(mine),
    })


@admin_required
def sales(request):
    """Platform analytics: what vendors sell on the POS, and what BeautyFlow earns."""
    from datetime import timedelta
    from django.db.models.functions import TruncDate, TruncMonth
    from pos.models import Order
    from vendors.views import _series

    days = 30 if request.GET.get("days") not in ("7", "90") else int(request.GET["days"])
    now, today = timezone.now(), timezone.localdate()
    since = now - timedelta(days=days - 1)
    paid = Order.objects.filter(paid_at__isnull=False)
    window = paid.filter(paid_at__gte=since)

    sales_series = _series(days, [{"d": r["d"], "val": r["val"]} for r in
                                  window.annotate(d=TruncDate("paid_at")).values("d").annotate(val=Sum("total"))])
    orders_series = _series(days, [{"d": r["d"], "val": r["val"]} for r in
                                   window.annotate(d=TruncDate("paid_at")).values("d").annotate(val=Count("id"))])
    rev_window = Payment.objects.filter(state=Payment.State.COMPLETE, applied_at__gte=since)
    rev_series = _series(days, [{"d": r["d"], "val": r["val"]} for r in
                                rev_window.annotate(d=TruncDate("applied_at")).values("d").annotate(val=Sum("amount"))])

    months = []
    m_rows = (Payment.objects.filter(state=Payment.State.COMPLETE, applied_at__gte=now - timedelta(days=365))
              .annotate(m=TruncMonth("applied_at")).values("m", "product").annotate(total=Sum("amount")).order_by("m"))
    by_month = {}
    for r in m_rows:
        slot = by_month.setdefault(r["m"].date().replace(day=1), {"premium": 0, "pos": 0})
        slot[r["product"]] = float(r["total"] or 0)
    mx = max([v["premium"] + v["pos"] for v in by_month.values()] or [0]) or 1
    for m, v in sorted(by_month.items()):
        total = v["premium"] + v["pos"]
        months.append({"label": m.strftime("%b"), "premium": v["premium"], "pos": v["pos"], "total": total,
                       "pct": int(total / mx * 100), "pct_premium": int(v["premium"] / mx * 100), "pct_pos": int(v["pos"] / mx * 100)})

    methods = list(window.values("payment_method").annotate(total=Sum("total"), n=Count("id")).order_by("-total"))
    m_all = sum(float(m["total"] or 0) for m in methods) or 1
    labels = {"cash": "Cash", "mpesa": "M-Pesa", "card": "Card"}
    for m in methods:
        m["label"] = labels.get(m["payment_method"], m["payment_method"] or "—")
        m["pct"] = int(float(m["total"] or 0) / m_all * 100)

    n_orders = window.count()
    return render(request, "adminpanel/sales.html", {
        "days": days, "sales": sales_series, "orders": orders_series, "rev": rev_series, "months": months,
        "methods": methods,
        "pos_today": paid.filter(paid_at__date=today).aggregate(s=Sum("total"))["s"] or 0,
        "pos_window": window.aggregate(s=Sum("total"))["s"] or 0,
        "pos_total": paid.aggregate(s=Sum("total"))["s"] or 0,
        "n_orders": n_orders,
        "avg_order": (window.aggregate(s=Sum("total"))["s"] or 0) / n_orders if n_orders else 0,
        "rev_window": rev_window.aggregate(s=Sum("amount"))["s"] or 0,
        "rev_total": Payment.objects.filter(state=Payment.State.COMPLETE).aggregate(s=Sum("amount"))["s"] or 0,
        "pos_vendors": Vendor.objects.filter(pos_expires_at__gte=now).count(),
        "premium_vendors": Vendor.objects.filter(premium_expires_at__gte=now).count(),
        "selling": window.values("vendor_id").distinct().count(),
    })


def _pos_volume():
    """What the POS vendors are ringing up — their money, not ours, but it shows how alive the product is."""
    from pos.models import Order
    now = timezone.now()
    paid = Order.objects.filter(paid_at__isnull=False)
    month = paid.filter(paid_at__gte=now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
    today = paid.filter(paid_at__date=timezone.localdate())
    return {
        "pos_sales_total": paid.aggregate(s=Sum("total"))["s"] or 0,
        "pos_sales_month": month.aggregate(s=Sum("total"))["s"] or 0,
        "pos_sales_today": today.aggregate(s=Sum("total"))["s"] or 0,
        "pos_orders_month": month.count(),
        "pos_vendors_live": Vendor.objects.filter(pos_expires_at__gte=now).count(),
    }


@admin_required
def vendors(request):
    q = request.GET.get("q", "").strip()
    plan = request.GET.get("plan", "")
    status = request.GET.get("status", "")
    qs = Vendor.objects.select_related("owner").annotate(n_items=Count("items", distinct=True),
                                                         n_inq=Count("inquiries", distinct=True)).order_by("-created_at")
    if q:
        qs = qs.filter(Q(brand_name__icontains=q) | Q(owner__email__icontains=q) | Q(phone__icontains=q) | Q(town__icontains=q))
    now = timezone.now()
    if plan == "premium":
        qs = qs.filter(plan="premium", premium_expires_at__gte=now)
    elif plan == "expired":
        qs = qs.filter(plan="premium", premium_expires_at__lt=now)
    elif plan == "free":
        qs = qs.filter(plan="free")
    if status == "pending":
        qs = qs.filter(is_approved=False)
    elif status == "unpublished":
        qs = qs.filter(is_published=False)
    page, qs_prefix = paginate(request, qs, 25)
    ctx = {"vendors": page, "page": page, "qs": qs_prefix, "q": q, "plan": plan, "status": status}
    if request.htmx:
        return render(request, "adminpanel/_vendor_rows.html", ctx)
    return render(request, "adminpanel/vendors.html", ctx)


@admin_required
def vendor_detail(request, pk):
    v = get_object_or_404(Vendor.objects.select_related("owner"), pk=pk)
    which = request.POST.get("_form")
    form = VendorAdminForm(request.POST if which == "vendor" else None, instance=v)
    act = ManualActivationForm(request.POST if which == "activate" else None, vendor=v)
    if request.method == "POST" and which == "vendor" and form.is_valid():
        changed = ", ".join(form.changed_data)
        form.save()
        log_event(request.user, "vendor_edit", f"{v.brand_name}: {changed}", request)
        messages.success(request, f"{v.brand_name} updated.")
        return redirect("ap_vendor", pk=v.pk)
    if request.method == "POST" and which == "activate" and act.is_valid():
        d = act.cleaned_data
        until = timezone.make_aware(timezone.datetime.combine(d["until"], timezone.datetime.max.time().replace(microsecond=0))) if d["until"] else None
        branch = v.branches.filter(pk=d.get("branch")).first() if d.get("branch") else None
        p = Payment.record_manual(v, d["product"], d["months"], request.user, d["note"], d["amount"], until, branch=branch)
        v.refresh_from_db()
        log_event(request.user, "manual_activation", f"{v.brand_name}: {d['product']} {d['months']}mo until {until or 'auto'} amount {d['amount']} — {d['note']}", request)
        exp = (branch.pos_expires_at if (d["product"] == "pos" and branch) else
               (v.pos_expires_at if d["product"] == "pos" else v.premium_expires_at))
        messages.success(request, f"{p.get_product_display()} activated for {v.brand_name} until {exp:%d %b %Y}. Recorded as manual payment; receipt emailed.")
        return redirect("ap_vendor", pk=v.pk)
    return render(request, "adminpanel/vendor_detail.html", {
        "v": v, "form": form, "act": act, "payments": v.payments.select_related("branch")[:20],
        "branches": list(v.branches.all()),
        "items": v.items.select_related("category")[:50],
        "inquiries": v.inquiries.all()[:20],
        "reviews": v.reviews.all()[:20],
    })


def _vendor_row(request, v):
    v = Vendor.objects.select_related("owner").annotate(n_items=Count("items", distinct=True),
                                                        n_inq=Count("inquiries", distinct=True)).get(pk=v.pk)
    return render(request, "adminpanel/_vendor_row.html", {"v": v})


@admin_required
@require_POST
def vendor_action(request, pk, action):
    v = get_object_or_404(Vendor, pk=pk)
    log_event(request.user, f"vendor_{action}", v.brand_name, request)
    if action == "premium":
        Payment.record_manual(v, Payment.Product.PREMIUM, 1, request.user, "Quick +1 month from vendors list")
    elif action == "free":
        v.plan, v.premium_expires_at = Vendor.Plan.FREE, None
    elif action == "pos":
        Payment.record_manual(v, Payment.Product.POS, 1, request.user, "Quick +1 month from vendors list")
    elif action == "pos_off":
        v.pos_expires_at = None
    elif action == "approve":
        v.is_approved = not v.is_approved
    elif action == "publish":
        v.is_published = not v.is_published
    elif action == "delete":
        v.owner.delete()  # cascades to vendor
        return HttpResponse("")
    v.save()
    return _vendor_row(request, v)


@admin_required
def admins(request):
    q = request.GET.get("q", "").strip()
    qs = User.objects.filter(Q(role=User.Role.ADMIN) | Q(is_superuser=True)).order_by("email")
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(phone__icontains=q))
    page, qs_prefix = paginate(request, qs, 25)
    return render(request, "adminpanel/admins.html", {"admins": page, "page": page, "qs": qs_prefix, "q": q})


@admin_required
def admin_form(request, pk=None):
    user = get_object_or_404(User, pk=pk) if pk else None
    form = AdminUserForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        log_event(request.user, "admin_user_save", f"{obj.email} ({'new' if not user else 'edit'})", request)
        messages.success(request, "Admin saved.")
        return redirect("ap_admins")
    return render(request, "adminpanel/admin_form.html", {"form": form, "obj": user})


@admin_required
@require_POST
def admin_delete(request, pk):
    u = get_object_or_404(User, pk=pk)
    if u == request.user or u.is_superuser:
        return HttpResponse("<p class='p-3 text-sm text-red-600'>Cannot delete this account.</p>")
    log_event(request.user, "admin_user_delete", u.email, request)
    u.delete()
    return HttpResponse("")


@admin_required
def inquiries(request):
    q = request.GET.get("q", "").strip()
    kind = request.GET.get("kind", "")
    qs = Inquiry.objects.select_related("vendor", "item")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(message__icontains=q) | Q(vendor__brand_name__icontains=q))
    if kind in Inquiry.Kind.values:
        qs = qs.filter(kind=kind)
    page, qs_prefix = paginate(request, qs, 25)
    return render(request, "adminpanel/inquiries.html", {"inquiries": page, "page": page, "qs": qs_prefix, "q": q, "kind": kind, "kinds": Inquiry.Kind.choices})


@admin_required
def reviews(request):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    qs = Review.objects.select_related("vendor").filter(verified_at__isnull=False)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(comment__icontains=q) | Q(vendor__brand_name__icontains=q))
    if status == "hidden":
        qs = qs.filter(is_approved=False)
    elif status == "visible":
        qs = qs.filter(is_approved=True)
    page, qs_prefix = paginate(request, qs, 25)
    return render(request, "adminpanel/reviews.html", {"reviews": page, "page": page, "qs": qs_prefix, "q": q, "status": status})


@admin_required
@require_POST
def review_action(request, pk, action):
    r = get_object_or_404(Review, pk=pk)
    log_event(request.user, f"review_{action}", f"{r.vendor.brand_name} / {r.name}", request)
    if action == "delete":
        r.delete()
        return HttpResponse("")
    r.is_approved = not r.is_approved
    r.save(update_fields=["is_approved"])
    return render(request, "adminpanel/_review_row.html", {"r": r})


@admin_required
def settings_view(request):
    form = SiteSettingsForm(request.POST or None, instance=SiteSettings.get())
    if request.method == "POST" and form.is_valid():
        log_event(request.user, "settings_change", ", ".join(form.changed_data), request)
        form.save()
        messages.success(request, "Settings saved.")
        return redirect("ap_settings")
    return render(request, "adminpanel/settings.html", {"form": form})


@admin_required
def payments(request):
    q = request.GET.get("q", "").strip()
    state = request.GET.get("state", "")
    qs = Payment.objects.select_related("vendor")
    if q:
        qs = qs.filter(Q(vendor__brand_name__icontains=q) | Q(api_ref__icontains=q))
    if state:
        qs = qs.filter(state=state)
    page, qs_prefix = paginate(request, qs, 25)
    return render(request, "adminpanel/payments.html", {
        "payments": page, "page": page, "qs": qs_prefix, "q": q, "state": state, "states": Payment.State.choices,
        "keys_on": bool(settings.PAYSTACK_SECRET_KEY and settings.PAYSTACK_PUBLIC_KEY),
    })


@admin_required
def security(request):
    """Audit trail + security events (lockouts, webhook mismatches, blocked duplicates)."""
    q = request.GET.get("q", "").strip()
    action = request.GET.get("action", "")
    qs = AuditLog.objects.select_related("actor")
    if q:
        qs = qs.filter(Q(detail__icontains=q) | Q(actor__email__icontains=q) | Q(ip__icontains=q))
    if action:
        qs = qs.filter(action=action)
    page, qs_prefix = paginate(request, qs, 50)
    actions = AuditLog.objects.values_list("action", flat=True).distinct().order_by("action")
    return render(request, "adminpanel/security.html", {"entries": page, "page": page, "qs": qs_prefix, "q": q, "action": action, "actions": actions})
