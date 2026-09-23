from django.db.models.signals import post_save
from django.dispatch import receiver

from vendors.models import MenuItem

from .models import Referral


@receiver(post_save, sender=MenuItem)
def qualify_on_first_item(sender, instance, created, **kwargs):
    if created:
        ref = Referral.objects.filter(vendor_id=instance.vendor_id, status=Referral.Status.PENDING).select_related("vendor__owner").first()
        if ref:
            ref.check_qualified()
