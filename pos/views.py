import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from vendors.models import MenuItem, SiteSettings
from vendors.paging import paginate
from vendors.views import vendor_required

from .branching import resolve as _resolve_branch, scope as _scope
from .models import (Booking, Branch, Expense, InsightQuestion, InsightReport, Order, OrderItem, Staff, StaffPayout,
                     StaffShift)

SESSION_ORDER = "pos_order_id"
SESSION_STAFF = "pos_staff_id"


# ── Who is asking ──────────────────────────────────────────────────────

def _resolve_pos_user(request):
    """Attach request.vendor, request.role (owner / cashier / staff) and request.staff (None for the owner)."""
    u = request.user
    vendor = getattr(u, "vendor", None)
    if vendor is not None:
        request.vendor, request.staff, request.role = vendor, None, "owner"
        return True
    staff = getattr(u, "staff_profile", None)
    if staff is not None and staff.is_active and u.is_team:
        request.vendor, request.staff, request.role = staff.vendor, staff, staff.role
        return True
    return False


def pos_required(view):
    """Owner or an active team member, AND the business has an active POS subscription."""
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not _resolve_pos_user(request):
            messages.error(request, "You don't have access to a point of sale.")
            return redirect("home")
        _resolve_branch(request)
        gate = request.branch if request.branch is not None else request.vendor
        if not gate.pos_active:
            return render(request, "pos/locked.html", {"vendor": request.vendor, "site": SiteSettings.get(), "product": "pos",
                                                       "branch": request.branch, "is_team": request.role != "owner",
                                                       "role": request.role}, status=402)
        return view(request, *args, **kwargs)
    return wrapper


def roles_required(*allowed):
    """POS pages limited to some roles; everyone else goes back to their own dashboard."""
    def deco(view):
        @wraps(view)
        @pos_required
        def wrapper(request, *args, **kwargs):
            if request.role not in allowed:
                return redirect("dashboard" if request.role == "owner" else "pos_me")
            return view(request, *args, **kwargs)
        return wrapper
    return deco


owner_pos_required = roles_required("owner")
till_required = roles_required("owner", "cashier")


def owner_branch_admin(view):
    """The owner's branch list. Never gated on a subscription — this is where they pay for one."""
    @wraps(view)
    @vendor_required
    def wrapper(request, *args, **kwargs):
        _resolve_pos_user(request)
        _resolve_branch(request)
        return view(request, *args, **kwargs)
    return wrapper


def needs_branch(what="This"):
    """Recording pages need one branch. In "All branches" mode the owner picks first."""
    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if getattr(request, "write_branch", None) is None and getattr(request, "branches", None):
                return render(request, "pos/pick_branch.html", _ctx(request, what=what))
            return view(request, *args, **kwargs)
        return wrapper
    return deco


def _team(vendor, **filters):
    return list(vendor.staff.filter(is_active=True, role=Staff.Role.STAFF, **filters).select_related("user"))


def _ctx(request, **extra):
    branches = getattr(request, "branches", [])
    owner = request.role == "owner"
    base = {"vendor": request.vendor, "is_team": not owner, "role": request.role, "me_staff": request.staff,
            "branch": getattr(request, "branch", None), "branches": branches,
            "show_branches": request.vendor.branches_enabled and owner,
            "many_branches": request.vendor.branches_enabled and len(branches) > 1 and owner,
            "branches_allowed": owner and request.vendor.can_use_branches}
    base.update(extra)
    return base


def _paid(request):
    """Paid sales for the branch in force; voided sales never count."""
    return _scope(request, request.vendor.orders.filter(paid_at__isnull=False).exclude(status=Order.Status.CANCELLED))


def _visible_orders(request):
    """Owner and cashier see every sale; staff only the ones they did a service on."""
    qs = request.vendor.orders.all()
    if request.role == "staff":
        qs = qs.filter(items__staff=request.staff).distinct()
    return qs


# ── POS screen (owner and cashier) ─────────────────────────────────────

def _current_order(request, create=True):
    """The ticket on this till: a draft being built, or an open one that was resumed."""
    v = request.vendor
    oid = request.session.get(SESSION_ORDER)
    order = (Order.objects.filter(pk=oid, vendor=v, paid_at__isnull=True, status__in=[Order.Status.DRAFT, Order.Status.OPEN]).first()
             if oid else None)
    if order is None and create:
        order = Order.objects.create(vendor=v, cashier=request.user, branch=getattr(request, "write_branch", None) or v.main_branch())
        request.session[SESSION_ORDER] = str(order.pk)
    return order


def _ticket_staff(request, order):
    """Who is doing this ticket: whoever the services already carry, else the person picked before adding any."""
    line = order.items.filter(staff__isnull=False).select_related("staff__user").first() if order else None
    if line:
        return line.staff
    sid = request.session.get(SESSION_STAFF)
    return request.vendor.staff.filter(pk=sid, is_active=True, role=Staff.Role.STAFF).select_related("user").first() if sid else None


def _order_panel(request, order):
    return render(request, "pos/_order.html", _ctx(request, order=order, lines=order.items.select_related("staff__user", "menu_item"),
                                                  team=_team(request.vendor), ticket_staff=_ticket_staff(request, order)))


@till_required
@needs_branch("A sale")
def home(request):
    from .pricing import price_items
    v = request.vendor
    order = _current_order(request)
    cat = request.GET.get("cat", "")
    q = request.GET.get("q", "").strip()
    items = v.items.filter(is_available=True, price_on_request=False).select_related("category").order_by("category__order", "name")
    if cat:
        items = items.filter(category_id=cat) if cat != "none" else items.filter(category__isnull=True)
    if q:
        items = items.filter(name__icontains=q)
    page, qs_prefix = paginate(request, items, 30)
    today = timezone.localdate()
    ctx = _ctx(request, order=order, lines=order.items.select_related("staff__user", "menu_item"),
               categories=v.categories.all(), items=price_items(page, request.write_branch),
               page=page, qs=qs_prefix, cat=cat, q=q, team=_team(v), ticket_staff=_ticket_staff(request, order),
               open_count=_scope(request, v.orders.filter(status=Order.Status.OPEN, paid_at__isnull=True)).count(),
               bookings_today=_scope(request, v.bookings.filter(date=today, status__in=[Booking.Status.REQUESTED, Booking.Status.CONFIRMED],
                                                                order__isnull=True)).select_related("staff__user").prefetch_related("items")[:6])
    if request.htmx and request.htmx.target in ("menu-grid", "grid-more"):
        return render(request, "pos/_menu_grid.html", ctx)
    return render(request, "pos/home.html", ctx)


