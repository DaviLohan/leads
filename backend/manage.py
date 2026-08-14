#!/usr/bin/env python
import os
import sys


def main() -> None:
    # Fail-closed: sem a variável, cai em produção — que recusa subir sem SECRET_KEY e
    # ALLOWED_HOSTS. Cair em `development` abriria DEBUG=True e ALLOWED_HOSTS=["*"] por
    # esquecimento. O ambiente de dev define a variável em `.env` (ver `.env.example`).
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
