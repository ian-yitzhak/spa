"""Dev seed: python manage.py shell < seed.py"""
from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from pos.models import Booking, Staff, StaffService, StaffShift
from vendors.models import MenuCategory, MenuItem, Offer, OpeningHours, Review, SiteSettings, Vendor

SiteSettings.get()
if not User.objects.filter(email="admin@beautyflow.co.ke").exists():
    User.objects.create_superuser(username="admin", email="admin@beautyflow.co.ke", password="admin1234", first_name="Admin",
                                  phone="254700000000", email_verified=True)


def team_member(v, name, email, role, title="", kind="percent", rate=0):
    u = User.objects.create_user(username=email, email=email, password="staff1234", first_name=name, phone="0722000000",
                                 role=User.Role.TEAM, email_verified=True)
    return Staff.objects.create(vendor=v, user=u, role=role, job_title=title, branch=v.main_branch(),
                                commission_type=kind, commission_value=rate, hired_on=timezone.localdate() - timedelta(days=200))


if not User.objects.filter(email="owner@beautyflow.co.ke").exists():
    u = User.objects.create_user(username="owner@beautyflow.co.ke", email="owner@beautyflow.co.ke", password="owner1234",
                                 first_name="Wanjiru", phone="0712345678", email_verified=True)
    v = Vendor.objects.create(owner=u, brand_name="Glow Studio Kilimani", business_type="salon", tagline="Braids, nails & glow facials in Kilimani",
                              county="Nairobi", town="Kilimani", address="Argwings Kodhek Rd, next to Yaya Centre", phone="0712345678",
                              whatsapp="0712345678", email=u.email, about="<p>Relaxed studio for natural hair, nails and skin.</p>")
    v.extend_pos(1)
    for d in range(7):
        OpeningHours.objects.update_or_create(vendor=v, day=d, defaults={"opens": "08:00", "closes": "19:00", "closed": d == 6})
    hair = MenuCategory.objects.create(vendor=v, name="Braids & locs", order=1)
    nails = MenuCategory.objects.create(vendor=v, name="Nails", order=3)
    skin = MenuCategory.objects.create(vendor=v, name="Facials & skin care", order=6)
    knot = MenuItem.objects.create(vendor=v, category=hair, name="Knotless braids — mid-back", net_price=4500, duration_min=300)
    loc = MenuItem.objects.create(vendor=v, category=hair, name="Locs retwist", net_price=2000, duration_min=120)
    gel = MenuItem.objects.create(vendor=v, category=nails, name="Gel manicure", net_price=1500, duration_min=60,
                                  discount_type="percent", discount_value=20)
    pedi = MenuItem.objects.create(vendor=v, category=nails, name="Spa pedicure", net_price=1800, duration_min=75)
    facial = MenuItem.objects.create(vendor=v, category=skin, name="Glow facial", net_price=3500, duration_min=60)
    amina = team_member(v, "Amina", "amina@beautyflow.co.ke", Staff.Role.STAFF, "Senior braider", "percent", 40)
    joy = team_member(v, "Joy", "joy@beautyflow.co.ke", Staff.Role.STAFF, "Nail tech", "fixed", 300)
    team_member(v, "Brian", "cashier@beautyflow.co.ke", Staff.Role.CASHIER, "Front desk")
    for s in (knot, loc):
        StaffService.objects.create(staff=amina, service=s)
    StaffService.objects.create(staff=joy, service=gel)
    StaffService.objects.create(staff=joy, service=pedi, commission_type="percent", commission_value=25)
    today = timezone.localdate()
    for i in range(6):
        for s, t in ((amina, ("08:00", "17:00")), (joy, ("10:00", "19:00"))):
            StaffShift.objects.create(vendor=v, branch=v.main_branch(), staff=s, date=today + timedelta(days=i), starts=t[0], ends=t[1])
    Booking.objects.create(vendor=v, branch=v.main_branch(), staff=amina, name="Faith", phone="0733111222",
                           date=today, time="10:00").set_services([knot])
    Booking.objects.create(vendor=v, branch=v.main_branch(), staff=joy, name="Mercy", phone="0733111333",
                           date=today + timedelta(days=1), time="14:00", status=Booking.Status.CONFIRMED).set_services([gel, pedi])
    Offer.objects.create(vendor=v, title="Mid-week glow — 20% off facials", details="Tuesday to Thursday")
    Review.objects.create(vendor=v, name="Kevin", email="kevin@example.com", stars=5, comment="Neatest braids in town!",
                          verified_at=timezone.now())
print("Seeded. Admin admin@beautyflow.co.ke / admin1234 · Owner owner@beautyflow.co.ke / owner1234 · "
      "Staff amina@ / joy@ and cashier cashier@beautyflow.co.ke / staff1234")