@till_required
@require_POST
def add_item(request, pk):
    item = get_object_or_404(MenuItem, pk=pk, vendor=request.vendor, price_on_request=False)
    order = _current_order(request)
    OrderItem.add(order, item, staff=_ticket_staff(request, order))
    return _order_panel(request, order)


@till_required
@require_POST
def line_qty(request, pk, direction):
    order = _current_order(request)
    line = get_object_or_404(OrderItem, pk=pk, order=order)
    if direction == "inc":
        line.qty += 1
        line.save()
    else:
        line.qty -= 1
        if line.qty <= 0:
            line.delete()
        else:
            line.save()
    order.recalc()
    return _order_panel(request, order)


@till_required
@require_POST
def ticket_staff(request):
    """One person does the whole ticket: every service on it, and anything added after, goes to them."""
    order = _current_order(request)
    sid = request.POST.get("staff") or ""
    staff = request.vendor.staff.filter(pk=sid, is_active=True).first() if sid else None
    request.session[SESSION_STAFF] = str(staff.pk) if staff else ""
    for line in list(order.items.all()):
        twin = order.items.filter(menu_item=line.menu_item, staff=staff).exclude(pk=line.pk).first() if line.menu_item_id else None
        if twin:                                    # same service twice now reads as one line with qty 2
            twin.qty += line.qty
            twin.save()
            line.delete()
        else:
            line.staff = staff
            line.save(update_fields=["staff"])
    order.recalc()
    return _order_panel(request, order)


@till_required
@require_POST
def set_client(request):
    order = _current_order(request)
    order.customer_name = (request.POST.get("customer_name") or "").strip()[:80]
    order.customer_phone = (request.POST.get("customer_phone") or "").strip()[:20]
    order.save(update_fields=["customer_name", "customer_phone", "updated_at"])
    return _order_panel(request, order)


@till_required
@require_POST
def set_discount(request):
    order = _current_order(request)
    try:
        value = max(Decimal((request.POST.get("discount_value") or "0").strip() or 0), Decimal(0))
    except InvalidOperation:
        value = Decimal(0)
    order.discount_type, order.discount_value = (Order.Discount.AMOUNT, value) if value else ("", Decimal(0))
    order.save(update_fields=["discount_type", "discount_value"])
    order.recalc()
    return _order_panel(request, order)


@till_required
@require_POST
def clear(request):
    order = _current_order(request, create=False)
    if order and order.status == Order.Status.DRAFT:
        order.delete()
    request.session.pop(SESSION_ORDER, None)
    request.session.pop(SESSION_STAFF, None)
    return _order_panel(request, _current_order(request))


@till_required
@require_POST
def hold(request):
    """Client is still in the chair: keep the ticket open and take payment later."""
    order = _current_order(request)
    if not order.items.exists():
        return _order_panel(request, order)
    if order.status == Order.Status.DRAFT:
        order.place()
    request.session.pop(SESSION_ORDER, None)
    request.session.pop(SESSION_STAFF, None)
    messages.success(request, f"Ticket #{order.ref} for {order.label} is open. Take payment from Open tickets when they're done.")
    resp = HttpResponse()
    resp["HX-Redirect"] = "/pos/open/"
    return resp


@till_required
def open_tickets(request):
    qs = (_scope(request, request.vendor.orders.filter(status=Order.Status.OPEN, paid_at__isnull=True))
          .select_related("cashier", "branch").prefetch_related("items__staff__user").order_by("placed_at"))
    return render(request, "pos/open.html", _ctx(request, tickets=qs[:80]))


@till_required
@require_POST
def resume(request, pk):
    order = get_object_or_404(request.vendor.orders, pk=pk, status=Order.Status.OPEN, paid_at__isnull=True)
    request.session[SESSION_ORDER] = str(order.pk)
    return redirect("pos_home")


@till_required
@require_POST
def pay(request):
    """Take payment for the ticket on this till. Every service must say who did it."""
    order = _current_order(request)
    if order.is_paid or not order.items.exists():
        raise Http404
    if order.items.filter(staff__isnull=True).exists():
        return HttpResponse("Pick who did it (Done by) before taking payment.", status=400)
    method = request.POST.get("method")
    if method not in Order.Method.values:
        return HttpResponse("Choose a payment method", status=400)

    def money(key):
        try:
            return Decimal((request.POST.get(key) or "0").strip() or 0)
        except InvalidOperation:
            return Decimal("0")
    tendered = money("tendered") if method == Order.Method.CASH and request.POST.get("tendered") else None
    if method == Order.Method.SPLIT:
        order.paid_mpesa, order.paid_cash = money("mpesa_amount"), money("cash_amount")
        if order.paid_mpesa + order.paid_cash <= 0:
            return HttpResponse("Enter the M-Pesa and cash amounts", status=400)
        order.save(update_fields=["paid_mpesa", "paid_cash"])
    order.mark_paid(method, (request.POST.get("ref") or "").strip(), tendered,
                    (request.POST.get("payer_name") or "").strip(), by=request.user)
    Booking.objects.filter(order=order).update(status=Booking.Status.DONE)
    request.session.pop(SESSION_ORDER, None)
    request.session.pop(SESSION_STAFF, None)
    resp = HttpResponse()
    resp["HX-Redirect"] = f"/pos/receipt/{order.pk}/"
    return resp


# ── Sales ──────────────────────────────────────────────────────────────

@pos_required
def sales(request):
    if request.role == "staff":
        return _my_sales(request)
    v = request.vendor
    q = request.GET.get("q", "").strip()
    method = request.GET.get("method", "")
    who = request.GET.get("staff", "")
    qs = _scope(request, v.orders.filter(paid_at__isnull=False)).select_related("cashier", "branch").prefetch_related("items__staff__user")
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(customer_name__icontains=q) | Q(customer_phone__icontains=q)
                       | Q(payment_ref__icontains=q) | Q(items__name__icontains=q)).distinct()
    if method in Order.Method.values:
        qs = qs.filter(payment_method=method)
    if who:
        qs = qs.filter(items__staff_id=who).distinct()
    d = request.GET.get("date")
    if d:
        qs = qs.filter(paid_at__date=d)
    qs = qs.order_by("-paid_at")
    page, qs_prefix = paginate(request, qs, 25)
    totals = qs.exclude(status=Order.Status.CANCELLED).aggregate(total=Sum("total"), n=Count("id"))
    return render(request, "pos/sales.html", _ctx(request, orders=page, page=page, qs=qs_prefix, q=q, method=method, who=who,
                                                  date=d or "", methods=Order.Method.choices, totals=totals,
                                                  team=_team(v)))


