# BeautyFlow — Deployment

Dedicated VPS **173.249.23.183** (Ubuntu 24.04, 8 GB RAM, 96 GB disk). Nothing else runs on it.
Set up 23 Sep 2026. The app answers on `http://173.249.23.183/` now; **https://beautyflow.co.ke**
goes live once DNS points here and the certificate is issued (see "Going live").

## Server layout

| Item | Value |
|---|---|
| OS | Ubuntu 24.04, Python 3.12, nginx 1.24, PostgreSQL 16 — timezone Africa/Nairobi |
| SSH | `ssh root@173.249.23.183` (port 22) |
| System user | `beautyflow` (owns everything below) |
| Code | `/home/beautyflow/app` |
| Virtualenv | `/home/beautyflow/venv` |
| Env / secrets | `/home/beautyflow/app/.env` (mode 600, never in git) |
| Uploads (media) | `/home/beautyflow/app/media` — served by nginx at `/media/` |
| Static files | `/home/beautyflow/app/staticfiles` — served by nginx at `/static/` |
| App server | gunicorn, 3 workers, `127.0.0.1:8020` — systemd unit `beautyflow.service` |
| Reverse proxy | `/etc/nginx/sites-available/beautyflow` (symlinked into `sites-enabled`, the default site is removed) |
| Database | PostgreSQL db `beautyflow`, role `beautyflow`, listens on localhost only. Password in `.env` and `/root/.beautyflow-db-pass` |
| Firewall | `ufw`: only SSH (22), HTTP (80), HTTPS (443) |
| Brute force | `fail2ban` on sshd — 5 failures = 1 h ban (`fail2ban-client status sshd`) |
| Logs | `journalctl -u beautyflow -f` · `/var/log/nginx/beautyflow.{access,error}.log` |

## First admin

`ianenoch11@gmail.com` (superuser, email pre-verified). The starting password is in
`/root/beautyflow-admin.txt` on the server — change it after the first login.
Log in at `/login/`; a 6-digit code is emailed, then you land on `/admin/`.

## Going live (DNS + HTTPS)

1. At the domain's DNS (registrar or Cloudflare) create:
   - `A  beautyflow.co.ke      → 173.249.23.183`
   - `A  www.beautyflow.co.ke  → 173.249.23.183` (or a CNAME to the apex)
   If you use Cloudflare, leave the records **grey-cloud (DNS only)** until step 2 is done.
2. On the server, once `dig +short beautyflow.co.ke` shows the new IP:
   ```bash
   certbot --nginx -d beautyflow.co.ke -d www.beautyflow.co.ke --redirect -m ianenoch11@gmail.com --agree-tos -n
   systemctl reload nginx
   ```
   Certbot adds the 443 server block and the HTTP→HTTPS redirect to the nginx site and renews by
   itself (`systemctl list-timers certbot.timer`). With Cloudflare you can then turn the orange cloud on,
   SSL mode **Full (strict)**.
3. In the Paystack dashboard (Settings → API keys & webhooks) set
   - Webhook URL: `https://beautyflow.co.ke/webhooks/paystack/`
   - Callback URL can stay empty — the app sends its own (`/dashboard/pay/done/`).
4. Remove `173.249.23.183` from `ALLOWED_HOSTS` in `.env` if you don't want the bare IP to serve the site,
   then `systemctl restart beautyflow`.

Until HTTPS is on, logging in over `http://173.249.23.183/` won't stick: the session cookie is
HTTPS-only in production. Public pages work.

## Deploying an update

From your machine, in the project folder:

```bash
export SSHPASS='<root password>'
./deploy.sh
```

That rsyncs the code (excluding `.env`, `media/`, `db.sqlite3`, `.venv`, `.git`), installs requirements,
runs `migrate` + `collectstatic`, **gracefully reloads** gunicorn (no downtime) and hits the site.
Use `systemctl restart beautyflow` after editing `.env` (a reload does not re-read it).

Manual equivalent on the server:

```bash
cd /home/beautyflow/app
sudo -u beautyflow -H /home/beautyflow/venv/bin/pip install -r requirements.txt
sudo -u beautyflow -H /home/beautyflow/venv/bin/python manage.py migrate
sudo -u beautyflow -H /home/beautyflow/venv/bin/python manage.py collectstatic --noinput
systemctl reload beautyflow
```

