"""Thin HTTP routes for Watchtower."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from watchtower.schemas import CompanySnapshotResponse
from watchtower.services import CompanySnapshotService

router = APIRouter(prefix="/companies", tags=["Company snapshots"])


def get_snapshot_service(request: Request) -> CompanySnapshotService:
    """Return the application-owned snapshot service for this process."""

    return request.app.state.snapshot_service


@router.get(
    "/{ticker}/snapshot",
    response_model=CompanySnapshotResponse,
    summary="Research a company by ticker",
    description=(
        "Enter a ticker such as `AAPL`, `NVDA`, or `HPE`. Watchtower returns "
        "recent SEC 8-K filings, a daily price snapshot, and ticker-associated "
        "headlines in one source-grounded response."
    ),
    response_description="Watchtower-owned company snapshot",
    responses={
        404: {"description": "The SEC ticker mapping does not contain the ticker"},
        502: {"description": "An upstream data provider request failed"},
        503: {"description": "The news provider is temporarily unavailable"},
    },
)
def get_company_snapshot(
    ticker: Annotated[
        str,
        Path(
            min_length=1,
            max_length=10,
            pattern=r"^[A-Za-z][A-Za-z0-9.-]*$",
            description="Exchange ticker symbol, such as AAPL or HPE",
        ),
    ],
    service: Annotated[CompanySnapshotService, Depends(get_snapshot_service)],
) -> CompanySnapshotResponse:
    """Compose current Watchtower data for one ticker."""

    return service.get_company_snapshot(ticker)
