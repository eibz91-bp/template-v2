from functools import wraps

import httpx
from sqlalchemy.exc import SQLAlchemyError

from exception.base import AppException
from exception.infrastructure import (
    DatabaseException,
    ExternalServiceException,
    ProviderError,
    ProviderTimeoutError,
)


def handle_db_errors(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except AppException:
            raise
        except SQLAlchemyError as e:
            raise DatabaseException(str(e))
    return wrapper


def handle_external_errors(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except AppException:
            raise
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(str(e))
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"Status {e.response.status_code}")
        except httpx.HTTPError as e:
            raise ExternalServiceException(str(e))
    return wrapper
