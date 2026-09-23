"""Insights: analysis computed entirely from the business's own POS data (no external services).
build_snapshot() gathers the numbers; generate_report() turns them into insights, service moves, a forecast and tips;
ask() answers plain-language questions by matching them to the snapshot."""
import re
from datetime import timedelta

from django.db.models import Avg, Count, Sum
from django.db.models.functions import ExtractHour, ExtractWeekDay, TruncDate
from django.utils import timezone

from .models import Expense, OrderItem

ENGINE = "beautyflow-insights"
WD = {1: "Sunday", 2: "Monday", 3: "Tuesday", 4: "Wednesday", 5: "Thursday", 6: "Friday", 7: "Saturday"}


def _f(x):
    return float(x or 0)


def kes(x):
    return f"KES {x:,.0f}"


def build_snapshot(vendor, days=30, branch=None):
    now = timezone.now(); today = timezone.localdate()
    start = now - timedelta(days=days); prev_start = now - timedelta(days=2 * days)
    orders, expenses = vendor.orders.all(), vendor.expenses.all()
    if branch is not None:
        orders, expenses = orders.filter(branch=branch), expenses.filter(branch=branch)
    paid = orders.filter(paid_at__gte=start).exclude(status="cancelled")
    prev = orders.filter(paid_at__gte=prev_start, paid_at__lt=start).exclude(status="cancelled")
    cur = paid.aggregate(sales_total=Sum("total"), n=Count("id"), avg_ticket=Avg("total"))
    pv = prev.aggregate(sales_total=Sum("total"), n=Count("id"), avg_ticket=Avg("total"))
    by_day = [{"date": r["d"], "sales": _f(r["t"]), "orders": r["n"]} for r in paid.annotate(d=TruncDate("paid_at")).values("d").annotate(t=Sum("total"), n=Count("id")).order_by("d")]
    by_hour = {int(r["h"]): _f(r["t"]) for r in paid.annotate(h=ExtractHour("paid_at")).values("h").annotate(t=Sum("total"))}
    by_weekday = {WD[r["w"]]: _f(r["t"]) for r in paid.annotate(w=ExtractWeekDay("paid_at")).values("w").annotate(t=Sum("total"))}
    wd_counts = {WD[r["w"]]: r["n"] for r in paid.annotate(w=ExtractWeekDay("paid_at")).values("w").annotate(n=Count("id"))}
    items = list(OrderItem.objects.filter(order__in=paid).values("name").annotate(qty=Sum("qty"), revenue=Sum("line_total")).order_by("-revenue"))
    prev_items = {r["name"]: r["qty"] for r in OrderItem.objects.filter(order__in=prev).values("name").annotate(qty=Sum("qty"))}
    sold_names = {i["name"] for i in items}
    never_sold = list(vendor.items.filter(is_available=True).exclude(name__in=sold_names).values_list("name", "price"))
    methods = {r["payment_method"] or "other": _f(r["t"]) for r in paid.values("payment_method").annotate(t=Sum("total"))}
    prev_methods = {r["payment_method"] or "other": _f(r["t"]) for r in prev.values("payment_method").annotate(t=Sum("total"))}
    sources = {r["source"]: r["n"] for r in paid.values("source").annotate(n=Count("id"))}
    exp = expenses.filter(date__gte=start.date())
    exp_total = _f(exp.aggregate(t=Sum("amount"))["t"])
    exp_cat = {r["category"]: _f(r["t"]) for r in exp.values("category").annotate(t=Sum("amount"))}
    prev_exp = _f(expenses.filter(date__gte=prev_start.date(), date__lt=start.date()).aggregate(t=Sum("amount"))["t"])
    team = [{"name": r["staff__user__first_name"] or "—", "sales": _f(r["t"]), "orders": r["n"] or 0}
            for r in OrderItem.objects.filter(order__in=paid, staff__isnull=False).values("staff__user__first_name")
            .annotate(t=Sum("line_total"), n=Sum("qty")).order_by("-t")]
    bookings = vendor.bookings.filter(created_at__gte=start)
    if branch is not None:
        bookings = bookings.filter(branch=branch)
    return {
        "business": {"name": vendor.brand_name + (f" · {branch.name}" if branch is not None else ""), "period_days": days, "today": today, "services": vendor.items.filter(is_available=True).count()},
        "sales": {"total": _f(cur["sales_total"]), "orders": cur["n"] or 0, "avg_ticket": _f(cur["avg_ticket"]),
                  "prev_total": _f(pv["sales_total"]), "prev_orders": pv["n"] or 0, "prev_avg_ticket": _f(pv["avg_ticket"]),
                  "by_day": by_day, "by_hour": by_hour, "by_weekday": by_weekday, "weekday_counts": wd_counts,
                  "methods": methods, "prev_methods": prev_methods, "sources": sources},
        "items": {"all": [{"name": i["name"], "qty": i["qty"], "revenue": _f(i["revenue"]), "prev_qty": prev_items.get(i["name"], 0)} for i in items],
                  "never_sold": [{"name": n, "price": _f(p)} for n, p in never_sold]},
        "expenses": {"total": exp_total, "prev_total": prev_exp, "by_category": exp_cat, "profit": _f(cur["sales_total"]) - exp_total, "count": exp.count()},
        "team": team,
        "bookings": {"total": bookings.count(), "no_show": bookings.filter(status="no_show").count(),
                     "cancelled": bookings.filter(status="cancelled").count(), "online": bookings.filter(source="online").count()},
        "customers": {"total": vendor.customers.count(), "repeat": vendor.customers.filter(orders_count__gte=2).count(),
                      "reviews": vendor.review_count(), "rating": round(float(vendor.rating() or 0), 1),
                      "inquiries": vendor.inquiries.filter(created_at__gte=start).count(), "bookings": bookings.count()},
    }


def _pct(cur, prev):
    return ((cur - prev) / prev * 100) if prev else None


def generate_report(vendor, days=30, branch=None):
    s = build_snapshot(vendor, days, branch)
    S, I, E, C = s["sales"], s["items"], s["expenses"], s["customers"]
    ins, moves = [], []
    sales, prev = S["total"], S["prev_total"]
    n_days = max(len(S["by_day"]), 1)
    if S["orders"] == 0:
        return {"headline": "No paid sales in this period yet — ring a few through the POS and the insights will build up.", "health_score": 30, "insights": [],
                "menu_moves": [], "forecast": {"next_7_days_sales": 0, "confidence": "low", "basis": "No sales data."},
                "staffing_tip": "Start ringing sales through the POS so we can see your busy hours.", "marketing_tip": "Share your booking link on WhatsApp status to fill the first slots."}, s, ENGINE

    # 1. Sales trend
    ch = _pct(sales, prev)
    if ch is not None:
        ins.append({"title": "Sales are " + ("up" if ch >= 0 else "down") + " vs the previous period", "metric": f"{ch:+.0f}%", "kind": "win" if ch >= 5 else ("risk" if ch <= -5 else "trend"),
                    "detail": f"{kes(sales)} from {S['orders']} visits, compared with {kes(prev)} from {S['prev_orders']} visits before that.",
                    "action": "Repeat what changed — same offers, same hours, same staff." if ch >= 5 else ("Check your slow days below and run a targeted offer on them." if ch <= -5 else "Steady. Try one promo to nudge it up.")})
    # 2. Average ticket
    if S["prev_avg_ticket"]:
        tch = _pct(S["avg_ticket"], S["prev_avg_ticket"])
        if tch is not None and abs(tch) >= 5:
            ins.append({"title": "Clients are spending " + ("more" if tch > 0 else "less") + " per visit", "metric": kes(S["avg_ticket"]), "kind": "win" if tch > 0 else "opportunity",
                        "detail": f"Average visit is {kes(S['avg_ticket'])}, {tch:+.0f}% vs {kes(S['prev_avg_ticket'])} before.",
                        "action": "Keep suggesting add-ons (treatments, nail art, a wash)." if tch > 0 else "Offer an add-on with your top service — a treatment or quick polish adds up."})
    # 3. Best day / hour
    if S["by_weekday"]:
        best = max(S["by_weekday"], key=S["by_weekday"].get); worst = min(S["by_weekday"], key=S["by_weekday"].get)
        ins.append({"title": f"{best} is your money day; {worst} is the quietest", "metric": kes(S["by_weekday"][best]), "kind": "trend",
                    "detail": f"{best} brought {kes(S['by_weekday'][best])} vs {kes(S['by_weekday'][worst])} on {worst} over the period.",
                    "action": f"Run a '{worst} special' (e.g. 10% off a popular service) and have your strongest team in on {best}."})
    if S["by_hour"]:
        top_h = sorted(S["by_hour"], key=S["by_hour"].get, reverse=True)[:2]
        share = sum(S["by_hour"][h] for h in top_h) / sales * 100 if sales else 0
        ins.append({"title": "Peak hours", "metric": " & ".join(f"{h:02d}:00" for h in sorted(top_h)), "kind": "trend",
                    "detail": f"These two hours bring {share:.0f}% of your revenue.", "action": "Have your full team in before the peak and push bookings into the quieter hours."})
    # 4. Items: movers and dead stock
    allitems = I["all"]
    if allitems:
        top = allitems[0]; share = top["revenue"] / sales * 100 if sales else 0
        ins.append({"title": f"{top['name']} carries the business", "metric": f"{share:.0f}% of sales", "kind": "win" if share < 50 else "risk",
                    "detail": f"{top['qty']} done for {kes(top['revenue'])}." + (" That's a lot of dependence on one service." if share >= 50 else ""),
                    "action": "Feature it first on your page and price it confidently." if share < 50 else "Push a second signature service so one slow week doesn't sink the month."})
        moves.append({"item": top["name"], "move": "promote", "why": f"Top seller — {kes(top['revenue'])}"})
        risers = sorted([i for i in allitems if i["prev_qty"] and i["qty"] >= i["prev_qty"] * 1.3 and i["qty"] >= 5], key=lambda i: i["qty"] - i["prev_qty"], reverse=True)[:2]
        fallers = sorted([i for i in allitems if i["prev_qty"] >= 5 and i["qty"] <= i["prev_qty"] * 0.7], key=lambda i: i["prev_qty"] - i["qty"], reverse=True)[:2]
        for r in risers:
            moves.append({"item": r["name"], "move": "raise_price", "why": f"Demand up {r['prev_qty']} → {r['qty']}; a small price rise will hold"})
        for fl in fallers:
            moves.append({"item": fl["name"], "move": "bundle", "why": f"Sales fell {fl['prev_qty']} → {fl['qty']}; bundle with a best seller"})
        if len(allitems) >= 6:
            low = allitems[-1]
            moves.append({"item": low["name"], "move": "keep" if low["qty"] >= 3 else "remove", "why": f"Only {low['qty']} done"})
    if I["never_sold"]:
        ins.append({"title": f"{len(I['never_sold'])} services had no bookings or sales", "metric": str(len(I["never_sold"])), "kind": "opportunity",
                    "detail": ", ".join(x["name"] for x in I["never_sold"][:5]) + ("…" if len(I["never_sold"]) > 5 else "") + ". A long price list makes it harder for clients to choose.",
                    "action": "Remove them, put them on offer, or add a photo so clients understand them."})
        for x in I["never_sold"][:2]:
            moves.append({"item": x["name"], "move": "remove", "why": "Zero sales this period"})
    # 5. Payments
    if S["methods"]:
        mp = S["methods"].get("mpesa", 0); mshare = mp / sales * 100 if sales else 0
        prev_mp = S["prev_methods"].get("mpesa", 0); prev_share = prev_mp / prev * 100 if prev else None
        if prev_share is not None and abs(mshare - prev_share) >= 10:
            ins.append({"title": "M-Pesa share shifted", "metric": f"{mshare:.0f}%", "kind": "trend", "detail": f"M-Pesa is now {mshare:.0f}% of sales (was {prev_share:.0f}%).", "action": "Keep the till number at reception and on receipts; reconcile M-Pesa daily."})
    # 6. Expenses & profit
    if E["count"]:
        margin = E["profit"] / sales * 100 if sales else 0
        big = max(E["by_category"], key=E["by_category"].get) if E["by_category"] else None
        ech = _pct(E["total"], E["prev_total"])
        ins.append({"title": "Profit margin", "metric": f"{margin:.0f}%", "kind": "win" if margin >= 25 else ("risk" if margin < 10 else "trend"),
                    "detail": f"{kes(sales)} sales − {kes(E['total'])} expenses = {kes(E['profit'])}." + (f" Biggest cost: {dict(Expense.Category.choices).get(big, big)} {kes(E['by_category'][big])}." if big else "") + (f" Expenses {ech:+.0f}% vs before." if ech is not None else ""),
                    "action": "Healthy — consider a small price rise on your top service." if margin >= 25 else "Renegotiate the biggest cost line and review commission rates on low-margin services."})
    else:
        ins.append({"title": "No expenses recorded", "metric": "—", "kind": "opportunity", "detail": "Without costs we can't show profit.", "action": "Record products, rent and wages under Expenses — it takes a minute a day."})
    # 7. Customers
    if C["total"]:
        rep = C["repeat"] / C["total"] * 100
        ins.append({"title": "Repeat clients", "metric": f"{rep:.0f}%", "kind": "win" if rep >= 30 else "opportunity",
                    "detail": f"{C['repeat']} of {C['total']} known clients came back. {C['inquiries']} inquiries and {C['bookings']} bookings this period.",
                    "action": "Send one WhatsApp offer to past clients this week." if rep < 30 else "Reward the regulars — a loyalty discount keeps them coming back."})
    B = s["bookings"]
    if B["total"] >= 5:
        lost = (B["no_show"] + B["cancelled"]) / B["total"] * 100
        if lost >= 15:
            ins.append({"title": "Bookings falling through", "metric": f"{lost:.0f}%", "kind": "risk",
                        "detail": f"{B['no_show']} no-shows and {B['cancelled']} cancellations out of {B['total']} bookings.",
                        "action": "Confirm every booking on WhatsApp the day before; ask for a deposit on long services."})
    # 8. Team
    if len(s["team"]) >= 2:
        t0, t1 = s["team"][0], s["team"][-1]
        ins.append({"title": f"{t0['name']} brings in the most", "metric": kes(t0["sales"]), "kind": "trend", "detail": f"{t0['orders']} services vs {t1['orders']} for {t1['name']}.", "action": "Pair your strongest and newest staff on the same shift, and route walk-ins fairly."})
    # Forecast: same-weekday averages over the period
    per_wd = {}
    for d in S["by_day"]:
        per_wd.setdefault(d["date"].strftime("%A"), []).append(d["sales"])
    daily_avg = sales / n_days
    fc = 0.0
    for i in range(1, 8):
        name = (s["business"]["today"] + timedelta(days=i)).strftime("%A")
        vals = per_wd.get(name)
        fc += (sum(vals) / len(vals)) if vals else daily_avg
    conf = "high" if n_days >= 21 else ("medium" if n_days >= 10 else "low")
    # Health score
    score = 50
    if ch is not None: score += max(-20, min(20, ch / 2))
    if E["count"]: score += 10 if (E["profit"] / sales if sales else 0) >= 0.2 else -10
    if C["total"]: score += 10 if C["repeat"] / C["total"] >= 0.3 else 0
    if I["never_sold"] and len(I["never_sold"]) > 5: score -= 5
    score = int(max(5, min(98, score)))
    kinds = {"risk": 0, "win": 1, "opportunity": 2, "trend": 3}
    ins.sort(key=lambda x: kinds[x["kind"]])
    head = f"{kes(sales)} from {S['orders']} visits in the last {days} days" + (f", {ch:+.0f}% vs the period before" if ch is not None else "") + (f"; {kes(E['profit'])} profit after expenses." if E["count"] else ".")
    best_day = max(S["by_weekday"], key=S["by_weekday"].get) if S["by_weekday"] else None
    peak = max(S["by_hour"], key=S["by_hour"].get) if S["by_hour"] else None
    report = {"headline": head, "health_score": score, "insights": ins[:7], "menu_moves": moves[:6],
              "forecast": {"next_7_days_sales": round(fc), "confidence": conf, "basis": f"Average of each weekday over the last {n_days} trading day{'s' if n_days != 1 else ''}."},
              "staffing_tip": (f"Schedule your best staff for {best_day} and around {peak:02d}:00; a lighter crew on quiet days." if best_day and peak is not None else "Ring all sales through the POS so we can map your busy hours."),
              "marketing_tip": ("Post your booking link on WhatsApp status weekly; message past clients before " + (best_day or "the weekend") + " with one offer.")}
    return report, s, ENGINE


# ── Ask your data ──────────────────────────────────────────────────────

def ask(vendor, question, history=None, days=30, branch=None):
    q = question.lower()
    s = build_snapshot(vendor, days, branch); S, I, E, C = s["sales"], s["items"], s["expenses"], s["customers"]
    # period override
    if re.search(r"\b(week|7 days)\b", q):
        s = build_snapshot(vendor, 7, branch); S, I, E, C = s["sales"], s["items"], s["expenses"], s["customers"]; span = "the last 7 days"
    elif re.search(r"\b(90|quarter|3 months)\b", q):
        s = build_snapshot(vendor, 90, branch); S, I, E, C = s["sales"], s["items"], s["expenses"], s["customers"]; span = "the last 90 days"
    elif "today" in q:
        s = build_snapshot(vendor, 1, branch); S, I, E, C = s["sales"], s["items"], s["expenses"], s["customers"]; span = "today"
    else:
        span = f"the last {days} days"
    if S["orders"] == 0:
        return f"No paid sales in {span} yet, so there's nothing to analyse for that question.", ENGINE
    # intents
    if re.search(r"m-?pesa|mpesa", q):
        v = S["methods"].get("mpesa", 0); return f"M-Pesa brought {kes(v)} in {span} — {v / S['total'] * 100:.0f}% of your {kes(S['total'])} sales. Cash: {kes(S['methods'].get('cash', 0))}, Card: {kes(S['methods'].get('card', 0))}.", ENGINE
    if re.search(r"\bcash\b", q):
        v = S["methods"].get("cash", 0); return f"Cash sales were {kes(v)} in {span} ({v / S['total'] * 100:.0f}% of sales).", ENGINE
    if re.search(r"promo|offer|discount|slow|quiet", q):
        if S["by_weekday"]:
            worst = min(S["by_weekday"], key=S["by_weekday"].get); best = max(S["by_weekday"], key=S["by_weekday"].get)
            return f"Run it on {worst} — your quietest day ({kes(S['by_weekday'][worst])} in {span}, vs {kes(S['by_weekday'][best])} on {best}). Announce it on WhatsApp status the evening before and message past clients.", ENGINE
    if re.search(r"best day|which day|busiest day|top day", q):
        best = max(S["by_weekday"], key=S["by_weekday"].get); return f"{best} is your best day: {kes(S['by_weekday'][best])} across {S['weekday_counts'].get(best, 0)} visits in {span}.", ENGINE
    if re.search(r"hour|time of day|peak|busiest", q):
        top = sorted(S["by_hour"], key=S["by_hour"].get, reverse=True)[:3]; return "Your busiest hours: " + ", ".join(f"{h:02d}:00 ({kes(S['by_hour'][h])})" for h in top) + f" in {span}.", ENGINE
    if re.search(r"profit|margin|loss", q):
        if not E["count"]: return "You haven't recorded any expenses yet, so I can't calculate profit. Add them under Expenses.", ENGINE
        return f"Sales {kes(S['total'])} − expenses {kes(E['total'])} = {kes(E['profit'])} profit in {span} ({E['profit'] / S['total'] * 100:.0f}% margin).", ENGINE
    if re.search(r"expense|cost|spend(ing)? on|rent|salar", q):
        if not E["count"]: return "No expenses recorded for that period.", ENGINE
        cats = sorted(E["by_category"].items(), key=lambda kv: kv[1], reverse=True); labels = dict(Expense.Category.choices)
        return f"Expenses in {span}: {kes(E['total'])}. " + "; ".join(f"{labels.get(k, k)} {kes(v)}" for k, v in cats[:4]) + ".", ENGINE
    for it in I["all"]:
        if it["name"].lower() in q:
            share = it["revenue"] / S["total"] * 100
            verdict = "worth keeping and promoting" if share >= 8 else ("a solid add-on" if it["qty"] >= 5 else "a candidate to remove or put on offer")
            return f"{it['name']}: {it['qty']} done, {kes(it['revenue'])} ({share:.0f}% of sales) in {span}" + (f"; last period {it['prev_qty']} done" if it["prev_qty"] else "") + f". It's {verdict}.", ENGINE
    if re.search(r"worst|least|not selling|dead|remove", q):
        low = I["all"][-3:] if len(I["all"]) > 3 else I["all"]; ns = I["never_sold"][:5]
        return "Least booked: " + ", ".join(f"{i['name']} ({i['qty']})" for i in reversed(low)) + (". Never sold: " + ", ".join(x["name"] for x in ns) if ns else "") + ".", ENGINE
    if re.search(r"best|top|most|popular|sell", q):
        top = I["all"][:3]; return "Top services in " + span + ": " + ", ".join(f"{i['name']} — {i['qty']} done, {kes(i['revenue'])}" for i in top) + ".", ENGINE
    if re.search(r"customer|client|repeat|regular|loyal", q):
        return f"You have {C['total']} known clients; {C['repeat']} ({(C['repeat'] / C['total'] * 100) if C['total'] else 0:.0f}%) have come more than once. {C['inquiries']} inquiries and {C['bookings']} bookings in {span}.", ENGINE
    if re.search(r"staff|team|stylist|therapist|barber|who", q):
        if not s["team"]: return "No services attributed to staff yet.", ENGINE
        return "Sales by staff in " + span + ": " + ", ".join(f"{t['name']} {kes(t['sales'])} ({t['orders']} services)" for t in s["team"]) + ".", ENGINE
    if re.search(r"forecast|next week|predict|expect", q):
        rep, _, _ = generate_report(vendor, days); return f"Expect about {kes(rep['forecast']['next_7_days_sales'])} over the next 7 days ({rep['forecast']['confidence']} confidence). {rep['forecast']['basis']}", ENGINE
    if re.search(r"book|no.?show|online|appointment", q):
        b = s["bookings"]; return f"{b['total']} bookings in {span} ({b['online']} online): {b['no_show']} no-shows, {b['cancelled']} cancelled.", ENGINE
    if re.search(r"average|ticket|per (visit|client|order)", q):
        return f"Average visit value is {kes(S['avg_ticket'])} in {span}" + (f" (was {kes(S['prev_avg_ticket'])} the period before)." if S["prev_avg_ticket"] else "."), ENGINE
    if re.search(r"sales|revenue|made|earn|total|how much", q):
        ch = _pct(S["total"], S["prev_total"]); return f"{kes(S['total'])} from {S['orders']} visits in {span}" + (f", {ch:+.0f}% vs the period before." if ch is not None else "."), ENGINE
    return ("I can answer about: sales, profit, expenses, M-Pesa/cash, best day, peak hours, top or weakest services, a specific service by name, "
            "clients, staff, bookings, average visit, or next week's forecast. Try e.g. 'How much did Jane bring in this week?'"), ENGINE


def ai_available():
    return True
