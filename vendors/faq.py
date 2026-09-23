"""Common-sense client questions answered from the vendor's own listing — no AI, no API, nothing for the vendor to write."""
import re

from django.db.models import Q
from django.utils import timezone

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# (label shown as a chip, topic key)
CHIPS = [("Are you open now?", "open"), ("What time do you close?", "hours"), ("Where are you?", "location"),
         ("Can I book?", "reserve"), ("Do you come to me?", "home"), ("How do I pay?", "pay"), ("What's cheapest?", "cheap")]

TOPICS = {
    "open": r"\bopen\b|\bopened\b|\bstill\b|right now|\bnow\b",
    "hours": r"\bhours?\b|\bclose|\bclosing|\btime\b|\bwhen\b|\bsunday|\bsaturday|\bmonday|\btuesday|\bwednesday|\bthursday|\bfriday|\bweekend|\btoday|\btomorrow",
    "location": r"\bwhere\b|\blocat|\baddress|\bdirection|\bmap\b|\bfind you|\bnear\b|\bplace\b",
    "home": r"\bhome\b|\bhouse\b|\bcome to|\bmobile\b|\bvisit me|\bmy place",
    "reserve": r"\bbook|\breserv|\bappointment|\bslot\b|\bwedding|\bbridal|\bgroup\b|\bbirthday",
    "pay": r"\bpay|\bm-?pesa|\bmpesa|\bcash|\bcard\b|\btill\b|\bpaybill",
    "cheap": r"\bcheap|\bbudget|\baffordable|\blowest|\bleast\b",
    "price": r"\bhow much|\bprice|\bcost|\bkes\b|\bbob\b|\bshilling",
    "menu": r"\bservices?\b|\bwhat do you (have|do|offer)|\bprice list\b|\bhair\b|\bnails?\b|\bbraids?\b|\bmassage\b|\bfacial|\bmakeup\b|\blash|\bkids",
    "contact": r"\bphone|\bcall\b|\bnumber\b|\bwhatsapp|\bcontact|\bemail",
    "offers": r"\boffer|\bdeal|\bdiscount|\bpromo|\bhappy hour|\bspecial",
    "wifi": r"\bwifi|\bwi-fi|\binternet",
    "parking": r"\bparking|\bpark\b",
}


def _fmt(t):
    return t.strftime("%-I:%M %p").replace(":00", "")


def _hours_map(vendor):
    return {h.day: h for h in vendor.hours.all()}


def _today_line(vendor):
    hm = _hours_map(vendor)
    if not any(h.opens for h in hm.values()):
        return None
    d = timezone.localtime().weekday()
    h = hm.get(d)
    if h is None or h.closed or not h.opens:
        return f"Closed today ({DAYS[d]})."
    return f"Today ({DAYS[d]}): {_fmt(h.opens)} – {_fmt(h.closes)}."


def _item_lookup(vendor, text):
    """Price questions: find services whose name appears in the question."""
    words = [w for w in re.findall(r"[a-z]{3,}", text) if w not in {"how", "much", "price", "cost", "the", "for", "your", "does", "what", "and", "with", "kes", "bob"}]
    if not words:
        return []
    q = Q()
    for w in words:
        q |= Q(name__icontains=w)
    return list(vendor.items.filter(is_available=True).filter(q).select_related("category")[:5])


def answer(vendor, question):
    """Return (answer_text, suggest_whatsapp). Always answers something; never invents facts."""
    text = (question or "").strip().lower()
    loc = ", ".join(x for x in [vendor.address, vendor.town, vendor.county] if x)
    wa = " Ask us on WhatsApp for anything else." if vendor.whatsapp_link else ""

    if not text:
        return "Tap a question above, or type your own.", False

    # price of a specific service first — "how much is knotless braids"
    if re.search(TOPICS["price"], text) or re.search(TOPICS["menu"], text):
        hits = _item_lookup(vendor, text)
        if hits:
            parts = [f"{i.name}: {'price on request' if i.price_on_request else f'KES {i.price:,.0f}'}" for i in hits]
            return "; ".join(parts) + ". Book it below, or send a question.", False

    if re.search(TOPICS["open"], text):
        state = vendor.is_open_now
        line = _today_line(vendor)
        if state is None:
            return "Opening hours aren't listed yet — please ask on WhatsApp or call before you come.", True
        return ("Yes, open now. " if state else "Closed right now. ") + (line or ""), not state

    if re.search(TOPICS["hours"], text):
        hm = _hours_map(vendor)
        if not any(h.opens for h in hm.values()):
            return "Opening hours aren't listed yet — please ask on WhatsApp.", True
        for i, day in enumerate(DAYS):
            if day.lower() in text or (day.lower()[:3] in text.split()):
                h = hm.get(i)
                return (f"{day}: closed." if h is None or h.closed or not h.opens else f"{day}: {_fmt(h.opens)} – {_fmt(h.closes)}."), False
        if "weekend" in text:
            out = []
            for i in (5, 6):
                h = hm.get(i)
                out.append(f"{DAYS[i]}: " + ("closed" if h is None or h.closed or not h.opens else f"{_fmt(h.opens)} – {_fmt(h.closes)}"))
            return "; ".join(out) + ".", False
        return (_today_line(vendor) or "") + " Full hours are listed under Opening hours.", False

    if re.search(TOPICS["location"], text):
        if not loc:
            return "The address isn't listed yet — ask on WhatsApp and we'll send directions.", True
        return f"We're at {loc}." + (" Tap 'Open in Maps' under Contact for directions." if vendor.map_link else ""), False

    if re.search(TOPICS["reserve"], text):
        if vendor.accepts_bookings:
            return "Yes — tap “Add” on the services you want, then pick a time under 'Book an appointment' on this page. We confirm on WhatsApp.", False
        return "Bookings aren't taken online — message us on WhatsApp to find a slot.", True

    if re.search(TOPICS["home"], text):
        if vendor.home_service:
            return "Yes, we do home visits. Send a question with your location and the service, and we'll confirm the price on WhatsApp.", False
        return "We don't do home visits — come to us" + (f" at {loc}." if loc else "."), False

    if re.search(TOPICS["pay"], text):
        return "Pay at the salon after your service — cash, M-Pesa or card. Nothing is charged on this website.", False

    if re.search(TOPICS["cheap"], text):
        cheap = list(vendor.items.filter(is_available=True, price_on_request=False, price__gt=0).order_by("price")[:3])
        if not cheap:
            return "Prices aren't listed yet — ask on WhatsApp.", True
        return "Most affordable: " + "; ".join(f"{i.name} KES {i.price:,.0f}" for i in cheap) + ".", False

    if re.search(TOPICS["offers"], text):
        today = timezone.localdate()
        live = vendor.offers.filter(is_active=True).filter(Q(starts__isnull=True) | Q(starts__lte=today)).filter(Q(ends__isnull=True) | Q(ends__gte=today))
        names = [o.title for o in live[:3]]
        return ("Current offers: " + "; ".join(names) + ". See Special offers above.") if names else "No special offers running right now.", False

    if re.search(TOPICS["contact"], text):
        bits = [f"Call {vendor.phone}" if vendor.phone else "", "WhatsApp us with the green button" if vendor.whatsapp_link else "", f"email {vendor.email}" if vendor.email else ""]
        bits = [b for b in bits if b]
        return (" · ".join(bits) + ".") if bits else "Contact details aren't listed yet.", False

    if re.search(TOPICS["menu"], text):
        cats = list(vendor.categories.values_list("name", flat=True)[:6])
        n = vendor.items.filter(is_available=True).count()
        if not n:
            return "The price list isn't online yet — ask on WhatsApp.", True
        return f"{n} services" + (f" across {', '.join(cats)}" if cats else "") + ". Use the search above to find one.", False

    if re.search(TOPICS["wifi"], text) or re.search(TOPICS["parking"], text):
        return "That isn't listed on this page — best to ask on WhatsApp.", True

    return "I can answer about opening hours, location, prices, bookings, home visits and payment. For anything else, WhatsApp us." + wa, True
