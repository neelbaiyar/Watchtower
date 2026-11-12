"""ASGI entry point for the Watchtower API."""

from watchtower.api.app import create_app

# Uvicorn imports this module and looks for this exact application object.
# Construction lives in create_app so tests can build an app with fake services.
app = create_app()
