from shared.domain.exception.base import AppException


class DatabaseException(AppException):
    def __init__(self, message="Service temporarily unavailable"):
        super().__init__(message)


class ExternalServiceException(AppException):
    def __init__(self, message="External service unavailable"):
        super().__init__(message)


class ProviderError(ExternalServiceException):
    def __init__(self, message="Provider unavailable"):
        super().__init__(message)


class ProviderTimeoutError(ExternalServiceException):
    def __init__(self, message="Provider timeout"):
        super().__init__(message)
