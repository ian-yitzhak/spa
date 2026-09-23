from decimal import Decimal

from django.db import migrations


def percent_to_kes(apps, schema_editor):
    """Service discounts are KES off now; turn any percentage into the amount it took off."""
    MenuItem = apps.get_model("vendors", "MenuItem")
    for it in MenuItem.objects.filter(discount_type="percent"):
        off = (Decimal(it.price) * min(Decimal(it.discount_value), Decimal(100)) / 100).quantize(Decimal("1"))
        it.discount_type, it.discount_value = ("amount", off) if off else ("", 0)
        it.save(update_fields=["discount_type", "discount_value"])


class Migration(migrations.Migration):
    dependencies = [("vendors", "0003_remove_qr_menu_token")]
    operations = [migrations.RunPython(percent_to_kes, migrations.RunPython.noop)]
