import logging

from fastapi.responses import JSONResponse

from exception.domain import (
    AlreadyExistsError,
    AlreadyProcessedError,
    DomainException,
    EntityNotFoundError,
    ImplementationNotFoundError,
    InvalidOperationError,
    InvalidTransitionError,
)
from exception.infrastructure import (
    DatabaseException,
    ExternalServiceException,
    ProviderError,
    ProviderTimeoutError,
)

logger = logging.getLogger(__name__)

DOMAIN_STATUS_MAP = {
    EntityNotFoundError: 404,
    AlreadyExistsError: 409,
    AlreadyProcessedError: 409,
    InvalidOperationError: 422,
    InvalidTransitionError: 422,
    ImplementationNotFoundError: 400,
}

INFRA_STATUS_MAP = {
    ProviderTimeoutError: 504,
    ProviderError: 502,
}


async def domain_handler(request, exc: DomainException):
    status = DOMAIN_STATUS_MAP.get(type(exc), 400)
    return JSONResponse(
        status_code=status,
        content={"error": exc.message},
    )


async def database_handler(request, exc: DatabaseException):
    logger.error(f"Database error: {exc.message}")
    return JSONResponse(
        status_code=503,
        content={"error": "Service temporarily unavailable"},
    )


async def external_handler(request, exc: ExternalServiceException):
    status = INFRA_STATUS_MAP.get(type(exc), 502)
    logger.error(f"External service error: {exc.message}")
    return JSONResponse(
        status_code=status,
        content={"error": exc.message},
    )


async def catch_all_handler(request, exc: Exception):
    logger.critical(f"Unhandled: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )
