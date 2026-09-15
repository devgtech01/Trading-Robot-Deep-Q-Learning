"""
wsgi.py - Ponto de entrada para servidor WSGI (gunicorn) na VPS.

Uso:
    gunicorn --workers 1 --threads 8 --bind 127.0.0.1:8000 wsgi:app

ATENÇÃO ao número de workers: `create_app()` sobe a thread do agendador de
automação. Cada worker do gunicorn é um PROCESSO separado, com a sua própria
cópia do agendador — dois workers significam dois robôs lendo o mesmo catálogo
e disparando a mesma ordem em duplicidade. Este painel deve rodar sempre com
`--workers 1`; a concorrência necessária vem das threads, não dos processos.
"""

import src  # noqa: F401  (ajusta o encoding dos streams)

from webapp.server import create_app

app = create_app()
