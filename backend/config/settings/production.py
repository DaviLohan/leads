"""Produção. `DEBUG` é False por construção — não há variável que ligue."""

from config.env import ConfigurationError, env, env_bool, env_int, env_list

from .base import *

DEBUG = False

_INSECURE_DEFAULT = "dev-only-insecure-key-change-me"
SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
if SECRET_KEY == _INSECURE_DEFAULT or len(SECRET_KEY) < 50:
    raise ConfigurationError(
        "DJANGO_SECRET_KEY de produção ausente, igual ao valor de desenvolvimento "
        "ou curta demais (mínimo 50 caracteres)."
    )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ConfigurationError("DJANGO_ALLOWED_HOSTS é obrigatória em produção.")

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
if "*" in CORS_ALLOWED_ORIGINS:
    raise ConfigurationError("CORS com '*' não é aceito em produção.")

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# --- HTTPS obrigatório -------------------------------------------------------

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 60 * 60 * 24 * 365)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# O TLS termina no reverse proxy; sem isto o Django acha que a requisição é http.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- Estáticos ---------------------------------------------------------------

STORAGES["staticfiles"] = {
    "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
}

# --- Sentry (opcional) -------------------------------------------------------

SENTRY_DSN = env("SENTRY_DSN")
if SENTRY_DSN:  # pragma: no cover - integração opcional
    import sentry_sdk

    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.1, send_default_pii=False)
