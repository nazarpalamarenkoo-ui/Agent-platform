from unittest.mock import AsyncMock

import pytest

from src.api.routers import catalog, rate_limit
from src.api.routers.errors import too_many_requests
from src.catalog.hint.catalog_hint_service import CatalogHintService
from src.catalog.hint.exceptions import (
    HintClientError,
    HintError,
    HintParseError,
    HintValidationError,
)
from src.dependencies import get_arq_pool, get_catalog_hint_service
from src.schemas.catalog import HintResponse
from src.services.errors import ConflictError, ForbiddenError, NotFoundError

pytestmark = pytest.mark.unit

ROUTER = catalog.router
SERVICE_DEPENDENCY = get_catalog_hint_service
SERVICE_SPEC = CatalogHintService

PAYLOAD = {"intent": "I need a tool for parsing pdf files"}


@pytest.fixture(autouse=True)
def rate_limit_check(monkeypatch, override):
    override(get_arq_pool, object())
    mock = AsyncMock()
    monkeypatch.setattr(rate_limit, "check_rate_limit", mock)
    return mock


async def test_propose_returns_hint(client, service, actor, fake):
    service.propose.return_value = fake(HintResponse)

    response = await client.post("/catalog/hint", json=PAYLOAD)

    assert response.status_code == 200
    service.propose.assert_awaited_once_with(viewer_id=actor.id, intent=PAYLOAD["intent"])


async def test_rate_limit_is_checked_per_user(client, service, actor, fake, rate_limit_check):
    service.propose.return_value = fake(HintResponse)

    await client.post("/catalog/hint", json=PAYLOAD)

    rate_limit_check.assert_awaited_once()
    assert rate_limit_check.await_args.args[1] == f"ratelimit:hint:{actor.id}"


async def test_rate_limit_exceeded_returns_429_and_skips_service(
    client, service, rate_limit_check
):
    rate_limit_check.side_effect = too_many_requests(retry_after=30)

    response = await client.post("/catalog/hint", json=PAYLOAD)

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    service.propose.assert_not_awaited()


@pytest.mark.parametrize(
    "error,code",
    [
        (HintClientError("secret upstream detail"), 503),
        (HintValidationError("secret upstream detail"), 502),
        (HintParseError("secret upstream detail"), 502),
        (HintError("secret upstream detail"), 500),
    ],
)
async def test_hint_errors_are_mapped_and_details_hidden(client, service, error, code):
    service.propose.side_effect = error

    response = await client.post("/catalog/hint", json=PAYLOAD)

    assert response.status_code == code
    assert "secret" not in response.json()["detail"]


@pytest.mark.parametrize(
    "error,code",
    [
        (ValueError("bad"), 400),
        (NotFoundError("bad"), 404),
        (ForbiddenError("bad"), 403),
        (ConflictError("bad"), 409),
    ],
)
async def test_value_errors_are_mapped(client, service, error, code):
    service.propose.side_effect = error

    response = await client.post("/catalog/hint", json=PAYLOAD)

    assert response.status_code == code
    assert response.json()["detail"] == "bad"


@pytest.mark.parametrize("payload", [{}, {"intent": ["x"]}, {"intent": None}])
async def test_rejects_invalid_payload(client, service, payload):
    response = await client.post("/catalog/hint", json=payload)

    assert response.status_code == 422
    service.propose.assert_not_awaited()