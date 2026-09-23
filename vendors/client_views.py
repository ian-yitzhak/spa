"""Clients: public questions and bookings, the inquiries inbox, and the client list."""
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Customer, Inquiry, Vendor
from .paging import paginate
from .security import protect
from .views import pos_module_required, vendor_required


def _live_vendor(slug):
    return get_object_or_404(Vendor, slug=slug, is_published=True, is_approved=True)


# ── Public: ask a question / request a quote ───────────────────────────

@protect("inquiry", 8, 600, require_turnstile=True)
def inquire(request, type_slug, slug):
    vendor = _live_vendor(slug)
    services = vendor.items.filter(is_available=True).order_by("category__order", "name")
    ctx = {"vendor": vendor, "services": services}
    if request.method != "POST":
        ctx["picked"] = request.GET.get("service", "")
        return render(request, "vendors/inquire.html", ctx)
    p = request.POST
    name = (p.get("name") or "").strip()[:80]
    phone = Vendor.normalize_msisdn(p.get("phone") or "")
    message = (p.get("message") or "").strip()[:1000]
    item = services.filter(pk=p.get("service")).first() if p.get("service") else None
    err = ""
    if not name:
        err = "Enter your name."
    elif not phone:
        err = "Enter a phone number we can reach you on."
    elif not message and not item:
        err = "Pick a service or write your question."
    if err:
        ctx.update({"error": err, "form": p, "picked": p.get("service", "")})
        return render(request, "vendors/inquire.html", ctx, status=400)
    kind = Inquiry.Kind.QUOTE if (item and item.price_on_request) else Inquiry.Kind.INQUIRY
    inq = Inquiry.objects.create(vendor=vendor, kind=kind, name=name, phone=phone, message=message, item=item)
    Customer.touch(vendor, phone, name)
    ctx.update({"sent": inq, "wa_link": _inquiry_wa(vendor, inq)})
    return render(request, "vendors/inquire.html", ctx)


def _inquiry_wa(vendor, inq):
    if not vendor.whatsapp_link:
        return ""
    from urllib.parse import quote
    bits = [f"Hi {vendor.brand_name}, I sent a question on BeautyFlow:"]
    if inq.item:
        bits += ["", f"Service: {inq.item.name}"]
    if inq.message:
        bits += ["", inq.message]
    bits += ["", f"Name: {inq.name}", f"Phone: 0{inq.phone[3:]}"]
    return f"{vendor.whatsapp_link}?text={quote(chr(10).join(bits))}"


# ── Public: book an appointment ───────────────────────────────────────

@require_POST
@protect("reserve", 5, 600)
def reserve(request, type_slug, slug):
    from pos.forms import PublicBookingForm
    vendor = _live_vendor(slug)
    if not vendor.accepts_bookings:
        return render(request, "partials/reservation_form.html", {"vendor": vendor, "closed": True})
    form = PublicBookingForm(request.POST, vendor=vendor)
    if form.is_valid():
        b = form.save(commit=False)
        b.vendor = vendor
        b.duration_min = b.service.duration_min if b.service else 60
        b.branch = (b.staff.branch if b.staff and b.staff.branch_id else None) or vendor.main_branch()
        b.save()
        Customer.touch(vendor, b.phone, b.name)
        return render(request, "partials/reservation_form.html", {"vendor": vendor, "sent": True, "res": b})
    return render(request, "partials/reservation_form.html", {"vendor": vendor, "res_form": form})


# ── Dashboard: inquiries inbox ────────────────────────────────────────

@vendor_required
def inquiry_new_count(request):
    """Sidebar badge: new questions waiting for a reply."""
    n = request.vendor.inquiries.filter(status=Inquiry.Status.NEW).count()
    return HttpResponse(str(n) if n else "")


@vendor_required
def inquiries(request):
    v = request.vendor
    tab = request.GET.get("tab", "open")
    qs = v.inquiries.select_related("item").order_by("-created_at")
    if tab == "open":
        qs = qs.filter(status__in=[Inquiry.Status.NEW, Inquiry.Status.CONTACTED])
    page, qs_prefix = paginate(request, qs, 30)
    Inquiry.objects.filter(pk__in=[i.pk for i in page], is_read=False).update(is_read=True)
    return render(request, "dashboard/inquiries.html", {"vendor": v, "inquiries": page, "page": page, "qs": qs_prefix, "tab": tab,
                                                        "new_count": v.inquiries.filter(status=Inquiry.Status.NEW).count()})


@vendor_required
@require_POST
def inquiry_action(request, pk, action):
    inq = get_object_or_404(Inquiry, pk=pk, vendor=request.vendor)
    if action in (Inquiry.Status.CONTACTED, Inquiry.Status.CLOSED, Inquiry.Status.CONVERTED):
        inq.status = action
        inq.is_read = True
        inq.save(update_fields=["status", "is_read"])
    return redirect("dashboard_inquiries")


# ── Dashboard: clients ────────────────────────────────────────────────

@pos_module_required
def customers(request):
    v = request.vendor
    q = request.GET.get("q", "").strip()
    qs = v.customers.all()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q))
    sort = request.GET.get("sort", "")
    if sort == "spent":
        qs = qs.order_by("-total_spent")
    elif sort == "orders":
        qs = qs.order_by("-orders_count")
    page, qs_prefix = paginate(request, qs, 30)
    totals = v.customers.aggregate(n=Sum("orders_count"), spent=Sum("total_spent"))
    return render(request, "dashboard/customers.html", {"vendor": v, "customers": page, "page": page, "qs": qs_prefix, "q": q, "sort": sort,
                                                        "count": v.customers.count(), "totals": totals,
                                                        "show_all_branches_note": v.branches_enabled and v.branches.filter(is_active=True).count() > 1})


@pos_module_required
def customers_export(request):
    """CSV of phone numbers for a WhatsApp broadcast list."""
    import csv
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{request.vendor.slug}-clients.csv"'
    w = csv.writer(resp)
    w.writerow(["name", "phone", "visits", "total_spent", "last_seen"])
    for c in request.vendor.customers.filter(opt_out=False):
        w.writerow([c.name, "+" + c.phone, c.orders_count, c.total_spent, c.last_seen.date()])
    return resp
