from django.db import migrations
from django.utils.text import slugify

from vendors.models import STANDARD_MENU_TYPES

TAGS = {
    "dish": ["Knotless braids", "Box braids", "Cornrows", "Locs & retwist", "Weaves & wigs", "Silk press", "Relaxer", "Hair colour",
             "Haircut", "Fade", "Beard trim", "Shave", "Gel nails", "Acrylic nails", "Manicure", "Pedicure", "Lash extensions",
             "Brow shaping", "Bridal makeup", "Facial", "Waxing", "Deep tissue massage", "Swedish massage", "Hot stone massage",
             "Body scrub", "Steam & sauna"],
    "cuisine": ["Natural hair", "Men's grooming", "Kids' hair", "Bridal", "Skin care", "Organic products", "Aromatherapy"],
    "meal": ["Home visits", "Walk-ins welcome", "Open Sundays", "Late opening", "Couples", "Group bookings"],
    "menu": STANDARD_MENU_TYPES,
}


def seed(apps, schema_editor):
    Tag = apps.get_model("vendors", "Tag")
    for kind, names in TAGS.items():
        for n in names:
            Tag.objects.get_or_create(slug=slugify(n), defaults={"name": n, "kind": kind})


class Migration(migrations.Migration):
    dependencies = [("vendors", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
