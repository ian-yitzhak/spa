from .models import AuditLog


def log_event(actor, action, detail="", request=None):
    ip = ua = None
    if request is not None:
        from vendors.security import client_ip
        ip = client_ip(request)
        ua = (request.META.get("HTTP_USER_AGENT") or "")[:200]
    try:
        AuditLog.objects.create(actor=actor if getattr(actor, "pk", None) else None, action=action, detail=str(detail)[:300], ip=ip, user_agent=ua or "")
    except Exception:
        pass  # never break a request because logging failed
