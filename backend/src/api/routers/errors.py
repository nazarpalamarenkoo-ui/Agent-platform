from fastapi import HTTPException

from src.catalog.hint.exceptions import HintClientError, HintError, HintParseError, HintValidationError
from src.services.errors import ConflictError, ForbiddenError, NotFoundError


def to_http(error: ValueError) -> HTTPException:
    if isinstance(error, NotFoundError):
        code = 404
    elif isinstance(error, ForbiddenError):
        code = 403
    elif isinstance(error, ConflictError):
        code = 409
    else:
        code = 400
    return HTTPException(status_code=code, detail=str(error))


def hint_to_http(error: HintError) -> HTTPException:
    if isinstance(error, HintClientError):
        return HTTPException(
            status_code=503,
            detail="Suggestion service is temporarily unavailable, try again later",
        )
    if isinstance(error, (HintValidationError, HintParseError)):
        return HTTPException(
            status_code=502,
            detail="Could not build a valid suggestion, try rephrasing your request",
        )
    return HTTPException(status_code=500, detail="Suggestion failed")


def too_many_requests(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail="Too many requests, try again later",
        headers={"Retry-After": str(retry_after)},
    )