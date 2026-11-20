"""Django settings.

Everything environment-specific comes from the gitignored .env at the repo root, which
scripts/init_env.sh writes. Secrets have no defaults here: a missing one must fail loudly.
"""

from datetime import timedelta
from pathlib import Path

import environ
from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
# read_env also exports values into os.environ, which is how the Hatchet SDK finds
# HATCHET_CLIENT_TOKEN / HATCHET_CLIENT_TLS_STRATEGY / HATCHET_CLIENT_HOST_PORT.
environ.Env.read_env(BASE_DIR.parent / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    # First, so `manage.py runserver` serves ASGI (HTTP and websockets) through Daphne.
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "channels",
    "oauth2_provider",
    # Platform apps: shared plumbing, no product features. Allowed imports between apps are
    # listed in apps/core/test_architecture.py.
    "apps.core",
    "apps.accounts",
    "apps.realms",
    "apps.jobs",
    "apps.users",
    # Domain apps go below, one per concern.
    "apps.integration_logs",
    "apps.integrations",
    "apps.feasibilities",
    "apps.api_clients",
    "apps.site_checks",
    "apps.pricebook",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"

# Websocket groups live in each API process's memory. Anything that must cross processes (the
# Hatchet worker telling the API something changed) goes over Postgres LISTEN/NOTIFY, not Redis.
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL")}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-za"
TIME_ZONE = "Africa/Johannesburg"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- API -------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    # InRealm resolves the request's company and refuses non-members (apps/realms/permissions.py).
    # An endpoint that works across companies, or before sign-in, sets its own permission
    # classes and is listed in apps/realms/test_isolation.py.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "apps.realms.permissions.InRealm",
    ],
    # "password": changing my own password (0002), which checks the current one.
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "invitation": "20/min",
        "password": "10/min",
        "oauth": "30/min",
    },
    "COERCE_DECIMAL_TO_STRING": False,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    # Tokens carry a hash of the password, so changing it signs out every other browser (0002).
    # Refresh checks it too (accounts.serializers); a future websocket must as well.
    "CHECK_REVOKE_TOKEN": True,
    "TOKEN_REFRESH_SERIALIZER": "apps.accounts.serializers.RevocableTokenRefreshSerializer",
}

# API clients (0006): OAuth2 client credentials only. Secrets are stored hashed; an access token
# lasts an hour and the client asks for a new one (no refresh tokens). What a token may do comes
# from its client's permission codes (apps/api_clients), not OAuth scopes.
OAUTH2_PROVIDER = {
    "ACCESS_TOKEN_EXPIRE_SECONDS": 3600,
    "SCOPES": {"api": "Use the Telejects API as this client"},
    "DEFAULT_SCOPES": ["api"],
    "PKCE_REQUIRED": True,
}
OAUTH2_PROVIDER_APPLICATION_MODEL = "oauth2_provider.Application"

# The Vite dev server proxies /api, so CORS only matters if you hit Django directly.
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:5184"])
CORS_ALLOW_HEADERS = (*default_headers, "x-realm")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# --- Integrations (0003) ---------------------------------------------------
# Fernet keys that encrypt connections' provider secrets, newest first (comma-separated). No
# default: without them a connection's credentials can't be stored or read.
INTEGRATIONS_ENCRYPTION_KEYS = env.list("INTEGRATIONS_ENCRYPTION_KEYS")
# Telejects' own provider accounts (0004), configured in .env only, never the database:
# their secrets and their settings, per connector key. A provider whose secrets are all set here
# is offered to every company, active from the start; companies can use their own account
# instead, whose credentials are stored in the database, encrypted with the keys above.
INTEGRATIONS_PLATFORM_ACCOUNTS = {
    "mtn": {
        "secrets": {"api_key": env("PLATFORM_MTN_API_KEY")},
        "settings": {
            "requestor_email": env("PLATFORM_MTN_REQUESTOR_EMAIL"),
            "customer_name": env("PLATFORM_MTN_CUSTOMER_NAME"),
        },
    },
    "vodacom": {
        "secrets": {"auth_key": env("PLATFORM_VODACOM_AUTH_KEY")},
        "settings": {"calling_system": env("PLATFORM_VODACOM_CALLING_SYSTEM")},
    },
    "herotel": {"secrets": {"api_key": env("PLATFORM_HEROTEL_API_KEY")}, "settings": {}},
    "link_africa": {
        "secrets": {"api_key": env("PLATFORM_LINK_AFRICA_KEY")},
        "settings": {
            "bandwidth_mbps": env("PLATFORM_LINK_AFRICA_BANDWIDTH_MBPS"),
            "term_months": env("PLATFORM_LINK_AFRICA_TERM_MONTHS"),
        },
    },
}
# How many provider requests a company keeps in its integration log (0005), unless platform
# staff set its own limit in Django admin.
INTEGRATION_LOGS_DEFAULT_LIMIT = env.int("INTEGRATION_LOGS_DEFAULT_LIMIT")
# Offer the Demo connector (a pretend provider). On for local development only. Where it's on,
# it is offered like one of Telejects' accounts (it needs no credentials).
INTEGRATIONS_DEMO_ENABLED = env.bool("INTEGRATIONS_DEMO_ENABLED", default=False)
if INTEGRATIONS_DEMO_ENABLED:
    INTEGRATIONS_PLATFORM_ACCOUNTS["demo"] = {"secrets": {}, "settings": {}}

# --- Email -----------------------------------------------------------------
# Without EMAIL_URL, mail is printed to the log of whichever process sends it (the Hatchet
# worker). e.g. EMAIL_URL=smtp+tls://user:password@host:587, set in .env only.
if env("EMAIL_URL", default=""):
    vars().update(env.email_url("EMAIL_URL"))
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Telejects <noreply@localhost>")
# Where the frontend lives; links in emails point here.
APP_URL = env("APP_URL", default="http://localhost:5184").rstrip("/")

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