def _my_sales(request):
    """Staff: every paid service they did, what they earned on it, and whether it has been paid out."""
    st = request.staff
    lines = st.earned_lines().select_related("order", "payout").order_by("-order__paid_at")
    d_from, d_to = request.GET.get("from", ""), request.GET.get("to", "")
    if d_from:
        lines = lines.filter(order__paid_at__date__gte=d_from)
    if d_to:
        lines = lines.filter(order__paid_at__date__lte=d_to)
    state = request.GET.get("state", "")
    if state == "unpaid":
        lines = lines.filter(payout__isnull=True)
    elif state == "paid":
        lines = lines.filter(payout__isnull=False)
    page, qs_prefix = paginate(request, lines, 30)
    totals = lines.aggregate(sales=Sum("line_total"), commission=Sum("commission"), n=Sum("qty"))
    return render(request, "pos/my_sales.html", _ctx(request, lines=page, page=page, qs=qs_prefix, totals=totals,
                                                     d_from=d_from, d_to=d_to, state=state, balance=st.balance()))


# ── Reports ────────────────────────────────────────────────────────────

def _period(request):
    period = request.GET.get("period", "daily")
    today = timezone.localdate()
    if period == "weekly":
        start = today - timedelta(days=today.weekday())
    elif period == "monthly":
        start = today.replace(day=1)
    else:
        period, start = "daily", today
    d = request.GET.get("date")
    if d:
        try:
            anchor = timezone.datetime.strptime(d, "%Y-%m-%d").date()
            if period == "daily":
                start = anchor
            elif period == "weekly":
                start = anchor - timedelta(days=anchor.weekday())
            else:
                start = anchor.replace(day=1)
        except ValueError:
            pass
    if period == "daily":
        end = start + timedelta(days=1)
    elif period == "weekly":
        end = start + timedelta(days=7)
    else:
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    tz = timezone.get_current_timezone()
    return (period, start, end, timezone.make_aware(timezone.datetime.combine(start, timezone.datetime.min.time()), tz),
            timezone.make_aware(timezone.datetime.combine(end, timezone.datetime.min.time()), tz))


def staff_earnings(lines):
    """Per person: services done, sales value, commission, and how much of it is still unpaid."""
    rows = (lines.filter(staff__isnull=False)
            .values("staff_id", "staff__user__first_name", "staff__job_title")
            .annotate(n=Sum("qty"), sales=Sum("line_total"), earned=Sum("commission"),
                      owed=Sum("commission", filter=Q(payout__isnull=True)))
            .order_by("-sales"))
    mx = max([r["sales"] or 0 for r in rows] or [0]) or 1
    return [{"id": r["staff_id"], "name": r["staff__user__first_name"] or "—", "title": r["staff__job_title"], "n": r["n"] or 0,
             "sales": r["sales"] or 0, "commission": r["earned"] or 0, "unpaid": r["owed"] or 0,
             "pct": int((r["sales"] or 0) / mx * 100)} for r in rows]


