# BeautyFlow — Deployment

Live at **https://beautyflow.co.ke** (Cloudflare → VPS 164.68.114.113).

## Server layout

| Item | Value |
|---|---|
| OS | Ubuntu 24.04, Python 3.12, nginx, PostgreSQL 16 |
| System user | `beautyflow` (no login shell needed; owns everything below) |
| Code | `/home/beautyflow/app` |
| Virtualenv | `/home/beautyflow/venv` |
| Env / secrets | `/home/beautyflow/app/.env` (never in git) |
| Uploads (media) | `/home/beautyflow/app/media` — served by nginx at `/media/` |
| Static files | `/home/beautyflow/app/staticfiles` — served by nginx at `/static/` |
| App server | gunicorn, 3 workers, `127.0.0.1:8020` — `systemd` unit `beautyflow.service` |
| Reverse proxy | `/etc/nginx/sites-available/beautyflow` (symlinked into `sites-enabled`) |
| TLS | Let's Encrypt, `/etc/letsencrypt/live/beautyflow.co.ke/`, auto-renews via `certbot.timer` |
| Database | PostgreSQL db `beautyflow`, role `beautyflow` (password in `.env`) |
| Logs | `journalctl -u beautyflow -f` · `/var/log/nginx/beautyflow.{access,error}.log` |

The server also hosts **afritherapy**, **buytickets** and **wananchimart** (their own users,
DBs, services and nginx sites). BeautyFlow shares only nginx and the PostgreSQL server with them
— its own DB/role, service, port and directories. Do not edit their files.

## First admin

`ianenoch11@gmail.com` (superuser, email pre-verified). Log in at https://beautyflow.co.ke/login/ —
a 6-digit code is emailed, then you land on https://beautyflow.co.ke/admin/.

## Deploying an update

From your machine, in the project folder:

```bash
export SSHPASS='<root password>'
./deploy.sh
```

That rsyncs the code (excluding `.env`, `media/`, `db.sqlite3`, `.venv`), installs
requirements, runs `migrate` + `collectstatic`, **gracefully reloads** gunicorn (zero downtime) and hits the site.
Use `systemctl restart beautyflow` only after editing `.env` (a reload does not re-read it).

Manual equivalent on the server:

```bash
cd /home/beautyflow/app
sudo -u beautyflow -H /home/beautyflow/venv/bin/pip install -r requirements.txt
sudo -u beautyflow -H /home/beautyflow/venv/bin/python manage.py migrate
sudo -u beautyflow -H /home/beautyflow/venv/bin/python manage.py collectstatic --noinput
systemctl restart beautyflow
```

## Environment file (`/home/beautyflow/app/.env`)

```
SECRET_KEY=…              # long random string
DEBUG=0
ALLOWED_HOSTS=beautyflow.co.ke,www.beautyflow.co.ke,164.68.114.113
SITE_URL=https://beautyflow.co.ke

DB_NAME=beautyflow  DB_USER=beautyflow  DB_PASSWORD=…  DB_HOST=127.0.0.1  DB_PORT=5432

EMAIL_BACKEND=smtp
EMAIL_HOST=isoftke.co.ke      # NOT mail.isoftke.co.ke — that host doesn't answer on mail ports
EMAIL_PORT=465
EMAIL_USE_SSL=1
EMAIL_HOST_USER=beauty@isoftke.com
EMAIL_HOST_PASSWORD=…
DEFAULT_FROM_EMAIL=BeautyFlow <beauty@isoftke.com>
```

If `DB_NAME` is unset the app falls back to SQLite (local development).
Locally, `EMAIL_BACKEND=console` prints the codes in the `runserver` terminal.

## Common operations

```bash
systemctl status beautyflow            # is it up?
systemctl restart beautyflow           # restart after editing .env
journalctl -u beautyflow -n 100        # recent app logs
nginx -t && systemctl reload nginx  # after editing the nginx site

# Django shell / management as the app user
sudo -u beautyflow -H /home/beautyflow/venv/bin/python /home/beautyflow/app/manage.py shell

# Create another admin
sudo -u beautyflow -H /home/beautyflow/venv/bin/python /home/beautyflow/app/manage.py shell -c "
from accounts.models import User
u=User.objects.create_superuser(username='x@y.com', email='x@y.com', password='…', first_name='Name', email_verified=True); print(u)"

# Database backup / restore
sudo -u postgres pg_dump beautyflow | gzip > /root/beautyflow-$(date +%F).sql.gz
gunzip -c /root/beautyflow-YYYY-MM-DD.sql.gz | sudo -u postgres psql beautyflow

# Media backup
tar czf /root/beautyflow-media-$(date +%F).tgz -C /home/beautyflow/app media
```

## DNS / Cloudflare

- `beautyflow.co.ke` → A record to `164.68.114.113`, proxied (orange cloud). Works.
- `www.beautyflow.co.ke` currently has **no DNS record**. Add a CNAME `www → beautyflow.co.ke`
  (proxied) in Cloudflare, then extend the certificate:
  `certbot certonly --webroot -w /var/www/certbot -d beautyflow.co.ke -d www.beautyflow.co.ke --expand`
  and `systemctl reload nginx`. Nginx already redirects `www` → apex.
