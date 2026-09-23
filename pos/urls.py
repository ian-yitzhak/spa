from django.urls import path

from . import views

urlpatterns = [
    # POS (owner and cashier)
    path("", views.home, name="pos_home"),
    path("add/<uuid:pk>/", views.add_item, name="pos_add"),
    path("staff/pick/", views.ticket_staff, name="pos_ticket_staff"),
    path("line/<uuid:pk>/<str:direction>/", views.line_qty, name="pos_line"),
    path("client/", views.set_client, name="pos_set_client"),
    path("discount/", views.set_discount, name="pos_discount"),
    path("clear/", views.clear, name="pos_clear"),
    path("hold/", views.hold, name="pos_hold"),
    path("pay/", views.pay, name="pos_pay"),
    path("open/", views.open_tickets, name="pos_open"),
    path("open/<uuid:pk>/resume/", views.resume, name="pos_resume"),
    path("sales/", views.sales, name="pos_sales"),
    path("sales/<uuid:pk>/void/", views.void, name="pos_void"),
    path("reports/", views.reports, name="pos_reports"),
    path("receipt/<uuid:pk>/", views.receipt, name="pos_receipt"),
    path("receipt/<uuid:pk>/pdf/", views.receipt_pdf, name="pos_receipt_pdf"),
    path("insights/", views.insights, name="pos_insights"),
    path("insights/ask/", views.insights_ask, name="pos_insights_ask"),
    # everyone on the team
    path("me/", views.me, name="pos_me"),
    path("profile/", views.profile, name="pos_profile"),
    path("bookings/", views.bookings, name="pos_bookings"),
    path("bookings/badge/", views.bookings_badge, name="pos_bookings_badge"),
    path("bookings/<uuid:pk>/", views.booking_edit, name="pos_booking_edit"),
    path("bookings/<uuid:pk>/status/", views.booking_status, name="pos_booking_status"),
    path("bookings/<uuid:pk>/start/", views.booking_start, name="pos_booking_start"),
    path("payouts/<uuid:pk>/", views.payout_receipt, name="pos_payout"),
    # owner: team, HR, rota, money out
    path("staff/", views.staff_list, name="pos_staff"),
    path("staff/<uuid:pk>/", views.staff_detail, name="pos_staff_detail"),
    path("staff/<uuid:pk>/edit/", views.staff_edit, name="pos_staff_edit"),
    path("staff/<uuid:pk>/pay/", views.staff_pay, name="pos_staff_pay"),
    path("staff/<uuid:pk>/toggle/", views.staff_toggle, name="pos_staff_toggle"),
    path("payouts/", views.payouts, name="pos_payouts"),
    path("shifts/", views.shifts, name="pos_shifts"),
    path("shifts/<uuid:pk>/", views.shift_status, name="pos_shift_status"),
    path("expenses/", views.expenses, name="pos_expenses"),
    path("expenses/<uuid:pk>/", views.expense_edit, name="pos_expense_edit"),
    path("expenses/<uuid:pk>/delete/", views.expense_delete, name="pos_expense_delete"),
    path("branches/", views.branches, name="pos_branches"),
]
