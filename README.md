# BeautyFlow — salon, spa & barbershop SaaS (Django + HTMX)

Public directory + booking pages for salons, spas, barbers, nail studios, makeup artists, massage,
beauty shops and wellness — and a business portal: POS by staff member, commission, payouts, bookings,
staff shifts, reports. beautyflow.co.ke

## Run locally
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # EMAIL_BACKEND=console locally
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createcachetable
.venv/bin/python manage.py shell < seed.py     # demo salon (optional)
.venv/bin/python manage.py runserver
.venv/bin/python manage.py test                # POS / commission / payout / access tests
```
Demo logins (from `seed.py`):
- Admin: admin@beautyflow.co.ke / admin1234 → /admin/
- Owner: owner@beautyflow.co.ke / owner1234 → /dashboard/
- Staff: amina@beautyflow.co.ke, joy@beautyflow.co.ke / staff1234 → /pos/me/
- Cashier: cashier@beautyflow.co.ke / staff1234 → /pos/me/

## CSS
Tailwind is compiled ahead of time into `static/css/tw.css` (committed). After changing classes in
templates or Python, run `./bin/build-css` (downloads nothing — put the standalone Tailwind v3.4 CLI at
`bin/tailwindcss` or on your PATH) and commit the result. Don't go back to `cdn.tailwindcss.com`: it
compiles CSS in every visitor's browser and made pages slow.

## Roles
- **Owner** — everything: services & prices (with discounts), service photos, offers, POS, bookings,
  sales, reports, insights, clients, expenses, staff (HR), staff shifts, payouts, branches, billing.
- **Cashier** — Dashboard, POS, Sales, Bookings, Reports, Insights, Profile.
- **Staff** — Dashboard, Sales (their own paid services and commission — read only), Bookings (their own), Profile (payslips).

## How commission works
Each staff member has a default rate (percent of the service, or fixed KES per service) and can have
their own rate on specific services (`StaffService`). On the POS every service line is attached to the
person who did it; payment is refused until every line has someone. When the sale is paid,
`Order.settle_commissions()` books each line's commission on what the client actually paid (a sale
discount reduces everyone's share). The owner pays out from Staff → person → "Mark as paid", which
creates a `StaffPayout` (bonus / deduction allowed) and links the lines to it; the staff member sees the
payslip. A sale whose commission has been paid out can't be voided.

## Payments (Paystack)
Plans are paid by card or M-Pesa via Paystack checkout. Keys in `.env` (`PAYSTACK_PUBLIC_KEY`,
`PAYSTACK_SECRET_KEY`). The browser returns to `/dashboard/pay/done/`, which verifies with Paystack.
Set the webhook URL in the Paystack dashboard to `https://beautyflow.co.ke/webhooks/paystack/`
(signed with the secret key). `manage.py reconcile_payments` re-checks unfinished checkouts.

## Email
`.env`: `EMAIL_HOST=mail.isoftke.com`, port 465 SSL, `EMAIL_HOST_USER=beauty@isoftke.com`.
Locally `EMAIL_BACKEND=console` prints mails (and login codes) in the runserver terminal.

## Production
`SECRET_KEY`, `DEBUG=0`, `ALLOWED_HOSTS=beautyflow.co.ke,www.beautyflow.co.ke`, `SITE_URL`, Postgres via
`DB_NAME/DB_USER/DB_PASSWORD`, `collectstatic`, serve `/media/` with nginx. See DEPLOY.md.
