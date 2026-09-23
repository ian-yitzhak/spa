from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.environ.get("DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,beautyflow.co.ke,www.beautyflow.co.ke").split(",")
CSRF_TRUSTED_ORIGINS = ["https://beautyflow.co.ke", "https://www.beautyflow.co.ke"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    "django_htmx",
    "django_ckeditor_5",
    "accounts",
    "vendors",
    "adminpanel",
    "payments",
    "pos",
    "affiliates",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "beautyflow.security_middleware.SecurityHeadersMiddleware",
]

# Passwords: Argon2id first (new hashes), PBKDF2 kept to verify existing ones (auto-upgraded on next login)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o644
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o755  # nginx (www-data) serves /media/ and must be able to enter every folder
ADMINS = [(n, e) for n, e in [a.split(":") for a in os.environ.get("ADMINS", "").split(",") if ":" in a]]
LOGIN_LOCKOUT_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15

ROOT_URLCONF = "beautyflow.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "vendors.context_processors.site_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "beautyflow.wsgi.application"

# Localhost: SQLite. Production: set DB_NAME/DB_USER/DB_PASSWORD in .env to use PostgreSQL.
if os.environ.get("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ.get("DB_USER", ""),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
if not DEBUG:
    # Hashed filenames (app.abc123.css) so browsers/Cloudflare never serve stale CSS/JS after a deploy
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
    }
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CKEditor 5
CKEDITOR_5_FILE_UPLOAD_PERMISSION = "authenticated"
CKEDITOR_5_CONFIGS = {
    "default": {
        "toolbar": ["heading", "|", "bold", "italic", "link", "bulletedList", "numberedList", "|", "undo", "redo"],
        "heading": {
            "options": [
                {"model": "paragraph", "title": "Paragraph", "class": "ck-heading_paragraph"},
                {"model": "heading3", "view": "h3", "title": "Heading", "class": "ck-heading_heading3"},
            ]
        },
    },
}

SITE_NAME = "BeautyFlow"
SITE_URL = os.environ.get("SITE_URL", "https://beautyflow.co.ke")

# Sessions: stay logged in for 60 days unless the user logs out
SESSION_COOKIE_AGE = 60 * 24 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True  # sliding window: 60 days from last visit

# Email (OTP + verification). EMAIL_BACKEND=console prints mails to the terminal.
_backend = os.environ.get("EMAIL_BACKEND", "smtp")
EMAIL_BACKEND = ("django.core.mail.backends.console.EmailBackend" if _backend == "console"
                 else "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "465"))
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "1") == "1"
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "0") == "1"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "noreply@beautyflow.co.ke")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Behind nginx + HTTPS in production
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_HSTS_PRELOAD = True
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"console": {"class": "logging.StreamHandler"},
                     "mail_admins": {"class": "django.utils.log.AdminEmailHandler", "level": "ERROR"}},
        "root": {"handlers": ["console"], "level": "INFO"},
        "loggers": {"django.request": {"handlers": ["mail_admins"], "level": "ERROR", "propagate": True},
                    # A wrong Host header is a scan or a local test, never a real user fault — log it, don't email.
                    "django.security.DisallowedHost": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
    }

# Paystack (card + M-Pesa checkout for plans). Webhook: POST /webhooks/paystack/, signed with the secret key.
PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY", "")
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")

# Cloudflare Turnstile (bot check on public forms). Blank secret = check skipped (local dev).
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "")
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")

# Shared cache for rate limiting across gunicorn workers
CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "beautyflow_cache"}}

# Second mailbox for one-time codes (login, verification, password reset, review confirmation).
# Falls back to the main mailbox when not configured.
OTP_EMAIL_HOST_USER = os.environ.get("OTP_EMAIL_HOST_USER", "")
OTP_EMAIL_HOST_PASSWORD = os.environ.get("OTP_EMAIL_HOST_PASSWORD", "")
OTP_EMAIL_HOST = os.environ.get("OTP_EMAIL_HOST", EMAIL_HOST)
OTP_FROM_EMAIL = os.environ.get("OTP_FROM_EMAIL", f"BeautyFlow <{OTP_EMAIL_HOST_USER}>" if OTP_EMAIL_HOST_USER else DEFAULT_FROM_EMAIL)

# Advanta / QuickSMS (welcome + order-ready + reservation texts). Blank = dry-run.
ADVANTA_API_KEY = os.environ.get("ADVANTA_API_KEY", "")
ADVANTA_PARTNER_ID = os.environ.get("ADVANTA_PARTNER_ID", "")
ADVANTA_SHORTCODE = os.environ.get("ADVANTA_SHORTCODE", "")

# POS Insights (computed from the vendor's own data)
INSIGHTS_REGEN_PER_DAY = 10
INSIGHTS_ASK_PER_DAY = 25

OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
