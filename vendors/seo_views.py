"""Indexable directory pages: business types × locations × services, owner landing pages, sitemap, robots."""
from django.contrib.sitemaps import Sitemap
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import ALL_TYPES, BT, BT_BY_PLURAL_SLUG, BUSINESS_TYPES, Location, Tag, Vendor
from .paging import paginate

MIN_VENDORS = 1  # a directory page must have at least this many live vendors, else 404 (no thin pages)


def live():
    return Vendor.objects.filter(is_published=True, is_approved=True)


def _type(plural_slug):
    row = ALL_TYPES if plural_slug == ALL_TYPES[4] else BT_BY_PLURAL_SLUG.get(plural_slug)
    if not row:
        raise Http404
    return row


def _loc(slug):
    return get_object_or_404(Location, slug=slug)


def _vendors_in(loc):
    return live().filter(Q(county_loc=loc) | Q(area_loc=loc))


def _apply_filters(request, qs):
    """Sidebar filters: location, business type, service type, home visits, open now, rating, sort."""
    from django.db.models import Avg, Count as _C
    from vendors.models import STANDARD_MENU_TYPES
    g = request.GET
    f = {"loc": g.get("loc", ""), "types": [t for t in g.getlist("type") if t in BT], "menus": [m for m in g.getlist("menu") if m in STANDARD_MENU_TYPES],
         "home": g.get("home") == "1", "open": g.get("open") == "1", "rating": g.get("rating", ""), "sort": g.get("sort", ""), "q": g.get("q", "").strip()[:60]}
    if f["loc"]:
        qs = qs.filter(Q(county_loc__slug=f["loc"]) | Q(area_loc__slug=f["loc"]))
    if f["types"]:
        qs = qs.filter(business_type__in=f["types"])
    for m in f["menus"]:
        qs = qs.filter(categories__name__iexact=m)
    if f["home"]:
        qs = qs.filter(home_service=True)
    if f["q"]:
        qs = qs.filter(Q(brand_name__icontains=f["q"]) | Q(items__name__icontains=f["q"]) | Q(tagline__icontains=f["q"]))
    qs = qs.distinct().annotate(avg_rating=Avg("reviews__stars", filter=Q(reviews__is_approved=True, reviews__verified_at__isnull=False)),
                                n_reviews=_C("reviews", filter=Q(reviews__is_approved=True, reviews__verified_at__isnull=False), distinct=True))
    if f["rating"] in ("3", "4", "4.5"):
        qs = qs.filter(avg_rating__gte=float(f["rating"]))
    if f["sort"] == "rating":
        qs = qs.order_by("-avg_rating", "-n_reviews", "brand_name")
    elif f["sort"] == "newest":
        qs = qs.order_by("-created_at")
    elif f["sort"] == "name":
        qs = qs.order_by("brand_name")
    if f["open"]:
        qs = [v for v in qs if v.is_open_now]  # computed per vendor; fine at directory scale
    f["loc_name"] = Location.objects.filter(slug=f["loc"]).values_list("name", flat=True).first() if f["loc"] else ""
    f["active"] = bool(f["loc"] or f["types"] or f["menus"] or f["home"] or f["open"] or f["rating"] or f["sort"] or f["q"])
    return qs, f


def _page(request, qs, ctx, template, hub=False):
    from vendors.models import STANDARD_MENU_TYPES
    qs = qs.prefetch_related("tags", "hours")
    base_count = qs.count()
    if not hub and base_count < MIN_VENDORS and not request.user.is_staff:
        raise Http404
    qs, filters = _apply_filters(request, qs)
    total = len(qs) if isinstance(qs, list) else qs.count()
    page, prefix = paginate(request, qs, 24)
    ctx.update({"vendors": page, "page": page, "qs": prefix, "total": total, "filters": filters,
                "filter_locations": Location.objects.filter(kind="county").order_by("name"),
                "filter_types": BUSINESS_TYPES, "filter_menus": STANDARD_MENU_TYPES})
    return render(request, template, ctx)


def types_index(request, type_plural):
    """/salons/ — all of a type, plus locations and services with counts. /beauty/ is every business."""
    row = _type(type_plural)
    qs = live().filter(business_type=row[0]) if row is not ALL_TYPES else live()
    locs = Location.objects.filter(Q(county_vendors__in=qs) | Q(area_vendors__in=qs)).annotate(n=Count("id")).order_by("-n", "name").distinct()
    tags = Tag.objects.filter(vendors__in=qs).annotate(n=Count("vendors")).order_by("-n")[:30]
    return _page(request, qs, {"row": row, "type_plural": type_plural, "locations": locs, "tags": tags, "loc": None,
                               "title": f"{row[3]} in Kenya — prices, reviews & online booking | BeautyFlow",
                               "h1": f"{row[3]} in Kenya",
                               "meta": f"Find {row[3].lower()} across Kenya on BeautyFlow: services with prices, photos, opening hours, reviews and online booking."},
                 "vendors/directory.html", hub=True)  # type hubs are linked from the header: always render


