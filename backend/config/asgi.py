import os

from django.core.asgi import get_asgi_application

# Fail-closed: ver a justificativa em `manage.py`.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_asgi_application()