## Environment file (`/home/beautyflow/app/.env`)

```
SECRET_KEY=…                       # long random string (generated on setup)
DEBUG=0
ALLOWED_HOSTS=beautyflow.co.ke,www.beautyflow.co.ke,173.249.23.183
SITE_URL=https://beautyflow.co.ke
DB_NAME=beautyflow  DB_USER=beautyflow  DB_PASSWORD=…  DB_HOST=127.0.0.1  DB_PORT=5432
EMAIL_BACKEND=smtp
EMAIL_HOST=mail.isoftke.com        # tested from this server 23 Sep 2026, port 465 SSL
EMAIL_PORT=465
EMAIL_USE_SSL=1
EMAIL_HOST_USER=beauty@isoftke.com
EMAIL_HOST_PASSWORD=…
DEFAULT_FROM_EMAIL=BeautyFlow <beauty@isoftke.com>
PAYSTACK_PUBLIC_KEY=pk_live_…
PAYSTACK_SECRET_KEY=sk_live_…
ADMINS=Ian:ianenoch11@gmail.com   # gets an email on server errors
# optional: TURNSTILE_SITE_KEY / TURNSTILE_SECRET_KEY (bot check on public forms),
#           ADVANTA_* (SMS), OTP_EMAIL_* (separate mailbox for login codes)
```

One variable per line. The mail password contains `{)` — that's fine for Django and systemd, but
don't `source` the file in bash.

## Scheduled jobs (systemd timers)

| Timer | Runs | What |
|---|---|---|
| `beautyflow-reconcile.timer` | every 5 min | `manage.py reconcile_payments` — asks Paystack about unfinished checkouts from the last 24 h |
| `beautyflow-reminders.timer` | daily 09:00 | `manage.py send_expiry_reminders` — plan expiry emails (7 days, 1 day, on the day) |
| `beautyflow-backup.timer` | daily 02:30 (±5 min) | `/usr/local/bin/beautyflow-backup.sh` |
| `certbot.timer` | twice a day | certificate renewal (after "Going live") |

Both manage.py jobs use the template unit `beautyflow-manage@.service`, so any command can be run the same way:

```bash
systemctl start beautyflow-manage@reconcile_payments.service
journalctl -u 'beautyflow-manage@*' -n 20
systemctl list-timers 'beautyflow*'
```

## Backups

`/usr/local/bin/beautyflow-backup.sh` writes to `/var/backups/beautyflow/` (root only, mode 600):

| File | What |
|---|---|
| `db-YYYY-MM-DD_HHMM.dump` | PostgreSQL dump of `beautyflow` (custom format) |
| `media-….tar.gz` | uploaded logos, covers, service and staff photos |
| `env-…` | the `.env` file |
| `globals-….sql` | Postgres roles and passwords |

**Files older than 30 days are deleted automatically.** After that a deletion is permanent.
The backups are **on the same server only** — copy them off the server (another machine, R2/S3 with
rclone crypt) if the server itself might be lost. That is not set up yet.

```bash
systemctl start beautyflow-backup.service      # run one now
journalctl -u beautyflow-backup -n 20          # each line says ok / FAIL
ls -la /var/backups/beautyflow/
```

**Restore the database:**

```bash
sudo -u postgres createdb -O beautyflow beautyflow_restore
cat /var/backups/beautyflow/db-2026-09-23_1541.dump | sudo -u postgres pg_restore --no-owner --role=beautyflow -d beautyflow_restore
# check it, then swap:
systemctl stop beautyflow
sudo -u postgres psql -c 'ALTER DATABASE beautyflow RENAME TO beautyflow_broken'
sudo -u postgres psql -c 'ALTER DATABASE beautyflow_restore RENAME TO beautyflow'
systemctl start beautyflow
```

**Restore media:** `tar -xzf /var/backups/beautyflow/media-….tar.gz -C /home/beautyflow/app && chown -R beautyflow:beautyflow /home/beautyflow/app/media`

## Common operations