- Cloudflare SSL mode should be **Full (strict)** — the origin has a valid Let's Encrypt cert.

## Fresh server (if ever rebuilding)

1. `adduser --system --group --home /home/beautyflow --shell /bin/bash beautyflow`
2. `sudo -u postgres psql -c "create role beautyflow login password '…'"` and
   `sudo -u postgres createdb -O beautyflow beautyflow`
3. rsync code to `/home/beautyflow/app`, write `.env`, `python3 -m venv /home/beautyflow/venv`,
   `pip install -r requirements.txt`, `migrate`, `collectstatic`, `mkdir media`
4. Copy the `beautyflow.service` unit (see below) to `/etc/systemd/system/`, `systemctl enable --now beautyflow`
5. Copy the nginx site, `ln -s` into `sites-enabled`, `nginx -t`, `systemctl reload nginx`
6. `certbot certonly --webroot -w /var/www/certbot -d beautyflow.co.ke`

### `beautyflow.service`
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

### nginx site (summary)
Port 80: ACME challenge from `/var/www/certbot`, everything else 301 → https.
Port 443: Let's Encrypt cert, `www` → apex redirect, `/static/` and `/media/` served from
`/home/beautyflow/app/…`, everything else `proxy_pass http://127.0.0.1:8020` with
`X-Forwarded-Proto` set (Django uses it for HTTPS-only cookies and redirects).

## Backups (nightly, automatic)

`beautyflow-backup.timer` runs `/usr/local/bin/beautyflow-backup.sh` every night at **02:30 server time** (±5 min). It covers **every product on the VPS**, not just BeautyFlow:

| Product | What |
|---|---|
| BeautyFlow | Postgres dump + `media/` (logos, covers, food photos) + `.env` |
| Afritherapy | Postgres dump + `media/` + `.env` |
| Buytickets | Postgres dump + `.env` |
| Wananchimart | Postgres dump taken inside the Docker container + `.env` |
| MySQL | all databases |
| Postgres | roles and passwords (`globals`) so logins restore too |

**Where and for how long**

- **On the server:** `/var/backups/<product>/`, root-only (mode 600). Files are named with date **and time** (`db-2026-09-17_0231.dump`) so two runs on the same day never overwrite each other.
  **Anything older than 30 days is deleted automatically** by the script (`KEEP=30`). At ~120 MB a night that is ~3.6 GB — it cannot fill the disk.
- **Off-site:** the same files are copied to Cloudflare R2, bucket `afritherapy-media`, folder `backups/`, **encrypted** (rclone crypt — file contents *and* names). Copies older than 30 days are deleted there too. Cloudflare can't read them; neither can anyone with the bucket key alone.
- **The decryption key** lives in `/root/.config/rclone/rclone.conf` with a copy at `/root/rclone-offsite-KEY-KEEP-SAFE.conf`. **Keep a copy of that file off the server** (password manager / USB). Without it the R2 copies are useless.

```bash
systemctl list-timers beautyflow-backup.timer     # when it next runs
systemctl start beautyflow-backup.service         # run one now
journalctl -u beautyflow-backup -n 30             # what happened (each line says ok / FAIL per product)
rclone lsf offsite:beautyflow/                    # what is in R2 (decrypted names)
```

**Restore a database** (dumps are root-only, so pipe them in):

```bash
# from the server copy
sudo -u postgres createdb beautyflow_restore
cat /var/backups/beautyflow/db-2026-09-17_0231.dump | sudo -u postgres pg_restore --no-owner --no-acl -d beautyflow_restore
# or first pull it back from R2
rclone copy offsite:beautyflow/db-2026-09-17_0231.dump /tmp/
# check it, then swap:
systemctl stop beautyflow
sudo -u postgres psql -c 'ALTER DATABASE beautyflow RENAME TO beautyflow_broken'
sudo -u postgres psql -c 'ALTER DATABASE beautyflow_restore RENAME TO beautyflow'
systemctl start beautyflow
```

**Restore media:** `tar -xzf /var/backups/beautyflow/media-2026-09-17_0231.tar.gz -C /home/beautyflow/app && chown -R beautyflow:beautyflow /home/beautyflow/app/media`

The same pattern works for afritherapy / buytickets (host Postgres) and MySQL (`gunzip -c all-….sql.gz | mysql`). Wananchimart: `gunzip -c db-….sql.gz | docker exec -i wananchimart-db-1 psql -U wananchimart -d wananchimart`.

Verified 17 Sep 2026: a dump pulled back from R2 restored into a scratch database with the right row counts, then the scratch database was dropped.

**A deletion is permanent after 30 days.** Backups protect against mistakes for 30 days only. Example: Dollarz Gentlemen's Club was deleted from the admin panel on 17 Sep 2026 06:37; the last backup containing it was overwritten the same morning (before filenames carried the time), so it is not recoverable from backups. Anything you might want back later than 30 days must be exported before then.
