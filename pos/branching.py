"""Which branch is in force for this request.

The owner may look at one branch or at all of them; staff only ever see the branch they work at.
Kept out of pos.views so the vendor dashboard can use exactly the same rules.
"""

BRANCH_KEY = "pos_branch"


def resolve(request):
    """Staff are locked to their branch. The owner picks one, or 'All'.
    request.branch is the branch in force (None = all branches); request.write_branch is where new work is filed."""
    v = request.vendor
    branches = list(v.branches.filter(is_active=True))
    request.branches = branches
    main = next((b for b in branches if b.is_main), branches[0] if branches else None)
    multi = v.branches_enabled and len(branches) > 1
    staff = getattr(request, "staff", None)
    if staff is not None:
        request.write_branch = staff.branch or main
        request.branch = request.write_branch if multi else None
        return
    if not v.branches_enabled:                      # branches not switched on: nothing to filter
        request.branch, request.write_branch = None, main
        return
    chosen = request.GET.get("branch") or request.session.get(BRANCH_KEY) or ""
    if request.GET.get("branch") is not None:
        request.session[BRANCH_KEY] = chosen
    if chosen == "all":
        # with a single branch "all" IS that branch, so work still has somewhere to go
        request.branch = None
        request.write_branch = main if not multi else None
        return
    picked = next((b for b in branches if str(b.pk) == str(chosen)), None) or main
    request.branch = request.write_branch = picked


def scope(request, qs, field="branch"):
    """Limit a queryset to the branch in force. 'All' shows everything for this vendor."""
    b = getattr(request, "branch", None)
    return qs.filter(**{field: b}) if b is not None else qs
