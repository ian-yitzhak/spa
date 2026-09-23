from django.core.paginator import Paginator


def paginate(request, queryset, per_page=20):
    """Return (page, qs_prefix). qs_prefix keeps current filters in page links."""
    page = Paginator(queryset, per_page).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    prefix = params.urlencode()
    return page, (prefix + "&") if prefix else ""
