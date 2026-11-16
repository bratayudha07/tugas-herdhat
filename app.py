"""Entrypoint ASGI untuk platform hosting (Vercel, dsb).

Vercel mencari instance `FastAPI` bernama `app` di file root bernama
`app.py`, `index.py`, `main.py`, `server.py`, `wsgi.py`, atau `asgi.py`.
Aplikasi sebenarnya tetap di `web/main.py` — file ini cuma jembatan tipis
supaya tidak ada logika yang diduplikasi.

Lokal tidak berubah: `.venv/bin/python -m uvicorn web.main:app --port 8000`.
"""

from web.main import app

__all__ = ["app"]
