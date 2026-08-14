"""Settings de teste: rápidos, isolados e sem rede."""

from .base import *

DEBUG = False
ALLOWED_HOSTS = ["*", "testserver"]

# Hashing rápido: os testes não medem força de KDF.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Tasks rodam no processo do teste — sem broker.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# O star-import faz o mypy perder o tipo do dicionário de settings.
LOGGING["root"]["level"] = "WARNING"  # type: ignore[index]
