import os

from django.core.wsgi import get_wsgi_application

# Fail-closed: ver a justificativa em `manage.py`.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_wsgi_application()
