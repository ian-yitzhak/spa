"""Branch pricing: the same services everywhere, with a price a branch can override."""
from .models import BranchPrice


def price_items(items, branch=None):
    """Set .list_price, .shown_price (after the service's discount) and .own_price on each item, in one query."""
    items = list(items)
    rows = {}
    if branch is not None and items:
        rows = {r.item_id: r for r in BranchPrice.objects.filter(branch=branch, item__in=items)}
    for i in items:
        row = rows.get(i.pk)
        i.list_price = row.price if row else i.price
        i.shown_price = i.apply_discount(i.list_price)
        i.own_price = row is not None
    return items
