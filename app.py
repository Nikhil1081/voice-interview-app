"""WSGI entrypoint shim.

Some hosts (and default Render templates) start Gunicorn with `app:app`.
This project’s Flask app lives in `main.py`, so we re-export it here.
"""

from main import app  # noqa: F401