def places_in(request, type_plural, loc_slug):
    """/salons/kilimani/ or /spas/mombasa/"""
    row = _type(type_plural)
    loc = _loc(loc_slug)
    qs = _vendors_in(loc)
    if row is not ALL_TYPES:
        qs = qs.filter(business_type=row[0])
    tags = Tag.objects.filter(vendors__in=qs).annotate(n=Count("vendors")).order_by("-n")[:20]
    sub = loc.areas.filter(area_vendors__in=qs).annotate(n=Count("area_vendors")).order_by("-n").distinct() if loc.kind == "county" else Location.objects.none()
    where = loc.name if loc.kind == "county" else f"{loc.name}, {loc.county.name}"
    return _page(request, qs, {"row": row, "type_plural": type_plural, "loc": loc, "tags": tags, "locations": sub,
                               "title": f"{row[3]} in {loc.name} — prices & booking | BeautyFlow",
                               "h1": f"{row[3]} in {loc.name}",
                               "meta": f"Find {row[3].lower()} in {where}: services with prices, photos, opening hours, reviews and online booking. Updated by the businesses themselves."},
                 "vendors/directory.html")


def service_tag(request, tag_slug, loc_slug=None):
    """/services/knotless-braids/ and /services/knotless-braids/nairobi/"""
    tag = get_object_or_404(Tag, slug=tag_slug)
    qs = live().filter(Q(tags=tag) | Q(items__name__icontains=tag.name) | Q(categories__name__iexact=tag.name)).distinct()
    loc = _loc(loc_slug) if loc_slug else None
    if loc:
        qs = qs.filter(Q(county_loc=loc) | Q(area_loc=loc))
    locs = Location.objects.filter(Q(county_vendors__in=qs) | Q(area_vendors__in=qs)).annotate(n=Count("id")).order_by("-n").distinct() if not loc else Location.objects.none()
    where = loc.name if loc else "Kenya"
    label = tag.name
    return _page(request, qs, {"tag": tag, "loc": loc, "locations": locs, "row": None, "type_plural": ALL_TYPES[4],
                               "title": f"{label} in {where} — prices & booking | BeautyFlow",
                               "h1": f"{label} in {where}",
                               "meta": f"Where to get {label.lower()} in {where}: salons, spas and studios with prices, photos, reviews and online booking on BeautyFlow."},
                 "vendors/directory.html", hub=(tag.kind == "menu" and not loc))


def services_index(request):
    from vendors.models import STANDARD_MENU_TYPES
    from django.core.cache import cache
    from django.db.models.functions import Lower
    from vendors.models import MenuCategory
    counts = cache.get("services_index_counts")
    if counts is None:  # one grouped query instead of one count per menu type
        rows = MenuCategory.objects.filter(vendor__is_published=True, vendor__is_approved=True).annotate(lname=Lower("name")).values("lname").annotate(n=Count("vendor", distinct=True))
        by_lower = {r["lname"]: r["n"] for r in rows}
        counts = {name: by_lower.get(name.lower(), 0) for name in STANDARD_MENU_TYPES}
        cache.set("services_index_counts", counts, 600)
    menu_tags = [t for t in Tag.objects.filter(kind="menu")]
    menu_tags.sort(key=lambda t: STANDARD_MENU_TYPES.index(t.name) if t.name in STANDARD_MENU_TYPES else 99)
    for t in menu_tags:
        t.n = counts.get(t.name, 0)
    tags = Tag.objects.exclude(kind="menu").annotate(n=Count("vendors", filter=Q(vendors__is_published=True, vendors__is_approved=True))).filter(n__gte=MIN_VENDORS).order_by("kind", "-n")
    return render(request, "vendors/services_index.html", {"tags": tags, "menu_tags": menu_tags})


def price_lists(request):
    qs = live().for_cards().annotate(n_items=Count("items", filter=Q(items__is_available=True), distinct=True)).filter(n_items__gt=0).order_by("-plan", "-n_items")
    page, prefix = paginate(request, qs, 24)
    return render(request, "vendors/menus.html", {"vendors": page, "page": page, "qs": prefix, "total": qs.count()})


def vendor_redirect(request, slug):
    """Old /<slug>/ → canonical /<type>/<slug>/ (301)."""
    v = get_object_or_404(Vendor, slug=slug)
    return redirect(v.get_absolute_url(), permanent=True)


