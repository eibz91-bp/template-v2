from exception.base import AppException


class DatabaseException(AppException):
    def __init__(self, message="Service temporarily unavailable"):
        super().__init__(message, 503)


class ExternalServiceException(AppException):
    def __init__(self, message="External service unavailable", status_code=502):
        super().__init__(message, status_code)


class ProviderError(ExternalServiceException):
    def __init__(self, message="Provider unavailable"):
        super().__init__(message, 502)


class ProviderTimeoutError(ExternalServiceException):
    def __init__(self, message="Provider timeout"):
        super().__init__(message, 504)
