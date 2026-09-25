"""ASGI entry point for the Watchtower API."""

from watchtower.api.app import create_app

app = create_app()
