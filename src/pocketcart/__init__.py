"""PocketCart: a synthetic checkout service."""

from .service import PocketCartApi
from .wsgi import WsgiApp


def create_app() -> WsgiApp:
    """Build a WSGI application backed by a fresh in-memory store."""
    return WsgiApp(PocketCartApi())
