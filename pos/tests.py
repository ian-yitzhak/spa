from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from vendors.models import MenuItem, Vendor

from .models import Booking, Order, OrderItem, Staff, StaffPayout, StaffService


def make_user(email, role=User.Role.VENDOR, **kw):
    return User.objects.create_user(username=email, email=email, password="pass12345!", role=role, email_verified=True, **kw)


class SalonCase(TestCase):
    def setUp(self):
        self.owner = make_user("owner@t.co", first_name="Owner")
        self.v = Vendor.objects.create(owner=self.owner, brand_name="Test Salon")
        self.v.extend_pos(1)
        self.braids = MenuItem.objects.create(vendor=self.v, name="Braids", net_price=4000, duration_min=240)
        self.nails = MenuItem.objects.create(vendor=self.v, name="Gel nails", net_price=1000, discount_type="amount", discount_value=100)
        self.amina = self.staff("amina@t.co", Staff.Role.STAFF, "percent", 40)
        self.joy = self.staff("joy@t.co", Staff.Role.STAFF, "fixed", 300)
        self.cashier = self.staff("cash@t.co", Staff.Role.CASHIER)
        StaffService.objects.create(staff=self.amina, service=self.braids)
        StaffService.objects.create(staff=self.joy, service=self.nails, commission_type="percent", commission_value=50)

    def staff(self, email, role, kind="percent", rate=0):
        u = make_user(email, User.Role.TEAM, first_name=email.split("@")[0].title())
        return Staff.objects.create(vendor=self.v, user=u, role=role, commission_type=kind, commission_value=rate)

    def ring_up(self, staff, *items, discount=None):
        """Cashier builds a ticket through the real POS views: one person does it all, then cash."""
        self.client.force_login(self.cashier.user)
        self.client.get("/pos/")
        self.client.post("/pos/staff/pick/", {"staff": staff.pk})
        for item in items:
            self.client.post(f"/pos/add/{item.pk}/")
        if discount:
            self.client.post("/pos/discount/", {"discount_value": discount})
        r = self.client.post("/pos/pay/", {"method": "cash"})
        self.assertEqual(r.status_code, 200, r.content)
        return Order.objects.filter(vendor=self.v, paid_at__isnull=False).latest("paid_at")


class CommissionTests(SalonCase):
    def test_service_discount_and_commission(self):
        o = self.ring_up(self.amina, self.braids)
        self.assertEqual(o.items.get().commission, Decimal("1600.00"))      # 40% of 4000
        self.assertEqual(o.cashier, self.cashier.user)
        o = self.ring_up(self.joy, self.nails)
        self.assertEqual(o.total, Decimal("900.00"))                        # 1000 less KES 100
        self.assertEqual(o.items.get().commission, Decimal("450.00"))       # own rate: 50% of 900

    def test_sale_discount_shared_by_commission(self):
        o = self.ring_up(self.amina, self.braids, discount="1000")
        self.assertEqual(o.total, Decimal("3000.00"))
        self.assertEqual(o.items.get().commission, Decimal("1200.00"))      # 40% of what was actually paid

    def test_fixed_commission_per_service(self):
        MenuItem.objects.filter(pk=self.nails.pk)
        StaffService.objects.filter(staff=self.joy).delete()
        o = self.ring_up(self.joy, self.nails, self.nails)
        line = o.items.get()
        self.assertEqual(line.qty, 2)
        self.assertEqual(line.commission, Decimal("600.00"))                # KES 300 x 2

    def test_cannot_pay_without_staff(self):
        self.client.force_login(self.cashier.user)
        self.client.post(f"/pos/add/{self.braids.pk}/")
        r = self.client.post("/pos/pay/", {"method": "cash"})
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"Done by", r.content)

    def test_one_staff_for_the_whole_ticket(self):
        self.client.force_login(self.cashier.user)
        self.client.post(f"/pos/add/{self.braids.pk}/")
        self.client.post(f"/pos/add/{self.nails.pk}/")
        self.client.post("/pos/staff/pick/", {"staff": self.amina.pk})      # picked after adding: both lines get her
        self.assertEqual({l.staff for l in OrderItem.objects.all()}, {self.amina})
        self.client.post(f"/pos/add/{self.braids.pk}/")                     # added after: goes to her too
        self.client.post("/pos/staff/pick/", {"staff": self.joy.pk})        # switch the whole ticket
        self.assertEqual({l.staff for l in OrderItem.objects.all()}, {self.joy})
        self.assertEqual(OrderItem.objects.get(menu_item=self.braids).qty, 2)
        r = self.client.post("/pos/pay/", {"method": "mpesa"})              # M-Pesa needs no code
        self.assertEqual(r.status_code, 200)


