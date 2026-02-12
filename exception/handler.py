import logging

from fastapi.responses import JSONResponse

from exception.domain import DomainException
from exception.infrastructure import DatabaseException, ExternalServiceException

logger = logging.getLogger(__name__)


async def domain_handler(request, exc: DomainException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message},
    )


async def database_handler(request, exc: DatabaseException):
    logger.error(f"Database error: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "Service temporarily unavailable"},
    )


async def external_handler(request, exc: ExternalServiceException):
    logger.error(f"External service error: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message},
    )


async def catch_all_handler(request, exc: Exception):
    logger.critical(f"Unhandled: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )
