import uuid
from functools import wraps

from django.conf import settings
from django.core.cache import cache

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (HoursFormSet, InquiryForm, MenuCategoryForm, MenuItemForm, OfferForm, PhotoForm, ReviewCodeForm, ReviewForm,
                    VendorProfileForm)
from .models import (BUSINESS_TYPES, STANDARD_MENU_TYPES, Customer, Inquiry, Location, MenuCategory, MenuItem, Offer, OpeningHours, Photo, Review,
                     SiteSettings, Tag, Vendor)
from pos.forms import PublicBookingForm

from .paging import paginate
from .security import protect, turnstile_ok


# ───────────────────────── Public site ─────────────────────────

@require_POST
@protect("reveal", 30, 600, require_turnstile=False)
def reveal_contact(request, type_slug, slug):
    """Contact details are hidden from bots/scrapers; shown after a Turnstile check."""
    vendor = get_object_or_404(Vendor, slug=slug, is_published=True, is_approved=True)
    return render(request, "partials/contact_revealed.html", {"vendor": vendor})


def vendor_jsonld(request, vendor):
    """schema.org Restaurant/Hotel/… + Menu + BreadcrumbList for rich results."""
    import json
    url = request.build_absolute_uri(vendor.get_absolute_url())
    data = {
        "@context": "https://schema.org", "@type": vendor.schema_type, "@id": url, "url": url, "name": vendor.brand_name,
        "description": vendor.tagline or vendor.seo_description,
        "address": {"@type": "PostalAddress", "streetAddress": vendor.address, "addressLocality": vendor.town, "addressRegion": vendor.county, "addressCountry": "KE"},
        "servesCuisine": [t.name for t in vendor.tags.all()],
        "priceRange": "KES",
    }
    if vendor.logo:
        data["logo"] = request.build_absolute_uri(vendor.logo.url)
        data["image"] = [request.build_absolute_uri(vendor.logo.url)]
    if vendor.cover:
        data.setdefault("image", []).insert(0, request.build_absolute_uri(vendor.cover.url))
    if vendor.map_link:
        data["hasMap"] = vendor.map_link
    hours = []
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for h in vendor.hours.all():
        if h.opens and h.closes and not h.closed:
            hours.append({"@type": "OpeningHoursSpecification", "dayOfWeek": days[h.day], "opens": h.opens.strftime("%H:%M"), "closes": h.closes.strftime("%H:%M")})
    if hours:
        data["openingHoursSpecification"] = hours
    if not vendor.menu_locked:
        sections = _menu_sections_jsonld(vendor)
        if sections:
            data["hasMenu"] = {"@type": "Menu", "name": f"{vendor.brand_name} menu", "url": url, "hasMenuSection": sections}
    crumbs = [{"@type": "ListItem", "position": 1, "name": "BeautyFlow", "item": request.build_absolute_uri("/")},
              {"@type": "ListItem", "position": 2, "name": vendor.type_row[3], "item": request.build_absolute_uri(f"/{vendor.type_plural_slug}/")}]
    if vendor.county_loc:
        crumbs.append({"@type": "ListItem", "position": 3, "name": vendor.county_loc.name, "item": request.build_absolute_uri(f"/{vendor.type_plural_slug}/{vendor.county_loc.slug}/")})
    crumbs.append({"@type": "ListItem", "position": len(crumbs) + 1, "name": vendor.brand_name, "item": url})
    return json.dumps([data, {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": crumbs}], ensure_ascii=False)


JSONLD_MENU_CAP = 60  # search engines only need a sample of the menu; the full menu is paginated on the page


def _menu_sections_jsonld(vendor):
    """Menu sections for JSON-LD: one query, capped, cached — a 2,000-item menu must not bloat every page view."""
    key = f"jsonld_menu:{vendor.pk}"
    sections = cache.get(key)
    if sections is not None:
        return sections
    by_cat = {}
    rows = vendor.items.filter(is_available=True).select_related("category").only("name", "price", "price_on_request", "category__name", "category__order")[:JSONLD_MENU_CAP]
    for i in rows:
        entry = {"@type": "MenuItem", "name": i.name}
        if not i.price_on_request:
            entry["offers"] = {"@type": "Offer", "price": str(i.price), "priceCurrency": "KES"}
        by_cat.setdefault(i.category.name if i.category else "Menu", []).append(entry)
    sections = [{"@type": "MenuSection", "name": name, "hasMenuItem": entries} for name, entries in by_cat.items()]
    cache.set(key, sections, 600)
    return sections


def _uuid_or_none(value):
    try:
        return str(uuid.UUID(str(value))) if value else None
    except ValueError:
        return None


def home(request):
    q = request.GET.get("q", "").strip()
    live = Vendor.objects.live()
    vendors = live.for_cards().order_by("-plan", "-created_at")
    if q:
        vendors = vendors.filter(Q(brand_name__icontains=q) | Q(town__icontains=q) | Q(county__icontains=q) | Q(tagline__icontains=q)
                                 | Q(items__name__icontains=q) | Q(categories__name__icontains=q)).distinct()
    page, qs_prefix = paginate(request, vendors, 18)
    ctx = {"vendors": page, "page": page, "qs": qs_prefix, "q": q}
    if request.htmx:
        return render(request, "partials/vendor_cards.html", ctx)
    ctx.update(_home_seo_block(live))
    ctx.update({
        "type_cards": [(r[4], r[3], BLURBS.get(r[0], ""), f"img/home/{r[0]}.webp") for r in BUSINESS_TYPES],
        "popular": ["Knotless braids", "Gel nails", "Haircut", "Facial", "Massage", "Lashes", "Locs"],
    })
    return render(request, "vendors/home.html", ctx)


BLURBS = {"salon": "Braids, weaves, colour, blow-dry", "spa": "Massage, facials, steam & sauna", "barber": "Cuts, fades, shaves, beard care",
          "nails": "Gel, acrylics, manicure, pedicure", "makeup": "Bridal, events, photoshoots", "massage": "Deep tissue, Swedish, hot stone",
          "beauty_shop": "Hair, skin care & cosmetics", "wellness": "Yoga, physio, holistic care"}


def _home_seo_block(live):
    """Counties, dish chips, deals count for the home page — cached 10 minutes, it only changes when vendors do."""
    block = cache.get("home_seo_block")
    if block is not None:
        return block
    from django.db.models import Count
    menu_names = {n.lower() for n in MenuCategory.objects.filter(vendor__in=live).values_list("name", flat=True).distinct()}
    block = {
        "counties": list(Location.objects.filter(kind="county").order_by("name")),
        "deals_count": Offer.objects.filter(is_active=True, vendor__is_published=True, vendor__is_approved=True).filter(Q(ends__isnull=True) | Q(ends__gte=timezone.localdate())).count(),
        "seo_locations": list(Location.objects.annotate(n=Count("county_vendors", filter=Q(county_vendors__is_published=True, county_vendors__is_approved=True)) + Count("area_vendors", filter=Q(area_vendors__is_published=True, area_vendors__is_approved=True))).filter(n__gte=1).order_by("-n", "name")[:12]),
        "seo_tags": [t for t in Tag.objects.filter(kind="menu") if t.name.lower() in menu_names][:12],
        "towns": list(live.exclude(county="").values_list("county", flat=True).distinct().order_by("county")[:8]),
    }
    cache.set("home_seo_block", block, 600)
    return block


def search(request):
    """Hero search → real results page (also used by the header search)."""
    q = request.GET.get("q", "").strip()[:80]
    loc = request.GET.get("loc", "").strip()[:80]
    qs = Vendor.objects.live().for_cards().order_by("-plan", "-created_at")
    if q:
        qs = qs.filter(Q(brand_name__icontains=q) | Q(tagline__icontains=q) | Q(items__name__icontains=q) | Q(categories__name__icontains=q) | Q(tags__name__icontains=q)).distinct()
    if loc:
        qs = qs.filter(Q(town__icontains=loc) | Q(county__icontains=loc) | Q(address__icontains=loc))
    page, qs_prefix = paginate(request, qs, 18)
    locs = Location.objects.filter(kind="county").order_by("name")
    return render(request, "vendors/search.html", {"vendors": page, "page": page, "qs": qs_prefix, "q": q, "loc": loc, "total": page.paginator.count, "locations": locs})


def deals(request):
    today = timezone.localdate()
    qs = Offer.objects.filter(is_active=True, vendor__is_published=True, vendor__is_approved=True, vendor__plan="premium").filter(Q(starts__isnull=True) | Q(starts__lte=today)).filter(Q(ends__isnull=True) | Q(ends__gte=today)).select_related("vendor")
    qs = [o for o in qs if not o.vendor.menu_locked]
    return render(request, "vendors/deals.html", {"offers": qs})


def features(request):
    return render(request, "vendors/features.html")


def about(request):
    live = Vendor.objects.filter(is_published=True, is_approved=True)
    return render(request, "vendors/about.html", {"vendor_count": live.count(), "county_count": Location.objects.filter(kind="county").count()})


def pricing(request):
    return render(request, "vendors/pricing.html")


def vendor_menu_only(request, type_slug, slug):
    """The old guessable menu link: send people to the public page (ordering lives on the QR link only)."""
    vendor = get_object_or_404(Vendor, slug=slug)
    return redirect(vendor.get_absolute_url(), permanent=True)


def menu_by_token(request, token):
    """QR landing: just the price list. Only reachable by the unguessable link on the QR."""
    from pos.pricing import price_items
    branch = None
    vendor = get_object_or_404(Vendor.objects.select_related("county_loc", "area_loc"), menu_token=token)
    if not vendor.is_live and (not request.user.is_authenticated or request.user != vendor.owner):
        return render(request, "vendors/unavailable.html", status=404)
    categories = vendor.categories.filter(items__is_available=True).distinct()  # tabs only for types that have dishes
    cat = _uuid_or_none(request.GET.get("cat"))
    mq = request.GET.get("mq", "").strip()[:60]
    items = vendor.items.filter(is_available=True).select_related("category")
    if cat:
        items = items.filter(category_id=cat)
    if mq:
        items = items.filter(Q(name__icontains=mq) | Q(description__icontains=mq))
    if vendor.menu_locked:
        categories = categories.none()
        first = vendor.items.filter(is_available=True).first()
        items, menu_page, menu_qs = ([first] if first else []), None, ""
    else:
        menu_page, menu_qs = paginate(request, items, 30)
        items = menu_page
    items = price_items(items, branch)
    ctx = {"vendor": vendor, "branch": branch, "categories": categories, "items": items, "active_cat": cat, "mq": mq,
           "menu_page": menu_page, "menu_qs": menu_qs,
           "menu_total": menu_page.paginator.count if menu_page else len(items), "menu_only": True,
           "menu_base": vendor.get_menu_url(),
           "canonical": request.build_absolute_uri(vendor.get_absolute_url())}
    if request.htmx and request.htmx.target in ("menu-items", "menu-more"):
        return render(request, "partials/menu_items.html", ctx)
    return render(request, "vendors/menu_only.html", ctx)


def vendor_og_image(request, type_slug, slug):
    """1200x630 JPEG social preview (cover, or logo on brand colour), cached on disk. WhatsApp/Facebook-friendly."""
    import io, os
    from PIL import Image, ImageDraw, ImageFont
    from django.conf import settings as dj
    vendor = get_object_or_404(Vendor, slug=slug)
    src = vendor.cover or vendor.logo
    key = f"{vendor.slug}-{int(os.path.getmtime(src.path)) if src and os.path.exists(src.path) else 0}.jpg"
    out_dir = os.path.join(dj.MEDIA_ROOT, "og"); os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, key)
    if not os.path.exists(out):
        W, H = 1200, 630
        canvas = Image.new("RGB", (W, H), (29, 29, 31))
        try:
            im = Image.open(src.path).convert("RGB")
            if vendor.cover:
                # cover-fit crop
                r = max(W / im.width, H / im.height); im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1)); x = (im.width - W) // 2; y = (im.height - H) // 2
                canvas.paste(im.crop((x, y, x + W, y + H)), (0, 0))
            else:
                im.thumbnail((360, 360)); canvas.paste(im, ((W - im.width) // 2, 110))
        except Exception:
            pass
        # bottom band with name
        band = Image.new("RGBA", (W, 150), (0, 0, 0, 150)); canvas.paste(band, (0, H - 150), band)
        d = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48); small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
        except Exception:
            font = small = ImageFont.load_default()
        d.text((48, H - 130), vendor.brand_name[:40], fill="white", font=font)
        d.text((48, H - 66), (f"Menu & prices · {vendor.town or vendor.county or 'Kenya'} · beautyflow.co.ke")[:80], fill=(244, 162, 97), font=small)
        canvas.save(out, "JPEG", quality=82, optimize=True)
        # clean older versions
        for f in os.listdir(out_dir):
            if f.startswith(vendor.slug + "-") and f != key:
                try: os.remove(os.path.join(out_dir, f))
                except OSError: pass
    with open(out, "rb") as f:
        resp = HttpResponse(f.read(), content_type="image/jpeg")
    resp["Cache-Control"] = "public, max-age=86400"
    return resp


def vendor_qr_card(request, type_slug, slug):
    """Printable QR card for the vendor's counter / table."""
    vendor = get_object_or_404(Vendor, slug=slug)
    if not vendor.is_live and (not request.user.is_authenticated or request.user != vendor.owner):
        return render(request, "vendors/unavailable.html", status=404)
    return render(request, "vendors/qr_card.html", {"vendor": vendor, "url": request.build_absolute_uri(vendor.get_absolute_url()),
                                                    "menu_url": request.build_absolute_uri(vendor.get_menu_url())})


def vendor_qr_png(request, type_slug, slug):
    """Download a print-ready PNG QR (menu, or the reviews section with ?for=review)."""
    import io
    import qrcode
    vendor = get_object_or_404(Vendor, slug=slug)
    target = request.build_absolute_uri(vendor.get_absolute_url() + "#reviews" if request.GET.get("for") == "review" else vendor.get_menu_url())
    img = qrcode.make(target, box_size=16, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    resp = HttpResponse(buf.getvalue(), content_type="image/png")
    resp["Content-Disposition"] = f'attachment; filename="{vendor.slug}-{"review" if request.GET.get("for") == "review" else "prices"}-qr.png"'
    return resp


def privacy(request):
    return render(request, "vendors/privacy.html")


def terms(request):
    return render(request, "vendors/terms.html")


def vendor_detail(request, type_slug, slug):
    vendor = get_object_or_404(Vendor.objects.select_related("county_loc", "area_loc")
                               .prefetch_related("hours", "tags", "categories"), slug=slug)
    if type_slug != vendor.type_slug:
        return redirect(vendor.get_absolute_url() + (f"?{request.GET.urlencode()}" if request.GET else ""), permanent=True)
    if not vendor.is_live and (not request.user.is_authenticated or request.user != vendor.owner):
        return render(request, "vendors/unavailable.html", status=404)
    categories = vendor.categories.filter(items__is_available=True).distinct()  # tabs only for types that have dishes
    cat = _uuid_or_none(request.GET.get("cat"))
    mq = request.GET.get("mq", "").strip()[:60]
    items = vendor.items.filter(is_available=True).select_related("category")
    if cat:
        items = items.filter(category_id=cat)
    if mq:
        items = items.filter(Q(name__icontains=mq) | Q(description__icontains=mq))
    if vendor.menu_locked:
        # Lapsed subscription: show only the first item, quietly hide the rest.
        categories = categories.none()
        first = vendor.items.filter(is_available=True).select_related("category").first()
        items = [first] if first else []
        menu_page, menu_qs = None, ""
    else:
        menu_page, menu_qs = paginate(request, items, 24)
        items = menu_page
    from pos.pricing import price_items
    items = price_items(items)
    if request.htmx and request.htmx.target in ("menu-items", "menu-more"):
        # "Show more" / menu search: only the rows are needed — skip reviews, offers, JSON-LD and similar places.
        return render(request, "partials/menu_items.html", {
            "vendor": vendor, "items": items, "mq": mq, "menu_page": menu_page, "menu_qs": menu_qs,
            "menu_total": menu_page.paginator.count if menu_page else len(items)})
    today = timezone.localdate()
    hours = list(vendor.hours.all())
    ctx = {
        "vendor": vendor, "categories": categories, "items": items, "active_cat": cat, "mq": mq,
        "menu_page": menu_page, "menu_qs": menu_qs, "menu_total": menu_page.paginator.count if menu_page else len(items),
        "reviews": _live_reviews(vendor), "review_form": ReviewForm(),
        "open_now": vendor.is_open_now,
        "photos": vendor.photos.all(),
        "hours": hours if any(h.opens for h in hours) else [],  # hide until the vendor sets real hours
        "offers": vendor.offers.none() if vendor.menu_locked else vendor.offers.filter(is_active=True).filter(Q(starts__isnull=True) | Q(starts__lte=today)).filter(Q(ends__isnull=True) | Q(ends__gte=today)),
        "res_form": PublicBookingForm(vendor=vendor, initial=_booking_initial(vendor, request.GET)),
        "today": today.weekday(),
        "jsonld": vendor_jsonld(request, vendor),
        "canonical": request.build_absolute_uri(vendor.get_absolute_url()),
    }
    from pos.models import Staff
    ctx["team"] = list(vendor.staff.filter(is_active=True, role=Staff.Role.STAFF, show_on_site=True).select_related("user")
                       .prefetch_related("service_links__service"))
    from .faq import CHIPS
    ctx["faq_chips"] = CHIPS
    ctx["similar"] = _similar_vendors(vendor)
    return render(request, "vendors/detail.html", ctx)


@require_POST
@protect("faq", 30, 600, require_turnstile=False)
def vendor_faq(request, type_slug, slug):
    """Common-sense answers from the listing (hours, prices, delivery…). Rules only — no AI, no API."""
    from .faq import answer
    vendor = get_object_or_404(Vendor.objects.prefetch_related("hours"), slug=slug, is_published=True, is_approved=True)
    q = (request.POST.get("q") or "").strip()[:160]
    text, suggest_wa = answer(vendor, q)
    return render(request, "partials/faq_answer.html", {"vendor": vendor, "q": q, "answer": text, "suggest_wa": suggest_wa})


def _booking_initial(vendor, get):
    """Pre-fill the booking form from a "Book" link: ?service=<id>&staff=<id>."""
    out = {}
    sid = _uuid_or_none(get.get("service"))
    if sid and vendor.items.filter(pk=sid, is_available=True).exists():
        out["service"] = sid
    tid = _uuid_or_none(get.get("staff"))
    if tid and vendor.staff.filter(pk=tid, is_active=True).exists():
        out["staff"] = tid
    return out


def _similar_vendors(vendor, limit=6):
    """Same type in the same town first, then same county, then same type anywhere. Cached — it barely changes."""
    key = f"similar:{vendor.pk}:{limit}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    out = _similar_query(vendor, limit)
    cache.set(key, out, 900)
    return out


def _similar_query(vendor, limit):
    live = Vendor.objects.live().for_cards().exclude(pk=vendor.pk)
    picked, seen = [], set()
    tiers = [
        live.filter(business_type=vendor.business_type, town__iexact=vendor.town) if vendor.town else live.none(),
        live.filter(business_type=vendor.business_type, county=vendor.county) if vendor.county else live.none(),
        live.filter(town__iexact=vendor.town) if vendor.town else live.none(),
        live.filter(business_type=vendor.business_type),
    ]
    for qs in tiers:
        for v in qs.order_by("-plan", "-created_at")[:limit]:
            if v.pk not in seen:
                seen.add(v.pk)
                picked.append(v)
            if len(picked) >= limit:
                return picked
    return picked


def _live_reviews(vendor):
    return vendor.reviews.filter(is_approved=True, verified_at__isnull=False)[:20]


def _send_review_code(request, review):
    from beautyflow.mailer import send_otp_mail
    code = review.issue_code()
    try:
        send_otp_mail(f"{code} — confirm your review of {review.vendor.brand_name}",
                  f"Hi {review.name},\n\nEnter this code on BeautyFlow to publish your review of {review.vendor.brand_name}:\n\n    {code}\n\n"
                  f"It expires in 15 minutes. If you didn't write a review, ignore this email.\n\n— BeautyFlow",
                  [review.email])
        return True
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Review code email failed")
        return False


@require_POST
@protect("review", 5, 3600)
def add_review(request, type_slug, slug):
    """Step 1: save the review unverified and email a code. One review per email per business."""
    vendor = get_object_or_404(Vendor, slug=slug, is_published=True, is_approved=True)
    form = ReviewForm(request.POST)
    ctx = {"vendor": vendor, "reviews": _live_reviews(vendor), "review_form": form}
    if not form.is_valid():
        return render(request, "partials/reviews.html", ctx)
    d = form.cleaned_data
    if d["email"] == (vendor.owner.email or "").lower() or d["email"] == (vendor.email or "").lower():
        form.add_error("email", "You can't review your own business.")
        return render(request, "partials/reviews.html", ctx)
    review, created = Review.objects.update_or_create(
        vendor=vendor, email=d["email"],
        defaults={"name": d["name"], "stars": d["stars"], "comment": d["comment"], "verified_at": None, "is_approved": True})
    if not _send_review_code(request, review):
        form.add_error("email", "We couldn't send the code right now. Please try again in a moment.")
        return render(request, "partials/reviews.html", ctx)
    return render(request, "partials/review_verify.html", {"vendor": vendor, "review": review, "code_form": ReviewCodeForm(), "updating": not created})


@require_POST
@protect("review_code", 15, 900, require_turnstile=False)
def verify_review(request, type_slug, slug, pk):
    """Step 2: code entered → review goes live."""
    vendor = get_object_or_404(Vendor, slug=slug, is_published=True, is_approved=True)
    review = get_object_or_404(Review, pk=pk, vendor=vendor, verified_at__isnull=True)
    if request.POST.get("resend"):
        _send_review_code(request, review)
        return render(request, "partials/review_verify.html", {"vendor": vendor, "review": review, "code_form": ReviewCodeForm(), "resent": True})
    form = ReviewCodeForm(request.POST)
    if form.is_valid() and review.check_code(form.cleaned_data["code"]):
        return render(request, "partials/reviews.html", {"vendor": vendor, "reviews": _live_reviews(vendor), "review_form": ReviewForm(), "thanks": True})
    form.add_error("code", "That code is wrong or has expired.")
    return render(request, "partials/review_verify.html", {"vendor": vendor, "review": review, "code_form": form})


# ───────────────────────── Vendor dashboard ─────────────────────────

def pos_module_required(view):
    """Owner pages that belong to the paid POS module (Customers)."""
    def deco(request, *args, **kwargs):
        from pos.branching import resolve as resolve_branch
        resolve_branch(request)
        gate = request.branch if request.branch is not None else request.vendor
        if not gate.pos_active:
            return render(request, "pos/locked.html", {"vendor": request.vendor, "site": SiteSettings.get(), "product": "pos",
                                                       "branch": request.branch, "is_team": False}, status=402)
        return view(request, *args, **kwargs)
    deco.__name__ = getattr(view, "__name__", "view")
    deco.__doc__ = view.__doc__
    return vendor_required(deco)


def branch_ctx(request):
    """Branch switcher context for the owner's POS-module pages."""
    branches = getattr(request, "branches", [])
    return {"branch": getattr(request, "branch", None), "branches": branches,
            "show_branches": request.vendor.branches_enabled,
            "many_branches": request.vendor.branches_enabled and len(branches) > 1,
            "branches_allowed": request.vendor.can_use_branches}


def vendor_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        vendor = getattr(request.user, "vendor", None)
        if vendor is None:
            if request.user.is_admin_role:
                return redirect("ap_index")
            if getattr(request.user, "is_team", False):
                return redirect("pos_me")
            if getattr(request.user, "is_affiliate", False):
                return redirect("aff_home")
            messages.error(request, "No vendor profile attached to this account.")
            return redirect("home")
        request.vendor = vendor
        return view(request, *args, **kwargs)
    return wrapper


def _series(days, rows, key="d"):
    """rows: iterable of dicts {d: date, val}. Returns list aligned to the last `days` days + SVG polyline points."""
    from datetime import timedelta
    today = timezone.localdate()
    by = {r[key]: float(r["val"] or 0) for r in rows}
    data = [{"date": today - timedelta(days=i), "val": by.get(today - timedelta(days=i), 0.0)} for i in range(days - 1, -1, -1)]
    mx = max([d["val"] for d in data] or [0]) or 1
    w, h = 600, 140
    pts = []
    for i, d in enumerate(data):
        x = round(i * (w / (days - 1)), 1)
        y = round(h - (d["val"] / mx) * (h - 10) - 4, 1)
        pts.append(f"{x},{y}")
        d["x"], d["y"], d["pct"] = x, y, int(d["val"] / mx * 100)
    return {"data": data, "points": " ".join(pts), "area": f"0,{h} " + " ".join(pts) + f" {w},{h}", "max": mx, "total": sum(d["val"] for d in data)}


@vendor_required
def dashboard(request):
    from datetime import timedelta
    from django.db.models import Count, Sum
    from django.db.models.functions import TruncDate
    v = request.vendor
    since30 = timezone.now() - timedelta(days=30)
    paid = v.orders.filter(paid_at__gte=since30)
    sales = _series(30, [{"d": r["d"], "val": r["val"]} for r in paid.annotate(d=TruncDate("paid_at")).values("d").annotate(val=Sum("total"))])
    orders = _series(30, [{"d": r["d"], "val": r["val"]} for r in paid.annotate(d=TruncDate("paid_at")).values("d").annotate(val=Count("id"))])
    inquiries = _series(30, [{"d": r["d"], "val": r["val"]} for r in v.bookings.filter(created_at__gte=since30).annotate(d=TruncDate("created_at")).values("d").annotate(val=Count("id"))])
    from pos.models import OrderItem
    top = list(OrderItem.objects.filter(order__in=paid).values("name").annotate(qty=Sum("qty"), total=Sum("line_total")).order_by("-qty")[:6])
    mx = max([t["qty"] for t in top] or [0]) or 1
    for t in top:
        t["pct"] = int(t["qty"] / mx * 100)
    methods = list(paid.values("payment_method").annotate(total=Sum("total"), n=Count("id")).order_by("-total"))
    grand = sum((m["total"] or 0) for m in methods) or 1
    labels = {"cash": "Cash", "mpesa": "M-Pesa", "card": "Card"}
    for m in methods:
        m["label"] = labels.get(m["payment_method"], m["payment_method"] or "—"); m["pct"] = int((m["total"] or 0) / grand * 100)
    score, _done, missing = v.profile_progress()
    week = v.orders.filter(paid_at__gte=timezone.now() - timedelta(days=7)).aggregate(t=Sum("total"), n=Count("id"))
    prev_week = v.orders.filter(paid_at__gte=timezone.now() - timedelta(days=14), paid_at__lt=timezone.now() - timedelta(days=7)).aggregate(t=Sum("total"))
    wk, pwk = float(week["t"] or 0), float(prev_week["t"] or 0)
    return render(request, "dashboard/index.html", {
        "vendor": v, "score": score, "missing_items": missing, "needed_for_public": v.missing_for_public(),
        "unread": v.bookings.filter(status="requested", date__gte=timezone.localdate()).count(),
        "item_count": v.items.count(), "photo_count": v.photos.count(),
        "recent": v.bookings.select_related("service", "staff__user").order_by("-created_at")[:5],
        "sales": sales, "orders": orders, "inquiries_s": inquiries, "top": top, "methods": methods,
        "week_total": wk, "week_n": week["n"] or 0, "week_change": (round((wk - pwk) / pwk * 100) if pwk else None),
        "has_pos_data": paid.exists(),
    })


PROFILE_SECTIONS = [
    ("info", "Business info", ["brand_name", "business_type", "tagline", "logo", "cover", "home_service", "accepts_bookings", "is_published"]),
    ("contact", "Contact", ["email", "phone", "whatsapp"]),
    ("location", "Location", ["county", "town", "address", "map_link"]),
    ("description", "Description", ["about"]),
]


@vendor_required
def profile(request):
    v = request.vendor
    if not v.hours.exists():
        OpeningHours.objects.bulk_create([OpeningHours(vendor=v, day=d) for d, _ in OpeningHours.DAYS])
    form = VendorProfileForm(request.POST or None, request.FILES or None, instance=v)
    hours_fs = HoursFormSet(request.POST if request.method == "POST" and "hours-TOTAL_FORMS" in request.POST else None, instance=v)
    if request.method == "POST" and form.is_valid() and (not hours_fs.is_bound or hours_fs.is_valid()):
        form.save()
        if hours_fs.is_bound:
            hours_fs.save()
        if v.maybe_publish():
            messages.success(request, f"{v.brand_name} is now live at {v.get_absolute_url()}")
        else:
            messages.success(request, "Business profile saved.")
        return redirect("dashboard_profile")
    sections = [(key, label, [form[n] for n in names]) for key, label, names in PROFILE_SECTIONS]
    score, done, missing = v.profile_progress()
    return render(request, "dashboard/profile.html", {"form": form, "vendor": v, "sections": sections,
                                                      "score": score, "done_items": done, "missing_items": missing,
                                                      "needed_for_public": v.missing_for_public(),
                                                      "hours_formset": hours_fs, "photo_form": PhotoForm(),
                                                      "photos": v.photos.all()[:12], "photo_total": v.photos.count(),
                                                      "limit": SiteSettings.get().free_photo_limit})


@vendor_required
def hours(request):
    v = request.vendor
    if not v.hours.exists():
        OpeningHours.objects.bulk_create([OpeningHours(vendor=v, day=d) for d, _ in OpeningHours.DAYS])
    fs = HoursFormSet(request.POST or None, instance=v)
    if request.method == "POST" and fs.is_valid():
        fs.save()
        v.maybe_publish()
        messages.success(request, "Opening hours saved.")
        return redirect(reverse("dashboard_profile") + "#hours")
    return render(request, "dashboard/hours.html", {"formset": fs, "vendor": v})


@vendor_required
def menu(request):
    v = request.vendor
    if request.method == "POST" and request.POST.get("_form") == "standard":
        chosen = set(request.POST.getlist("types")) & set(STANDARD_MENU_TYPES)
        existing = {c.name: c for c in v.categories.all()}
        for name in chosen:
            if name not in existing:
                MenuCategory.objects.create(vendor=v, name=name, order=STANDARD_MENU_TYPES.index(name))
        for name, c in existing.items():
            if name in STANDARD_MENU_TYPES and name not in chosen:
                c.delete()  # items keep, they just lose the type
        messages.success(request, "Categories updated.")
        return redirect("dashboard_menu")
    cat_form = MenuCategoryForm(request.POST or None) if request.POST.get("_form") == "category" else MenuCategoryForm()
    if request.method == "POST" and request.POST.get("_form") == "category" and cat_form.is_valid():
        c = cat_form.save(commit=False)
        c.vendor = v
        c.save()
        messages.success(request, f"Category “{c.name}” added.")
        return redirect("dashboard_menu")
    q = request.GET.get("q", "").strip()
    items = v.items.select_related("category")
    if q:
        items = items.filter(Q(name__icontains=q) | Q(category__name__icontains=q))
    if v.branches_enabled:
        from django.db.models import Count as _Count
        items = items.annotate(branch_price_count=_Count("branch_prices")).order_by("category__order", "name")
    page, qs_prefix = paginate(request, items, 20)
    if request.htmx and request.htmx.target == "item-list":
        return render(request, "dashboard/_item_list.html", {"items": page, "page": page, "qs": qs_prefix, "q": q})
    from .menu_pdf import profile_gaps
    return render(request, "dashboard/menu.html", {
        "vendor": v, "cat_form": cat_form, "categories": v.categories.all(), "q": q, "pdf_gaps": profile_gaps(v),
        "standard_types": STANDARD_MENU_TYPES, "ticked": set(v.categories.filter(name__in=STANDARD_MENU_TYPES).values_list("name", flat=True)),
        "custom_types": v.categories.exclude(name__in=STANDARD_MENU_TYPES),
        "items": page, "page": page, "qs": qs_prefix, "item_total": v.items.count(),
        "limit": SiteSettings.get().free_menu_limit,
    })


@vendor_required
def menu_pdf(request):
    from .menu_pdf import build_menu_pdf, profile_gaps
    v = request.vendor
    gaps = profile_gaps(v)
    if gaps:
        messages.warning(request, "Complete your profile first: " + ", ".join(gaps) + ".")
        return redirect("dashboard_menu")
    pdf = build_menu_pdf(v, request.build_absolute_uri(v.get_menu_url()), watermark=not v.is_premium)
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'{"inline" if request.GET.get("print") else "attachment"}; filename="{v.slug}-price-list.pdf"'
    return resp


@vendor_required
def item_form(request, pk=None):
    v = request.vendor
    item = get_object_or_404(MenuItem, pk=pk, vendor=v) if pk else None
    if item is None and not v.can_add_item():
        messages.warning(request, "Free plan limit reached. Upgrade to Premium to add more services.")
        return redirect("dashboard_upgrade")
    branches = _editable_branches(request)
    form = MenuItemForm(request.POST or None, request.FILES or None, instance=item, vendor=v)
    if request.method == "POST" and form.is_valid():
        if item is None and not v.can_add_item():  # re-check at save time, not just on page load
            messages.warning(request, "Free plan limit reached. Upgrade to Premium to add more services.")
            return redirect("dashboard_upgrade")
        obj = form.save(commit=False)
        obj.vendor = v
        obj.save()
        _save_branch_prices(request, obj)
        went_live = v.maybe_publish()
        messages.success(request, f"{v.brand_name} is now live at {v.get_absolute_url()}" if went_live else "Service saved.")
        return redirect("dashboard_menu")
    return render(request, "dashboard/item_form.html", {"form": form, "item": item, "vendor": v,
                                                        "branch_prices": _branch_price_rows(v, item, branches)})


def _editable_branches(request):
    """Branches whose price the owner can set on the service form (only when there is more than one)."""
    v = request.vendor
    if not v.branches_enabled:
        return []
    branches = list(v.branches.filter(is_active=True))
    return branches if len(branches) > 1 else []


def _branch_price_rows(vendor, item, branches=None):
    """One row per branch for the price table on the item form. Blank means it uses the business price."""
    if not vendor.branches_enabled:
        return []
    from pos.models import BranchPrice
    branches = list(branches) if branches is not None else list(vendor.branches.filter(is_active=True))
    if not branches:
        return []
    own = {}
    if item is not None:
        own = {r.branch_id: r for r in BranchPrice.objects.filter(item=item, branch__in=branches)}
    return [{"branch": b, "row": own.get(b.pk)} for b in branches]


def _save_branch_prices(request, item):
    """Store a price only where the branch charges something different; blank clears the override."""
    if not request.vendor.branches_enabled or item.price_on_request:
        return
    from decimal import Decimal, InvalidOperation
    from pos.models import BranchPrice
    for b in _editable_branches(request):
        raw = (request.POST.get(f"bp_{b.pk}") or "").strip()
        if not raw:
            BranchPrice.objects.filter(branch=b, item=item).delete()   # back to the business price
            continue
        try:
            val = Decimal(raw)
        except (InvalidOperation, ValueError):
            continue
        if val <= 0:
            BranchPrice.objects.filter(branch=b, item=item).delete()
            continue
        row = BranchPrice.objects.filter(branch=b, item=item).first() or BranchPrice(branch=b, item=item)
        row.net_price = val
        row.save()


@vendor_required
@require_POST
def item_delete(request, pk):
    get_object_or_404(MenuItem, pk=pk, vendor=request.vendor).delete()
    return HttpResponse("")


@vendor_required
@require_POST
def item_toggle(request, pk):
    item = get_object_or_404(MenuItem, pk=pk, vendor=request.vendor)
    item.is_available = not item.is_available
    item.save(update_fields=["is_available"])
    return render(request, "partials/item_row.html", {"item": item})


@vendor_required
@require_POST
def category_delete(request, pk):
    get_object_or_404(MenuCategory, pk=pk, vendor=request.vendor).delete()
    return HttpResponse("")


@vendor_required
def gallery(request):
    v = request.vendor
    form = PhotoForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if not v.can_add_photo():
            messages.warning(request, "Free plan photo limit reached. Upgrade to Premium for unlimited photos.")
            return redirect("dashboard_upgrade")
        if form.is_valid():
            p = form.save(commit=False)
            p.vendor = v
            p.save()
            messages.success(request, "Photo added.")
            return redirect(request.POST.get("_next") or "dashboard_gallery")
    page, qs_prefix = paginate(request, v.photos.all(), 24)
    return render(request, "dashboard/gallery.html", {"form": form, "vendor": v, "photos": page, "page": page, "qs": qs_prefix,
                                                       "photo_total": v.photos.count(), "limit": SiteSettings.get().free_photo_limit})


@vendor_required
@require_POST
def photo_delete(request, pk):
    get_object_or_404(Photo, pk=pk, vendor=request.vendor).delete()
    return HttpResponse("")


@vendor_required
def offers(request, pk=None):
    v = request.vendor
    editing = get_object_or_404(Offer, pk=pk, vendor=v) if pk else None
    form = OfferForm(request.POST or None, request.FILES or None, instance=editing)
    if request.method == "POST" and form.is_valid():
        o = form.save(commit=False)
        o.vendor = v
        o.save()
        messages.success(request, "Offer updated." if editing else "Offer published.")
        return redirect("dashboard_offers")
    page, qs_prefix = paginate(request, v.offers.all(), 20)
    return render(request, "dashboard/offers.html", {"form": form, "vendor": v, "offers": page, "page": page, "qs": qs_prefix, "editing": editing,
                                                     "today": timezone.localdate()})


@vendor_required
@require_POST
def offer_delete(request, pk):
    get_object_or_404(Offer, pk=pk, vendor=request.vendor).delete()
    return HttpResponse("")


@vendor_required
@require_POST
def offer_toggle(request, pk):
    o = get_object_or_404(Offer, pk=pk, vendor=request.vendor)
    o.is_active = not o.is_active
    o.save(update_fields=["is_active"])
    return render(request, "partials/offer_row.html", {"offer": o})


@vendor_required
def reviews(request):
    v = request.vendor
    q = request.GET.get("q", "").strip()
    qs = v.reviews.filter(verified_at__isnull=False)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(comment__icontains=q))
    page, qs_prefix = paginate(request, qs, 20)
    return render(request, "dashboard/reviews.html", {"vendor": v, "reviews": page, "page": page, "qs": qs_prefix, "q": q})


@vendor_required
def payments_page(request):
    qs = request.vendor.payments.all()
    page, qs_prefix = paginate(request, qs, 25)
    return render(request, "dashboard/payments.html", {"vendor": request.vendor, "payments": page, "page": page, "qs": qs_prefix})


@vendor_required
def share(request):
    v = request.vendor
    if request.method == "POST" and request.POST.get("action") == "rotate":
        v.rotate_menu_token()
        messages.success(request, "New QR link created. Reprint your QR — the old one no longer opens your price list.")
        return redirect("dashboard_share")
    return render(request, "dashboard/share.html", {"vendor": v, "url": request.build_absolute_uri(v.get_absolute_url()),
                                                    "menu_url": request.build_absolute_uri(v.get_menu_url())})


@vendor_required
def upgrade(request):
    return render(request, "dashboard/upgrade.html", {"vendor": request.vendor})


def page_not_found(request, exception=None):
    return render(request, "404.html", status=404)


def server_error(request):
    return render(request, "500.html", status=500)
