"""Settings comuns a todos os ambientes.

Cada ambiente importa este módulo e sobrescreve o necessário:
`development`, `test`, `production`.
"""

from __future__ import annotations

from pathlib import Path

import dj_database_url

from config.env import env, env_int, env_list

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# --- Núcleo ------------------------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    # terceiros
    "rest_framework",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # domínio (ver CLAUDE.md: um app nasce na etapa que o usa)
    "apps.core",
    "apps.accounts",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.OrganizationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
]

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
            ],
        },
    },
]

# --- Banco (ADR-0002) --------------------------------------------------------

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", "postgis://leads:leads@db:5432/leads"),
        conn_max_age=env_int("DB_CONN_MAX_AGE", 60),
        conn_health_checks=True,
    )
}

# --- Cache / Celery (ADR-0002: Redis nunca é fonte de verdade) ---------------

REDIS_URL = env("REDIS_URL", "redis://redis:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://redis:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "redis://redis:6379/2")
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 600
CELERY_TASK_SOFT_TIME_LIMIT = 540
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TIMEZONE = "UTC"

# --- Autenticação (ADR-0005) -------------------------------------------------

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_NAME = "leads_sessionid"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 12
CSRF_COOKIE_HTTPONLY = False  # o frontend precisa ler o token para enviá-lo no header
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:3000")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- CORS --------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
CORS_ALLOW_CREDENTIALS = True

# --- E-mail ------------------------------------------------------------------

# Base dos links enviados por e-mail (redefinição de senha, convites).
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:3000").rstrip("/")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "nao-responda@leads.local")

# --- API ---------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "password_reset": "5/hour",
        "search_create": "30/hour",
        "analysis": "60/hour",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Leads API",
    "DESCRIPTION": "Radar nacional de oportunidades digitais",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    # O default do drf-spectacular é AllowAny: sem isto, o schema e o Swagger entregam a
    # superfície inteira da API a qualquer anônimo em produção. Dev relaxa (development.py).
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
}

# --- Internacionalização -----------------------------------------------------

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "UTC"  # armazenamento em UTC; conversão só na apresentação
USE_I18N = True
USE_TZ = True
DISPLAY_TIME_ZONE = env("DISPLAY_TIME_ZONE", "America/Sao_Paulo")

# --- Estáticos ---------------------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# --- Segurança ---------------------------------------------------------------

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# 'unsafe-inline' em style-src é exigido pelo admin do Django; script-src continua estrito.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
)

# --- Logging (ver apps/core/logging.py) --------------------------------------

LOG_LEVEL = env("DJANGO_LOG_LEVEL", "INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.core.logging.RequestIDFilter"},
        "redact_secrets": {"()": "apps.core.logging.RedactSecretsFilter"},
    },
    "formatters": {
        "json": {"()": "apps.core.logging.JSONFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_id", "redact_secrets"],
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"], "propagate": False},
    },
}

# --- Providers externos (ADR-0003 / ADR-0004) --------------------------------

OVERPASS_API_URL = env("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")
OVERPASS_RATE_LIMIT_PER_SECOND = env_int("OVERPASS_RATE_LIMIT_PER_SECOND", 1)
OVERPASS_USER_AGENT = env("OVERPASS_USER_AGENT", "leads-radar/0.1")

# --- Análise de sites (limites do guard de SSRF, ver SECURITY.md) ------------

WEBSITE_SCAN_TIMEOUT_SECONDS = env_int("WEBSITE_SCAN_TIMEOUT_SECONDS", 10)
WEBSITE_SCAN_MAX_REDIRECTS = env_int("WEBSITE_SCAN_MAX_REDIRECTS", 3)
WEBSITE_SCAN_MAX_BYTES = env_int("WEBSITE_SCAN_MAX_BYTES", 2_000_000)