```bash
systemctl status beautyflow            # is it up?
systemctl restart beautyflow           # after editing .env
journalctl -u beautyflow -n 100        # recent app logs
nginx -t && systemctl reload nginx     # after editing the nginx site

# Django shell as the app user
cd /home/beautyflow/app && sudo -u beautyflow /home/beautyflow/venv/bin/python manage.py shell

# Create another admin
cd /home/beautyflow/app && sudo -u beautyflow /home/beautyflow/venv/bin/python manage.py shell -c "
from accounts.models import User
User.objects.create_superuser(username='x@y.com', email='x@y.com', password='…', first_name='Name', email_verified=True)"

# Test outgoing email
cd /home/beautyflow/app && sudo -u beautyflow /home/beautyflow/venv/bin/python manage.py shell -c "
from django.core.mail import send_mail; print(send_mail('test', 'hello', None, ['you@example.com']))"
```

## Rebuilding a server from scratch

1. `apt install postgresql nginx python3-venv python3-dev build-essential libpq-dev certbot python3-certbot-nginx ufw fail2ban rsync`
   and `timedatectl set-timezone Africa/Nairobi`
2. `adduser --system --group --home /home/beautyflow --shell /bin/bash beautyflow`
3. `sudo -u postgres psql -c "create role beautyflow login password '…'"` and `sudo -u postgres createdb -O beautyflow beautyflow`
4. rsync the code to `/home/beautyflow/app` (or run `./deploy.sh` once the venv exists), write `.env`,
   `python3 -m venv /home/beautyflow/venv`, `pip install -r requirements.txt`,
   `migrate`, `createcachetable`, `collectstatic`, `mkdir media`, `chown -R beautyflow:beautyflow /home/beautyflow`
5. Install the units and nginx site below, `systemctl daemon-reload`,
   `systemctl enable --now beautyflow beautyflow-backup.timer beautyflow-reconcile.timer beautyflow-reminders.timer`
6. `ufw allow OpenSSH && ufw allow 'Nginx Full' && ufw enable`; fail2ban `[sshd] enabled = true` in `/etc/fail2ban/jail.local`
7. Restore the latest backup if moving servers, then "Going live".

### `/etc/systemd/system/beautyflow.service`
```ini
[Unit]
Description=BeautyFlow (Django/gunicorn)
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=beautyflow
Group=beautyflow
WorkingDirectory=/home/beautyflow/app
EnvironmentFile=/home/beautyflow/app/.env
ExecStart=/home/beautyflow/venv/bin/gunicorn beautyflow.wsgi:application --bind 127.0.0.1:8020 --workers 3 --timeout 60 --access-logfile - --error-logfile -
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/beautyflow/app/media
StandardOutput=journal
StandardError=journal
SyslogIdentifier=beautyflow

[Install]
WantedBy=multi-user.target
```

### `/etc/systemd/system/beautyflow-manage@.service`
```ini
[Unit]
Description=BeautyFlow manage.py %i
After=postgresql.service

[Service]
Type=oneshot
User=beautyflow
WorkingDirectory=/home/beautyflow/app
EnvironmentFile=/home/beautyflow/app/.env
ExecStart=/home/beautyflow/venv/bin/python manage.py %i
```
Timers: `beautyflow-reconcile.timer` (`OnCalendar=*:0/5`), `beautyflow-reminders.timer`
(`OnCalendar=*-*-* 09:00:00`), each with `Unit=beautyflow-manage@<command>.service`;
`beautyflow-backup.timer` (`OnCalendar=*-*-* 02:30:00`) → `beautyflow-backup.service` → the backup script.

### nginx site (before certbot)
Port 80, `server_name beautyflow.co.ke www.beautyflow.co.ke 173.249.23.183`, `client_max_body_size 8M`:
`/.well-known/acme-challenge/` from `/var/www/certbot`; `/static/` and `/media/` served from
`/home/beautyflow/app/…`; everything else `proxy_pass http://127.0.0.1:8020` with `Host`,
`X-Forwarded-For` and `X-Forwarded-Proto` set (Django uses the last for HTTPS-only cookies and redirects).
`certbot --nginx` then adds the 443 block and the redirect.