@till_required
def reports(request):
    from django.db.models.functions import ExtractHour, ExtractWeekDay
    v = request.vendor
    period, start, end, dt_start, dt_end = _period(request)
    paid = _paid(request).filter(paid_at__gte=dt_start, paid_at__lt=dt_end)
    lines = OrderItem.objects.filter(order__in=paid)
    by_staff = staff_earnings(lines)
    summary = paid.aggregate(total=Sum("total"), tax=Sum("tax"), discount=Sum("discount"), n=Count("id"))
    commission = lines.aggregate(t=Sum("commission"))["t"] or 0
    by_method = list(paid.values("payment_method").annotate(total=Sum("total"), n=Count("id")).order_by("-total"))
    for m in by_method:
        m["label"] = dict(Order.Method.choices).get(m["payment_method"], m["payment_method"])
    top_items = lines.values("name").annotate(qty=Sum("qty"), total=Sum("line_total")).order_by("-total")[:10]
    by_day = paid.annotate(day=TruncDate("paid_at")).values("day").annotate(total=Sum("total"), n=Count("id")).order_by("day")
    unpaid = _scope(request, v.orders.filter(status=Order.Status.OPEN, paid_at__isnull=True)).aggregate(total=Sum("total"), n=Count("id"))
    pnl = None
    if request.role == "owner":
        exp = _scope(request, v.expenses.all()).filter(date__gte=start, date__lt=end)
        exp_total = exp.aggregate(t=Sum("amount"))["t"] or 0
        by_cat = list(exp.values("category").annotate(total=Sum("amount"), n=Count("id")).order_by("-total"))
        labels = dict(Expense.Category.choices)
        mxe = max([c["total"] for c in by_cat] or [0]) or 1
        for c_ in by_cat:
            c_["label"] = labels.get(c_["category"], c_["category"])
            c_["pct"] = int(c_["total"] / mxe * 100)
        sales_total = summary["total"] or 0
        profit = sales_total - exp_total - commission
        pnl = {"sales": sales_total, "expenses": exp_total, "commission": commission, "profit": profit, "by_cat": by_cat,
               "margin": (round(profit / sales_total * 100) if sales_total else None), "n": exp.count()}
    # Analytics (inline SVG): hour-of-day, weekday, 30-day trend, payment and service donuts
    last30 = _paid(request).filter(paid_at__gte=timezone.now() - timedelta(days=30))
    hours = {r["h"]: float(r["t"] or 0) for r in last30.annotate(h=ExtractHour("paid_at")).values("h").annotate(t=Sum("total"))}
    mxh = max(hours.values() or [0]) or 1
    by_hour = [{"h": h, "label": f"{h:02d}", "total": hours.get(h, 0), "pct": int(hours.get(h, 0) / mxh * 100)} for h in range(6, 24)]
    peak_hour = max(by_hour, key=lambda x: x["total"]) if any(x["total"] for x in by_hour) else None
    wd = {r["w"]: float(r["t"] or 0) for r in last30.annotate(w=ExtractWeekDay("paid_at")).values("w").annotate(t=Sum("total"))}
    names = {2: "Mon", 3: "Tue", 4: "Wed", 5: "Thu", 6: "Fri", 7: "Sat", 1: "Sun"}
    mxw = max(wd.values() or [0]) or 1
    by_weekday = [{"label": names[k], "total": wd.get(k, 0), "pct": int(wd.get(k, 0) / mxw * 100)} for k in (2, 3, 4, 5, 6, 7, 1)]
    best_day = max(by_weekday, key=lambda x: x["total"]) if any(x["total"] for x in by_weekday) else None
    today = timezone.localdate()
    s_by = {r["d"]: float(r["t"] or 0) for r in last30.annotate(d=TruncDate("paid_at")).values("d").annotate(t=Sum("total"))}
    e_by = {}
    if request.role == "owner":
        e_by = {r["date"]: float(r["t"] or 0) for r in _scope(request, v.expenses.all()).filter(date__gte=today - timedelta(days=29)).values("date").annotate(t=Sum("amount"))}
    days = [today - timedelta(days=i) for i in range(29, -1, -1)]
    mxt = max(list(s_by.values()) + list(e_by.values()) + [0]) or 1
    W, H = 600, 160

    def pts(src):
        return " ".join(f"{round(i * W / 29, 1)},{round(H - (src.get(d, 0) / mxt) * (H - 12) - 4, 1)}" for i, d in enumerate(days))
    trend = {"sales": pts(s_by), "expenses": pts(e_by) if e_by else "", "sales_area": f"0,{H} " + pts(s_by) + f" {W},{H}",
             "first": days[0], "mid": days[15], "max": mxt}

    def donut(rows, colors):
        tot = sum(float(r["total"] or 0) for r in rows) or 1
        acc, out = 0.0, []
        for i, r in enumerate(rows):
            frac = float(r["total"] or 0) / tot
            out.append({"label": r["label"], "pct": round(frac * 100), "offset": round(acc * 100, 2), "dash": round(frac * 100, 2),
                        "color": colors[i % len(colors)], "total": r["total"]})
            acc += frac
        return out
    pay_donut = donut(by_method, ["#16a34a", "#1D1D1F", "#C0587E"])
    item_donut = donut([{"label": t["name"], "total": t["total"]} for t in top_items[:5]],
                       ["#C0587E", "#E7B8C8", "#1D1D1F", "#6b7280", "#9ca3af"])
    max_day = max([d["total"] for d in by_day] or [0]) or 1
    by_day = [{**d, "pct": int(d["total"] / max_day * 100)} for d in by_day]
    grand = summary["total"] or 1
    by_method = [{**m, "pct": int(m["total"] / grand * 100)} for m in by_method]
    max_item = max([t["total"] for t in top_items] or [0]) or 1
    top_items = [{**t, "pct": int(t["total"] / max_item * 100)} for t in top_items]
    return render(request, "pos/reports.html", _ctx(
        request, by_staff=by_staff, pnl=pnl, by_hour=by_hour, peak_hour=peak_hour, by_weekday=by_weekday, best_day=best_day,
        trend=trend, pay_donut=pay_donut, item_donut=item_donut, commission=commission,
        period=period, start=start, end=end - timedelta(days=1), summary=summary,
        by_method=by_method, top_items=top_items, by_day=by_day, unpaid=unpaid,
        avg=(summary["total"] / summary["n"]) if summary["n"] else 0,
        prev=(start - (end - start)).isoformat(), next=end.isoformat()))


# ── Receipts ───────────────────────────────────────────────────────────

def _receipt_lines(order):
    """The lines, plus who did them: one name for the whole receipt when one person did everything."""
    items = list(order.items.select_related("staff__user"))
    names = list(dict.fromkeys(l.staff.name for l in items if l.staff_id))
    return {"items": items, "many_staff": len(names) > 1, "done_by": names[0] if len(names) == 1 else ""}


@pos_required
def receipt(request, pk):
    order = get_object_or_404(_visible_orders(request).select_related("cashier", "vendor"), pk=pk)
    return render(request, "pos/receipt.html", {"vendor": order.vendor, "order": order, **_receipt_lines(order),
                                                "public_url": request.build_absolute_uri(f"/r/{order.pk}/"), "owner": True})


