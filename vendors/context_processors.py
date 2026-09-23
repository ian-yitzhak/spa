from .models import SiteSettings


def site_settings(request):
    from django.conf import settings
    return {"site": SiteSettings.get(), "TURNSTILE_SITE_KEY": settings.TURNSTILE_SITE_KEY}