class PayoutTests(SalonCase):
    def test_owner_pays_staff_and_staff_sees_payslip(self):
        o = self.ring_up(self.amina, self.braids)
        self.assertEqual(self.amina.balance(), Decimal("1600.00"))
        self.client.force_login(self.owner)
        line = o.items.get()
        r = self.client.post(f"/pos/staff/{self.amina.pk}/pay/", {"line": [line.pk], "method": "mpesa", "reference": "QWE123",
                                                                  "bonus": "100", "deduction": "50"})
        p = StaffPayout.objects.get()
        self.assertRedirects(r, f"/pos/payouts/{p.pk}/")
        self.assertEqual(p.amount, Decimal("1650.00"))
        self.assertEqual(self.amina.balance(), 0)
        # Amina sees it; Joy can't open it
        self.client.force_login(self.amina.user)
        self.assertContains(self.client.get(f"/pos/payouts/{p.pk}/"), "1,650")
        self.assertContains(self.client.get("/pos/profile/"), f"#{p.number}")
        self.client.force_login(self.joy.user)
        self.assertEqual(self.client.get(f"/pos/payouts/{p.pk}/").status_code, 404)

    def test_receipt_names_the_stylist_once(self):
        o = self.ring_up(self.amina, self.braids, self.nails)
        self.client.force_login(self.owner)
        page = self.client.get(f"/pos/receipt/{o.pk}/").content.decode()
        self.assertEqual(page.count("Amina"), 1)
        self.assertIn("Done by", page)
        self.assertNotIn("Void", page)