OWNER_PAGES = {
    "salon-software": ("Salon software in Kenya — POS, bookings & staff commission | BeautyFlow",
                       "Run your salon on BeautyFlow: a POS that tracks which stylist did each service, automatic commission, online bookings, payslips and reports. Built for Kenya, M-Pesa ready.", "salon"),
    "spa-software": ("Spa & massage software in Kenya — bookings, therapists & payouts | BeautyFlow",
                     "Spa and wellness software for Kenya: online booking, therapist schedules, commission and payouts, client history and a POS that takes M-Pesa.", "spa"),
    "barbershop-software": ("Barbershop POS in Kenya — track every cut and pay your barbers | BeautyFlow",
                            "A barbershop POS for Kenya: ring up cuts per barber, pay commission in one tap, see who brings in the most, and take bookings online.", "barber"),
    "booking-page": ("Free online booking page for salons, spas & barbers in Kenya | BeautyFlow",
                     "Get a free booking page with your services, prices, team and photos. Clients book a slot with the stylist they want; you confirm on WhatsApp.", "booking"),
    "list-your-business": ("List your salon, spa or barbershop in Kenya — free | BeautyFlow",
                           "List your beauty or wellness business on BeautyFlow for free: show your prices and team, get found on Google for “salons in …” searches, and take bookings.", "listing"),
}


def owner_page(request, page):
    if page not in OWNER_PAGES:
        raise Http404
    title, meta, kind = OWNER_PAGES[page]
    return render(request, "vendors/owner_page.html", {"title": title, "meta": meta, "page": page, "kind": kind,
                                                       "vendor_count": live().count()})


def healthz(request):
    """Uptime probe: DB + cache reachable → 200 'ok'."""
    from django.core.cache import cache
    from django.db import connection
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
        cache.set("healthz", "1", 30)
        return HttpResponse("ok", content_type="text/plain")
    except Exception:
        return HttpResponse("unhealthy", status=503, content_type="text/plain")


def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /dashboard/\nDisallow: /pos/\nDisallow: /admin/\nDisallow: /django-admin/\nDisallow: /login/\nDisallow: /signup/\nDisallow: /r/\nDisallow: /webhooks/\nDisallow: /healthz/\n"
                        f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}\n", content_type="text/plain")


# ── Sitemaps ───────────────────────────────────────────────────────────

class VendorSitemap(Sitemap):
    changefreq, priority = "weekly", 0.8

    def items(self):
        return live()

    def lastmod(self, v):
        return v.created_at


class DirectorySitemap(Sitemap):
    changefreq, priority = "weekly", 0.7

    def items(self):
        from django.core.cache import cache
        return cache.get_or_set("sitemap_directory_urls", self._build, 3600)

    def _build(self):
        urls = [reverse("types_index", args=[ALL_TYPES[4]]), reverse("services_index"), reverse("price_lists")]
        for row in BUSINESS_TYPES:
            if live().filter(business_type=row[0]).count() >= MIN_VENDORS:
                urls.append(reverse("types_index", args=[row[4]]))
        for loc in Location.objects.all():
            qs = _vendors_in(loc)
            if qs.count() >= MIN_VENDORS:
                urls.append(reverse("places_in", args=[ALL_TYPES[4], loc.slug]))
                for row in BUSINESS_TYPES:
                    if qs.filter(business_type=row[0]).count() >= MIN_VENDORS:
                        urls.append(reverse("places_in", args=[row[4], loc.slug]))
        for tag in Tag.objects.all():
            qs = live().filter(Q(tags=tag) | Q(items__name__icontains=tag.name) | Q(categories__name__iexact=tag.name)).distinct()
            if qs.count() >= MIN_VENDORS:
                urls.append(reverse("service_tag", args=[tag.slug]))
                for loc in Location.objects.filter(kind="county"):
                    if qs.filter(Q(county_loc=loc) | Q(area_loc=loc)).count() >= MIN_VENDORS:
                        urls.append(reverse("service_tag_in", args=[tag.slug, loc.slug]))
        return urls

    def location(self, item):
        return item


class StaticSitemap(Sitemap):
    changefreq, priority = "monthly", 0.5

    def items(self):
        return ([reverse("home"), reverse("about"), reverse("features"), reverse("pricing"), reverse("deals"), reverse("terms"), reverse("privacy")]
                + [reverse("owner_page", args=[p]) for p in OWNER_PAGES])

    def location(self, item):
        return item


SITEMAPS = {"vendors": VendorSitemap, "directory": DirectorySitemap, "static": StaticSitemap}