@pos_required
def receipt_pdf(request, pk):
    order = get_object_or_404(_visible_orders(request).select_related("vendor"), pk=pk)
    resp = HttpResponse(_receipt_bytes(request, order), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="receipt-{order.ref}-{order.vendor.slug}.pdf"'
    return resp


def _receipt_bytes(request, order):
    """Drawing a PDF with a QR takes ~200ms, and a receipt never changes unless it is voided."""
    from django.core.cache import cache
    from .receipt_pdf import build_receipt_pdf
    stamp = int((order.updated_at or order.created_at).timestamp())
    key = f"receiptpdf:{order.pk}:{stamp}"
    pdf = cache.get(key)
    if pdf is None:
        pdf = build_receipt_pdf(order, request.build_absolute_uri(f"/r/{order.pk}/"))
        cache.set(key, pdf, 7 * 24 * 3600)
    return pdf


def public_receipt_pdf(request, pk):
    """Client's own receipt PDF — the sale's UUID is the secret."""
    order = get_object_or_404(Order.objects.select_related("vendor"), pk=pk, paid_at__isnull=False)
    resp = HttpResponse(_receipt_bytes(request, order), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="receipt-{order.ref}-{order.vendor.slug}.pdf"'
    return resp


def public_receipt(request, pk):
    """Shareable receipt (UUID acts as the secret)."""
    order = get_object_or_404(Order.objects.select_related("vendor"), pk=pk, paid_at__isnull=False)
    return render(request, "pos/receipt.html", {"vendor": order.vendor, "order": order, **_receipt_lines(order),
                                                "public_url": request.build_absolute_uri(), "owner": False})


# ── Expenses (owner) ───────────────────────────────────────────────────

@owner_pos_required
@needs_branch("An expense")
def expenses(request):
    from .forms import ExpenseForm
    v = request.vendor
    form = ExpenseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        e = form.save(commit=False)
        e.vendor, e.recorded_by = v, request.user
        e.branch = getattr(request, "write_branch", None) or v.main_branch()
        e.save()
        messages.success(request, f"Expense recorded: KES {e.amount:,.0f} — {e.description}.")
        return redirect("pos_expenses")
    q = request.GET.get("q", "").strip()
    cat = request.GET.get("cat", "")
    d_from, d_to = request.GET.get("from", ""), request.GET.get("to", "")
    qs = _scope(request, v.expenses.all())
    if q:
        qs = qs.filter(Q(description__icontains=q) | Q(reference__icontains=q))
    if cat in Expense.Category.values:
        qs = qs.filter(category=cat)
    if d_from:
        qs = qs.filter(date__gte=d_from)
    if d_to:
        qs = qs.filter(date__lte=d_to)
    page, qs_prefix = paginate(request, qs, 30)
    total = qs.aggregate(t=Sum("amount"))["t"] or 0
    month = v.expenses.filter(date__gte=timezone.localdate().replace(day=1)).aggregate(t=Sum("amount"))["t"] or 0
    return render(request, "pos/expenses.html", _ctx(request, form=form, expenses=page, page=page, qs=qs_prefix, q=q, cat=cat,
                                                     d_from=d_from, d_to=d_to, cats=Expense.Category.choices, total=total, month=month))


@owner_pos_required
def expense_edit(request, pk):
    from .forms import ExpenseForm
    e = get_object_or_404(Expense, pk=pk, vendor=request.vendor)
    form = ExpenseForm(request.POST or None, instance=e)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Expense updated.")
        return redirect("pos_expenses")
    return render(request, "pos/expense_form.html", _ctx(request, form=form, expense=e))


@owner_pos_required
@require_POST
def expense_delete(request, pk):
    get_object_or_404(Expense, pk=pk, vendor=request.vendor).delete()
    return HttpResponse("")


# ── Team dashboard and profile ─────────────────────────────────────────

@pos_required
def me(request):
    """Landing page for staff and cashiers (the owner has /dashboard/)."""
    if request.role == "owner":
        return redirect("dashboard")
    v = request.vendor
    today = timezone.localdate()
    ctx = _ctx(request, today=today)
    if request.role == "staff":
        st = request.staff
        mine = st.earned_lines()
        month_start = today.replace(day=1)
        agg_today = mine.filter(order__paid_at__date=today).aggregate(n=Sum("qty"), sales=Sum("line_total"), c=Sum("commission"))
        agg_month = mine.filter(order__paid_at__date__gte=month_start).aggregate(n=Sum("qty"), sales=Sum("line_total"), c=Sum("commission"))
        ctx.update(
            agg_today=agg_today, agg_month=agg_month, balance=st.balance(),
            bookings=v.bookings.filter(staff=st, date__gte=today, status__in=[Booking.Status.REQUESTED, Booking.Status.CONFIRMED])
                               .prefetch_related("items")[:8],
            shifts=st.shifts.filter(date__gte=today)[:7],
            payouts=st.payouts.all()[:5],
            recent=mine.select_related("order").order_by("-order__paid_at")[:8])
        return render(request, "pos/me_staff.html", ctx)
    paid_today = _paid(request).filter(paid_at__date=today)
    agg = paid_today.aggregate(total=Sum("total"), n=Count("id"))
    ctx.update(total_today=agg["total"] or 0, n_today=agg["n"] or 0,
               by_method=list(paid_today.values("payment_method").annotate(t=Sum("total")).order_by("-t")),
               open_tickets=_scope(request, v.orders.filter(status=Order.Status.OPEN, paid_at__isnull=True)).prefetch_related("items")[:10],
               bookings=_scope(request, v.bookings.filter(date=today)).exclude(status=Booking.Status.CANCELLED)
                        .select_related("staff__user").prefetch_related("items"),
               recent=paid_today.order_by("-paid_at")[:8])
    return render(request, "pos/me_cashier.html", ctx)


@pos_required
def profile(request):
    """A team member's own details, what they earn, and their payslips."""
    if request.role == "owner":
        return redirect("dashboard_profile")
    st = request.staff
    links = st.service_links.select_related("service")
    return render(request, "pos/profile.html", _ctx(request, st=st, links=links, payouts=st.payouts.all()[:24],
                                                    balance=st.balance() if st.role == Staff.Role.STAFF else None))


@pos_required
def payout_receipt(request, pk):
    """Payslip for one payout. The owner sees any; a staff member only their own."""
    p = get_object_or_404(StaffPayout.objects.select_related("staff__user", "vendor", "paid_by"), pk=pk, vendor=request.vendor)
    if request.role != "owner" and (request.staff is None or p.staff_id != request.staff.pk):
        raise Http404
    lines = p.lines.select_related("order").order_by("order__paid_at")
    return render(request, "pos/payout_receipt.html", _ctx(request, p=p, lines=lines))


# ── Bookings ───────────────────────────────────────────────────────────

@pos_required
def bookings(request):
    from .forms import BookingForm
    v = request.vendor
    can_edit = request.role in ("owner", "cashier")
    form = BookingForm(request.POST or None, vendor=v) if can_edit else None
    if can_edit and request.method == "POST" and form.is_valid():
        b = form.save(commit=False)
        b.vendor, b.created_by = v, request.user
        b.branch = (b.staff.branch if b.staff and b.staff.branch_id else None) or getattr(request, "write_branch", None) or v.main_branch()
        if b.source != Booking.Source.ONLINE:
            b.status = Booking.Status.CONFIRMED
        b.save()
        b.set_services(list(form.cleaned_data["services"]))
        if form.cleaned_data.get("duration_min"):
            b.duration_min = form.cleaned_data["duration_min"]
            b.save(update_fields=["duration_min"])
        messages.success(request, f"Booked: {b.name}, {b.services_label} on {b.date:%a %d %b} at {b.time:%H:%M}.")
        return redirect(f"{request.path}?date={b.date.isoformat()}")
    today = timezone.localdate()
    qs = _scope(request, v.bookings.all()).select_related("staff__user", "order").prefetch_related("items")
    if request.role == "staff":
        qs = qs.filter(staff=request.staff)
    view = request.GET.get("view", "upcoming")
    d = request.GET.get("date", "")
    status = request.GET.get("status", "")
    who = request.GET.get("staff", "")
    if d:
        qs, view = qs.filter(date=d), "day"
    elif view == "past":
        qs = qs.filter(date__lt=today).order_by("-date", "-time")
    else:
        view = "upcoming"
        qs = qs.filter(date__gte=today)
    if status in Booking.Status.values:
        qs = qs.filter(status=status)
    elif view == "upcoming":
        qs = qs.exclude(status__in=[Booking.Status.CANCELLED, Booking.Status.NO_SHOW])
    if who and request.role != "staff":
        qs = qs.filter(staff_id=who) if who != "none" else qs.filter(staff__isnull=True)
    page, qs_prefix = paginate(request, qs, 30)
    pending = _scope(request, v.bookings.filter(status=Booking.Status.REQUESTED, date__gte=today))
    if request.role == "staff":
        pending = pending.filter(staff=request.staff)
    return render(request, "pos/bookings.html", _ctx(request, form=form, bookings=page, page=page, qs=qs_prefix, view=view,
                                                     date=d, status=status, who=who, statuses=Booking.Status.choices,
                                                     team=_team(v), can_edit=can_edit, pending=pending.count(), today=today))


@till_required
def booking_edit(request, pk):
    from .forms import BookingForm
    b = get_object_or_404(request.vendor.bookings, pk=pk)
    form = BookingForm(request.POST or None, instance=b, vendor=request.vendor)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Booking updated.")
        return redirect("pos_bookings")
    return render(request, "pos/booking_form.html", _ctx(request, form=form, b=b))


@till_required
@require_POST
def booking_status(request, pk):
    b = get_object_or_404(request.vendor.bookings, pk=pk)
    target = request.POST.get("status")
    if target in Booking.Status.values:
        b.status = target
        b.save(update_fields=["status"])
    return redirect(request.POST.get("next") or "pos_bookings")


@till_required
@require_POST
def booking_assign(request, pk):
    """Give an incoming booking to a staff member. It then shows in their bookings."""
    b = get_object_or_404(request.vendor.bookings, pk=pk)
    sid = request.POST.get("staff") or ""
    b.staff = request.vendor.staff.filter(pk=sid, is_active=True, role=Staff.Role.STAFF).first() if sid else None
    b.save(update_fields=["staff"])
    if b.order_id and b.order.paid_at is None and b.staff:      # ticket already open: move it to them too
        b.order.items.update(staff=b.staff)
    if b.staff:
        messages.success(request, f"{b.name}'s booking is now with {b.staff.name}.")
    return redirect(request.POST.get("next") or "pos_bookings")


@till_required
@require_POST
def booking_start(request, pk):
    """Client has arrived: open a ticket with their service and stylist already on it."""
    b = get_object_or_404(request.vendor.bookings.select_related("staff").prefetch_related("items__service"), pk=pk)
    if b.order_id and b.order.paid_at is None:
        request.session[SESSION_ORDER] = str(b.order_id)
        return redirect("pos_home")
    if b.order_id:
        messages.info(request, "That booking has already been paid for.")
        return redirect("pos_receipt", pk=b.order_id)
    order = Order.objects.create(vendor=request.vendor, branch=b.branch or request.vendor.main_branch(), cashier=request.user,
                                 source=Order.Source.BOOKING, customer_name=b.name, customer_phone=b.phone, notes=b.note[:200])
    for line in b.items.all():
        if line.service and not line.service.price_on_request:
            OrderItem.add(order, line.service, staff=b.staff)
    b.order = order
    if b.status == Booking.Status.REQUESTED:
        b.status = Booking.Status.CONFIRMED
    b.save(update_fields=["order", "status"])
    request.session[SESSION_ORDER] = str(order.pk)
    return redirect("pos_home")


@login_required
def bookings_badge(request):
    """Sidebar badge: bookings waiting to be confirmed. Empty (not the locked page) when the POS isn't paid for."""
    if not _resolve_pos_user(request) or not request.vendor.pos_active:
        return HttpResponse("")
    qs = request.vendor.bookings.filter(status=Booking.Status.REQUESTED, date__gte=timezone.localdate())
    if request.role == "staff":
        qs = qs.filter(staff=request.staff)
    n = qs.count()
    return HttpResponse(str(n) if n else "")


# ── Team: staff records, earnings and payouts (owner) ──────────────────

def _period_lines(request, st):
    """This person's paid services in the chosen window (default: this month)."""
    today = timezone.localdate()
    d_from = request.GET.get("from") or today.replace(day=1).isoformat()
    d_to = request.GET.get("to") or today.isoformat()
    lines = st.earned_lines().filter(order__paid_at__date__gte=d_from, order__paid_at__date__lte=d_to)
    return lines, d_from, d_to


@owner_pos_required
def staff_list(request):
    from .forms import StaffForm, save_staff_services
    v = request.vendor
    services = list(v.items.filter(price_on_request=False).order_by("category__order", "name"))
    form = StaffForm(request.POST or None, vendor=v, branch=getattr(request, "write_branch", None))
    if request.method == "POST" and form.is_valid():
        st = form.save(vendor=v)
        save_staff_services(st, request.POST, services)
        messages.success(request, f"{st.name} added as {st.get_role_display().lower()}. They log in with {st.user.email}.")
        return redirect("pos_staff_detail", pk=st.pk)
    team = list(_scope(request, v.staff.all()).select_related("user", "branch").annotate(n_services=Count("service_links")))
    month = timezone.localdate().replace(day=1)
    month_rows = {r["id"]: r for r in staff_earnings(OrderItem.objects.filter(order__vendor=v, order__paid_at__date__gte=month)
                                                     .exclude(order__status=Order.Status.CANCELLED))}
    unpaid = {r["staff_id"]: r["t"] for r in OrderItem.objects.filter(order__vendor=v, order__paid_at__isnull=False, payout__isnull=True)
              .exclude(order__status=Order.Status.CANCELLED).values("staff_id").annotate(t=Sum("commission"))}
    for s in team:
        s.month = month_rows.get(s.pk)
        s.unpaid = unpaid.get(s.pk) or 0
    return render(request, "pos/staff.html", _ctx(request, form=form, team=team, services=services,
                                                  total_unpaid=sum(s.unpaid for s in team)))


@owner_pos_required
def staff_edit(request, pk):
    from .forms import StaffForm, save_staff_services
    v = request.vendor
    st = get_object_or_404(Staff.objects.select_related("user"), pk=pk, vendor=v)
    services = list(v.items.filter(price_on_request=False).order_by("category__order", "name"))
    form = StaffForm(request.POST or None, instance=st, vendor=v)
    if request.method == "POST" and form.is_valid():
        form.save(vendor=v)
        save_staff_services(st, request.POST, services)
        messages.success(request, f"{st.name} updated.")
        return redirect("pos_staff_detail", pk=st.pk)
    links = {l.service_id: l for l in st.service_links.all()}
    return render(request, "pos/staff_form.html", _ctx(request, form=form, st=st, services=services, links=links))


@owner_pos_required
def staff_detail(request, pk):
    """HR card: who they are, what they earned, what is still owed, and paying it."""
    from .forms import PayoutForm
    v = request.vendor
    st = get_object_or_404(Staff.objects.select_related("user", "branch"), pk=pk, vendor=v)
    lines, d_from, d_to = _period_lines(request, st)
    period = lines.aggregate(n=Sum("qty"), sales=Sum("line_total"), c=Sum("commission"))
    unpaid = st.unpaid_lines().select_related("order").order_by("order__paid_at")
    form = PayoutForm()
    return render(request, "pos/staff_detail.html", _ctx(
        request, st=st, period=period, d_from=d_from, d_to=d_to, unpaid=unpaid[:200], balance=st.balance(),
        unpaid_count=unpaid.count(), form=form, payouts=st.payouts.all()[:12],
        links=st.service_links.select_related("service"), shifts=st.shifts.filter(date__gte=timezone.localdate())[:10],
        top=lines.values("name").annotate(n=Sum("qty"), t=Sum("line_total")).order_by("-t")[:6]))


@owner_pos_required
@require_POST
def staff_pay(request, pk):
    from .forms import PayoutForm
    st = get_object_or_404(Staff, pk=pk, vendor=request.vendor)
    form = PayoutForm(request.POST)
    ids = request.POST.getlist("line")
    if not form.is_valid():
        messages.error(request, "Check the payout details and try again.")
        return redirect("pos_staff_detail", pk=st.pk)
    d = form.cleaned_data
    p = StaffPayout.pay(st, ids, request.user, d["method"], d.get("reference") or "", d.get("note") or "",
                        bonus=d.get("bonus") or 0, deduction=d.get("deduction") or 0)
    if p is None:
        messages.error(request, "Tick at least one service to pay (or enter a bonus).")
        return redirect("pos_staff_detail", pk=st.pk)
    messages.success(request, f"Paid {st.name} KES {p.amount:,.0f}. {st.name} can see the payslip on their profile.")
    return redirect("pos_payout", pk=p.pk)


@owner_pos_required
@require_POST
def staff_toggle(request, pk):
    st = get_object_or_404(Staff, pk=pk, vendor=request.vendor)
    st.is_active = not st.is_active
    st.save(update_fields=["is_active"])
    st.user.is_active = st.is_active
    st.user.save(update_fields=["is_active"])
    messages.success(request, f"{st.name} {'can log in again' if st.is_active else 'is disabled and can no longer log in'}.")
    return redirect("pos_staff")


@owner_pos_required
def payouts(request):
    qs = request.vendor.payouts.select_related("staff__user", "paid_by")
    who = request.GET.get("staff", "")
    if who:
        qs = qs.filter(staff_id=who)
    page, qs_prefix = paginate(request, qs, 30)
    return render(request, "pos/payouts.html", _ctx(request, payouts=page, page=page, qs=qs_prefix, who=who,
                                                    team=list(request.vendor.staff.select_related("user")),
                                                    total=qs.aggregate(t=Sum("amount"))["t"] or 0))


# ── Staff shifts (rota) ───────────────────────────────────────────────

def _today_board(request, v, today):
    """Who is in today, who is absent or on leave, and who has nothing planned."""
    team = list(_scope(request, v.staff.filter(is_active=True)).select_related("user"))
    todays = {}
    for sh in _scope(request, v.staff_shifts.filter(date=today)).select_related("staff__user"):
        todays.setdefault(sh.staff_id, []).append(sh)
    board = {"working": [], "absent": [], "leave": [], "off": []}
    for st in team:
        mine = todays.get(st.pk, [])
        if any(x.status == StaffShift.Status.LEAVE for x in mine):
            board["leave"].append(st)
        elif mine and all(x.status == StaffShift.Status.ABSENT for x in mine):
            board["absent"].append(st)
        elif mine:
            board["working"].append((st, [x for x in mine if x.status != StaffShift.Status.ABSENT]))
        else:
            board["off"].append(st)
    return team, board


def _month_calendar(shifts_by_date, month_start, today):
    """Weeks (Mon–Sun) of day cells for one month; days outside the month are None."""
    import calendar
    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(month_start.year, month_start.month):
        weeks.append([{"date": d, "in_month": d.month == month_start.month, "today": d == today,
                       "shifts": shifts_by_date.get(d, [])} for d in week])
    return weeks


@owner_pos_required
def shifts(request):
    """Today's board and the staff list; one person's shifts on a month calendar."""
    from .forms import StaffShiftForm
    v = request.vendor
    today = timezone.localdate()
    who = v.staff.filter(pk=request.GET.get("staff")).select_related("user").first() if request.GET.get("staff") else None
    initial = {"date": today, "starts": "08:00", "ends": "17:00"}
    if who:
        initial["staff"] = who.pk
    form = StaffShiftForm(request.POST or None, vendor=v, initial=initial)
    if request.method == "POST" and form.is_valid():
        s = form.save(commit=False)
        s.vendor = v
        s.branch = s.staff.branch or v.main_branch()
        s.save()
        repeat = request.POST.get("repeat") == "on"
        if repeat:                                   # same slot every day to the end of that week
            for i in range(1, 7 - s.date.weekday()):
                StaffShift.objects.get_or_create(vendor=v, staff=s.staff, date=s.date + timedelta(days=i),
                                                 defaults={"starts": s.starts, "ends": s.ends, "branch": s.branch, "note": s.note})
        messages.success(request, f"{s.staff.name} on {s.date:%a %d %b}, {s.starts:%H:%M}–{s.ends:%H:%M}" + (" and the rest of that week." if repeat else "."))
        back = request.POST.get("next") or ""
        return redirect(back if back.startswith("/pos/shifts/") else f"{request.path}?staff={s.staff_id}&month={s.date:%Y-%m}")
    team, board = _today_board(request, v, today)
    ctx = _ctx(request, form=form, today=today, board=board, team=team, who=who, statuses=StaffShift.Status.choices)
    if who:
        try:
            month = timezone.datetime.strptime(request.GET.get("month", ""), "%Y-%m").date()
        except ValueError:
            month = today.replace(day=1)
        nxt = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        rows = list(who.shifts.filter(date__gte=month, date__lt=nxt))
        by_date = {}
        for sh in rows:
            by_date.setdefault(sh.date, []).append(sh)
        worked = [x for x in rows if x.status in (StaffShift.Status.WORKED, StaffShift.Status.PLANNED)]
        ctx.update(month=month, weeks=_month_calendar(by_date, month, today),
                   prev_month=(month - timedelta(days=1)).strftime("%Y-%m"), next_month=nxt.strftime("%Y-%m"),
                   month_stats={"shifts": len(worked), "hours": round(sum(x.hours for x in worked), 1),
                                "absent": sum(1 for x in rows if x.status == StaffShift.Status.ABSENT),
                                "leave": sum(1 for x in rows if x.status == StaffShift.Status.LEAVE)})
        return render(request, "pos/shifts_person.html", ctx)
    return render(request, "pos/shifts.html", ctx)


@owner_pos_required
@require_POST
def shift_status(request, pk):
    s = get_object_or_404(StaffShift, pk=pk, vendor=request.vendor)
    target = request.POST.get("status")
    if target == "delete":
        s.delete()
    elif target in StaffShift.Status.values:
        s.status = target
        s.save(update_fields=["status"])
    back = request.POST.get("next") or ""
    return redirect(back if back.startswith("/pos/shifts/") else f"/pos/shifts/?staff={s.staff_id}&month={s.date:%Y-%m}")


# ── Branches (owner) ──────────────────────────────────────────────────

@owner_branch_admin
def branches(request):
    """Add outlets, rename them, see each one's POS expiry and renew it."""
    v = request.vendor
    if not v.can_use_branches:
        raise Http404
    site = SiteSettings.get()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            name = (request.POST.get("name") or "").strip()[:40]
            location = (request.POST.get("location") or "").strip()[:80]
            if not name:
                messages.error(request, "Give the branch a name.")
            elif v.branches.filter(name__iexact=name).exists():
                messages.error(request, f"You already have a branch called {name}.")
            else:
                b = Branch.objects.create(vendor=v, name=name, location=location)
                messages.success(request, f"{b.name} added. Pay for it below to switch it on.")
                if not v.branches_enabled:
                    v.branches_enabled = True
                    v.save(update_fields=["branches_enabled"])
        elif action == "rename":
            b = v.branches.filter(pk=request.POST.get("branch")).first()
            if b:
                name = (request.POST.get("name") or b.name).strip()[:40]
                if name and not v.branches.filter(name__iexact=name).exclude(pk=b.pk).exists():
                    b.name = name
                b.location = (request.POST.get("location") or "").strip()[:80]
                b.save(update_fields=["name", "location"])
                messages.success(request, f"{b.name} updated.")
        elif action == "close":
            b = v.branches.filter(pk=request.POST.get("branch"), is_main=False).first()
            if b:
                b.is_active = False
                b.save(update_fields=["is_active"])
                messages.warning(request, f"{b.name} closed. Its sales history stays in your reports.")
        return redirect("pos_branches")
    rows = list(v.branches.all())
    now = timezone.now()
    for b in rows:
        b.staff_count = b.staff.filter(is_active=True).count()
        b.own_prices = b.prices.count()
        base = b.pos_expires_at if (b.pos_expires_at and b.pos_expires_at > now) else now
        b.renew_to = base + timedelta(days=30)    # a renewal goes on top of whatever is left
    return render(request, "pos/branches.html", _ctx(request, rows=rows, site=site, fee=site.pos_fee))


# ── Insights — owner and cashier ───────────────────────────────────────

@till_required
def insights(request):
    from django.conf import settings as dj
    from . import insights as ai
    v = request.vendor
    days = 30 if request.GET.get("days") != "90" else 90
    today = timezone.localdate()
    branch = getattr(request, "branch", None)
    latest = v.insight_reports.filter(branch=branch, days=days).first()
    regen_used = v.insight_reports.filter(created_at__date=today).count()
    if request.method == "POST" and request.POST.get("action") == "regenerate":
        if regen_used >= dj.INSIGHTS_REGEN_PER_DAY:
            messages.warning(request, f"You can refresh insights {dj.INSIGHTS_REGEN_PER_DAY} times a day. Try again tomorrow.")
        else:
            report, snap, engine = ai.generate_report(v, days, branch)
            InsightReport.objects.create(vendor=v, branch=branch, days=days, report=report,
                                         snapshot=json.loads(json.dumps(snap, default=str)), engine=engine)
        return redirect(f"{request.path}?days={days}")
    if latest is None or latest.created_at.date() < today:
        if regen_used < dj.INSIGHTS_REGEN_PER_DAY or latest is None:
            report, snap, engine = ai.generate_report(v, days, branch)
            latest = InsightReport.objects.create(vendor=v, branch=branch, days=days, report=report,
                                                  snapshot=json.loads(json.dumps(snap, default=str)), engine=engine)
    asked_today = v.insight_questions.filter(created_at__date=today).count()
    return render(request, "pos/insights.html", _ctx(request, rep=latest, r=latest.report, days=days, ai_on=ai.ai_available(),
                                                     regen_left=max(0, dj.INSIGHTS_REGEN_PER_DAY - regen_used),
                                                     ask_left=max(0, dj.INSIGHTS_ASK_PER_DAY - asked_today),
                                                     questions=v.insight_questions.all()[:8]))


@till_required
@require_POST
def insights_ask(request):
    from django.conf import settings as dj
    from . import insights as ai
    v = request.vendor
    q = (request.POST.get("q") or "").strip()[:600]
    if not q:
        return HttpResponse("")
    if v.insight_questions.filter(created_at__date=timezone.localdate()).count() >= dj.INSIGHTS_ASK_PER_DAY:
        return render(request, "pos/_insight_answer.html", {"q": q, "a": f"Daily question limit reached ({dj.INSIGHTS_ASK_PER_DAY}). Try again tomorrow.", "engine": "limit"})
    history = []
    for prev in reversed(list(v.insight_questions.all()[:3])):
        history += [{"role": "user", "content": prev.question}, {"role": "assistant", "content": prev.answer}]
    a, engine = ai.ask(v, q, history, branch=getattr(request, "branch", None))
    InsightQuestion.objects.create(vendor=v, asked_by=request.user, question=q, answer=a, engine=engine)
    return render(request, "pos/_insight_answer.html", {"q": q, "a": a, "engine": engine})