class AccessTests(SalonCase):
    def test_staff_pages(self):
        self.ring_up(self.amina, self.braids); self.ring_up(self.joy, self.nails)
        self.client.force_login(self.amina.user)
        for url in ("/pos/me/", "/pos/sales/", "/pos/bookings/", "/pos/profile/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        sales = self.client.get("/pos/sales/").content.decode()
        self.assertIn("Braids", sales)
        self.assertNotIn("Gel nails", sales)                                # only her own services
        for url in ("/pos/", "/pos/reports/", "/pos/staff/", "/pos/insights/", "/pos/shifts/"):
            self.assertRedirects(self.client.get(url), "/pos/me/", fetch_redirect_response=False)
        self.assertEqual(self.client.post("/pos/pay/", {"method": "cash"}).status_code, 302)   # staff can't take money

    def test_cashier_pages(self):
        self.client.force_login(self.cashier.user)
        for url in ("/pos/me/", "/pos/", "/pos/sales/", "/pos/reports/", "/pos/insights/", "/pos/profile/", "/pos/bookings/", "/pos/open/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        for url in ("/pos/staff/", "/pos/payouts/", "/pos/shifts/", "/pos/expenses/"):
            self.assertRedirects(self.client.get(url), "/pos/me/", fetch_redirect_response=False)

    def test_owner_pages(self):
        self.ring_up(self.amina, self.braids)
        self.client.force_login(self.owner)
        for url in ("/dashboard/", "/dashboard/menu/", "/dashboard/menu/new/", f"/dashboard/menu/{self.nails.pk}/", "/dashboard/gallery/",
                    "/dashboard/inquiries/", "/dashboard/customers/", "/dashboard/upgrade/", "/dashboard/payments/",
                    "/pos/", "/pos/sales/", "/pos/reports/?period=monthly", "/pos/insights/", "/pos/staff/",
                    f"/pos/staff/{self.amina.pk}/", f"/pos/staff/{self.amina.pk}/edit/", "/pos/payouts/", "/pos/shifts/",
                    "/pos/bookings/", "/pos/expenses/", "/pos/open/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_other_business_is_invisible(self):
        other = Vendor.objects.create(owner=make_user("x@t.co"), brand_name="Other")
        self.client.force_login(other.owner)
        self.assertEqual(self.client.get(f"/pos/staff/{self.amina.pk}/").status_code, 402)   # its POS isn't paid
        other.extend_pos(1)
        self.assertEqual(self.client.get(f"/pos/staff/{self.amina.pk}/").status_code, 404)


class StaffFormTests(SalonCase):
    def test_owner_adds_staff_with_services_and_rates(self):
        self.client.force_login(self.owner)
        r = self.client.post("/pos/staff/", {
            "first_name": "Wambui", "role": "staff", "job_title": "Therapist", "email": "wambui@t.co", "phone": "0711222333",
            "password": "Str0ng-pass-99", "commission_type": "percent", "commission_value": "30", "show_on_site": "on",
            f"svc:{self.braids.pk}": "on", f"svc:{self.nails.pk}": "on", f"svc_type:{self.nails.pk}": "fixed",
            f"svc_rate:{self.nails.pk}": "250"})
        st = Staff.objects.get(user__email="wambui@t.co")
        self.assertRedirects(r, f"/pos/staff/{st.pk}/")
        self.assertEqual(st.rate_for(self.braids), ("percent", Decimal("30.00")))
        self.assertEqual(st.rate_for(self.nails), ("fixed", Decimal("250.00")))
        self.assertTrue(self.client.login(username="wambui@t.co", password="Str0ng-pass-99"))


class BookingTests(SalonCase):
    def test_booking_to_sale(self):
        b = Booking.objects.create(vendor=self.v, staff=self.amina, name="Faith", phone="0733111222",
                                   date=timezone.localdate(), time="10:00")
        b.set_services([self.braids])
        self.client.force_login(self.cashier.user)
        self.assertRedirects(self.client.post(f"/pos/bookings/{b.pk}/start/"), "/pos/", fetch_redirect_response=False)
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.CONFIRMED)
        self.assertEqual(b.order.items.get().staff, self.amina)
        self.client.post("/pos/pay/", {"method": "mpesa", "ref": "ABC"})
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.DONE)
        self.assertEqual(b.order.customer_name, "Faith")

    def test_staff_only_sees_own_bookings(self):
        Booking.objects.create(vendor=self.v, staff=self.amina, name="Faith", phone="0733111222",
                               date=timezone.localdate() + timedelta(days=1), time="10:00").set_services([self.braids])
        Booking.objects.create(vendor=self.v, staff=self.joy, name="Mercy", phone="0733111333",
                               date=timezone.localdate() + timedelta(days=1), time="11:00").set_services([self.nails])
        self.client.force_login(self.amina.user)
        page = self.client.get("/pos/bookings/").content.decode()
        self.assertIn("Faith", page)
        self.assertNotIn("Mercy", page)


class PublicBookingTests(SalonCase):
    def test_client_books_several_services(self):
        from django.urls import reverse
        url = reverse("reserve", args=[self.v.type_slug, self.v.slug])
        day = (timezone.localdate() + timedelta(days=2)).isoformat()
        r = self.client.post(url, {"services": [self.braids.pk, self.nails.pk], "date": day, "time": "10:00",
                                   "name": "Wanjiku", "phone": "0712345678"})
        self.assertContains(r, "Booking request sent")
        b = Booking.objects.get(name="Wanjiku")
        self.assertEqual([l.name for l in b.items.all()], ["Braids", "Gel nails"])
        self.assertEqual(b.duration_min, 240 + 60)
        self.assertEqual(b.total, Decimal("4900.00"))                      # nails at their 10% discount
        # the cashier opens a ticket with both services on it
        self.client.force_login(self.cashier.user)
        self.client.post(f"/pos/bookings/{b.pk}/start/")
        b.refresh_from_db()
        self.assertEqual(sorted(l.name for l in b.order.items.all()), ["Braids", "Gel nails"])

    def test_booking_needs_a_service(self):
        from django.urls import reverse
        r = self.client.post(reverse("reserve", args=[self.v.type_slug, self.v.slug]),
                             {"date": (timezone.localdate() + timedelta(days=1)).isoformat(), "time": "10:00",
                              "name": "X", "phone": "0712345678"})
        self.assertContains(r, "Add at least one service")
        self.assertFalse(Booking.objects.exists())

    def test_public_page_has_no_team_or_qr(self):
        self.v.is_published = True
        self.v.save()
        page = self.client.get(self.v.get_absolute_url()).content.decode()
        self.assertNotIn("Meet the team", page)
        self.assertNotIn("Ask a question or get a quote", page)
        self.assertIn('data-add="', page)
