# BeautyFlow — food vendor directory (Django + HTMX)

## Run locally (SQLite)
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py shell < seed.py     # demo data (optional)
.venv/bin/python manage.py runserver
```
- Public site: http://127.0.0.1:8000/
- Vendor dashboard: http://127.0.0.1:8000/dashboard/ (mama@beautyflow.co.ke / vendor1234)
- Admin panel (custom, sidebar): http://127.0.0.1:8000/admin/ (admin@beautyflow.co.ke / admin1234)
- Raw Django admin (fallback only): http://127.0.0.1:8000/django-admin/

## Plans
- **Free**: limits set in Admin → Plans & settings (default 10 menu items, 3 photos).
- **Premium**: monthly fee set in Admin → Plans & settings. Vendor pays (M-Pesa) and sends
  confirmation on WhatsApp; admin clicks "Activate Premium" / "+1 month" on the vendor — each
  click adds 30 days. When it lapses the vendor automatically falls back to Free limits.

## Email (verification codes + login OTP)
Config lives in `.env` (copy `.env.example`). Locally `EMAIL_BACKEND=console` prints every
email — including the 6-digit codes — in the `runserver` terminal. On the server set
`EMAIL_BACKEND=smtp` with the mail.isoftke.co.ke credentials (port 465, SSL).
Note: many home/mobile ISPs block outbound SMTP ports, so real sending only works from the server.

Sessions last 60 days (sliding) until the user logs out.

## Production
Set env vars `SECRET_KEY`, `DEBUG=0`, `ALLOWED_HOSTS=beautyflow.co.ke,www.beautyflow.co.ke`,
run `collectstatic`, and serve `/media/` via nginx.
