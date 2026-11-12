"""FastAPI application factory and provider lifecycle ownership."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from watchtower.api.routes import router
from watchtower.clients.marketaux import (
    MarketauxClient,
    NewsAuthenticationError,
    NewsClientError,
    NewsRateLimitError,
)
from watchtower.clients.sec_edgar import (
    SecEdgarClient,
    SecEdgarError,
    SecTickerNotFoundError,
)
from watchtower.clients.yfinance import PriceClientError, YFinanceClient
from watchtower.config import Settings
from watchtower.services import CompanySnapshotService
from watchtower.signals import TransparentResearchSignalEngine


def create_app(
    *,
    settings: Settings | None = None,
    snapshot_service: CompanySnapshotService | None = None,
) -> FastAPI:
    """Create a Watchtower application with production or injected dependencies."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # A supplied service is a test seam: tests avoid real SEC, price, and
        # news providers while exercising the same HTTP routes.
        if snapshot_service is not None:
            app.state.snapshot_service = snapshot_service
            yield
            return

        # Production creates provider clients once at startup, not once per
        # request. The context managers close their HTTP connections on exit.
        active_settings = settings or Settings.from_environment()
        with (
            SecEdgarClient(user_agent=active_settings.sec_user_agent) as sec_client,
            MarketauxClient(
                api_token=active_settings.marketaux_api_token
            ) as news_client,
        ):
            # app.state is FastAPI's process-local place for dependencies that
            # routes retrieve later through Depends.
            app.state.snapshot_service = CompanySnapshotService(
                sec_client=sec_client,
                price_client=YFinanceClient(),
                news_client=news_client,
                signal_engine=TransparentResearchSignalEngine(),
            )
            yield

    app = FastAPI(
        title="Watchtower API",
        summary="Source-grounded company research snapshots",
        description=(
            "Research a ticker through normalized SEC filings, daily market-price "
            "data, and current headline metadata. Watchtower distinguishes source "
            "events from retrieval time and does not provide investment advice."
        ),
        version="0.1.0",
        lifespan=lifespan,
        openapi_tags=[
            {
                "name": "Company snapshots",
                "description": (
                    "Retrieve one source-grounded research snapshot using a ticker "
                    "as input."
                ),
            }
        ],
        swagger_ui_parameters={"docExpansion": "full"},
    )
    # Route declarations and provider-error translation are registered after
    # the application object exists, keeping the factory easy to test.
    app.include_router(router)
    _register_exception_handlers(app)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    # Provider-specific exceptions never cross the public HTTP boundary. These
    # handlers turn them into stable API responses without leaking vendor data.
    async def ticker_not_found_handler(
        _: Request,
        __: SecTickerNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Ticker not found"},
        )

    async def news_unavailable_handler(
        _: Request,
        __: NewsAuthenticationError | NewsRateLimitError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "News provider temporarily unavailable"},
        )

    async def upstream_failure_handler(
        _: Request,
        __: SecEdgarError | PriceClientError | NewsClientError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "Upstream provider request failed"},
        )

    app.add_exception_handler(SecTickerNotFoundError, ticker_not_found_handler)
    app.add_exception_handler(NewsAuthenticationError, news_unavailable_handler)
    app.add_exception_handler(NewsRateLimitError, news_unavailable_handler)
    app.add_exception_handler(SecEdgarError, upstream_failure_handler)
    app.add_exception_handler(PriceClientError, upstream_failure_handler)
    app.add_exception_handler(NewsClientError, upstream_failure_handler)
