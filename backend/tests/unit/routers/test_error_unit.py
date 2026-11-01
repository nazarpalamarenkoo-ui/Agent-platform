import pytest

from src.api.routers.errors import hint_to_http, to_http, too_many_requests
from src.catalog.hint.exceptions import (
    HintClientError,
    HintError,
    HintParseError,
    HintValidationError,
)
from src.services.errors import ConflictError, ForbiddenError, NotFoundError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "error,code",
    [
        (ValueError("bad"), 400),
        (NotFoundError("bad"), 404),
        (ConflictError("bad"), 409),
        (ForbiddenError("bad"), 403),
    ],
)
def test_to_http_maps_error_type_to_status(error, code):
    http = to_http(error)

    assert http.status_code == code
    assert http.detail == "bad"


@pytest.mark.parametrize(
    "error,code",
    [
        (HintClientError("secret upstream detail"), 503),
        (HintValidationError("secret upstream detail"), 502),
        (HintParseError("secret upstream detail"), 502),
        (HintError("secret upstream detail"), 500),
    ],
)
def test_hint_to_http_maps_status_and_hides_internal_details(error, code):
    http = hint_to_http(error)

    assert http.status_code == code
    assert "secret" not in http.detail


def test_too_many_requests_sets_retry_after_header():
    http = too_many_requests(retry_after=30)

    assert http.status_code == 429
    assert http.headers == {"Retry-After": "30"}