"""Desenvolvimento local. Nunca use estes settings em produção."""

from config.env import env_bool

from .base import *

DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Sem HTTPS em dev: marcar o cookie como Secure impediria o login em http://localhost.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Schema navegável em dev.
SPECTACULAR_SETTINGS["SERVE_INCLUDE_SCHEMA"] = True

# O Swagger UI carrega assets de CDN. Só em dev — a CSP de produção segue estrita.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https:; frame-ancestors 'none'"
)
