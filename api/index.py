"""Vercel entry point: every request is routed here (see vercel.json) and handled by the Flask
app in server.py, the same app `python server.py` runs locally."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app  # noqa: E402,F401  (Vercel serves the WSGI `app`)
