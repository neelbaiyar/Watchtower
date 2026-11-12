"""Tests for Watchtower's local static dashboard delivery."""

from fastapi.testclient import TestClient

from watchtower.api.app import create_app


class FakeDashboardService:
    """Static-asset tests do not invoke a snapshot operation."""


def test_dashboard_and_static_assets_are_served() -> None:
    """The product landing page is separate from the developer documentation."""

    with TestClient(create_app(snapshot_service=FakeDashboardService())) as client:
        dashboard = client.get("/")
        styles = client.get("/assets/styles.css")
        script = client.get("/assets/app.js")

    assert dashboard.status_code == 200
    assert "Watchtower | Research Priority" in dashboard.text
    assert "/assets/styles.css" in dashboard.text
    assert "/assets/app.js" in dashboard.text
    assert 'id="snapshot-status"' in dashboard.text
    assert styles.status_code == 200
    assert "--accent" in styles.text
    assert "[hidden]" in styles.text
    assert script.status_code == 200
    assert "WATCHLIST_KEY" in script.text
    assert "SELECTED_TICKER_KEY" in script.text
    assert "snapshot.snapshot_status" in script.text
