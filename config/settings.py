"""
Django settings for the Data Structure Management Service.

Configuration is read from the environment with development-friendly defaults, so
`python manage.py runserver` works on a fresh checkout with no `.env` file. See
`.env.example` for the supported variables.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool) -> bool:
    """Read a boolean from the environment, accepting the usual truthy spellings."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str]) -> list[str]:
    """Read a comma-separated list from the environment."""
    raw = os.environ.get(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


# --------------------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------------------

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1", "0.0.0.0"])

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    # Local
    "catalog",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

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

# --------------------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / os.environ.get("DJANGO_SQLITE_PATH", "db.sqlite3"),
        "OPTIONS": {
            # The data model leans on database-level CHECK and UNIQUE constraints.
            # SQLite only enforces foreign keys when explicitly asked to, and the
            # default isolation behaviour is easier to reason about in WAL mode.
            "init_command": "PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL;",
        },
    }
}

# --------------------------------------------------------------------------------------
# Password validation, i18n, static files
# --------------------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Europe/Amsterdam")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --------------------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------------------

# Applied only outside development, so `runserver` stays usable over plain HTTP while a
# real deployment gets the hardening `manage.py check --deploy` asks for.
if not DEBUG:
    # Opt-out rather than opt-in: forgetting to enable HTTPS redirection should not be
    # possible by omission. docker-compose turns it off explicitly, because the review
    # environment is served over http://localhost.
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", 60 * 60 * 24 * 365))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Behind a load balancer that terminates TLS, this is how Django learns the original
    # request was HTTPS. Only safe when the proxy is trusted to set the header itself.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --------------------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------------------

REST_FRAMEWORK = {
    # Every error response in this service goes through one handler, so clients get a
    # single, predictable error envelope. See api/v2/core/exceptions.py.
    "EXCEPTION_HANDLER": "api.v2.core.exceptions.exception_handler",
    "DEFAULT_PAGINATION_CLASS": "api.v2.core.pagination.LimitOffsetPagination",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # This exercise ships without an authentication story; see the README trade-offs.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Data Structure Management Service",
    "DESCRIPTION": (
        "A metadata catalog: datasets (business entities such as Customer or Order) and "
        "the data elements (fields) that make them up."
    ),
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/v2",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
}
