from exception.base import AppException


class DomainException(AppException):
    def __init__(self, message, status_code=400):
        super().__init__(message, status_code)


class EntityNotFoundError(DomainException):
    def __init__(self, message="Not found"):
        super().__init__(message, 404)


class AlreadyExistsError(DomainException):
    def __init__(self, message="Already exists"):
        super().__init__(message, 409)


class AlreadyProcessedError(DomainException):
    def __init__(self, message="Already processed"):
        super().__init__(message, 409)


class InvalidOperationError(DomainException):
    def __init__(self, message="Invalid operation"):
        super().__init__(message, 422)


class InvalidTransitionError(DomainException):
    def __init__(self, message="Invalid transition"):
        super().__init__(message, 422)


class ImplementationNotFoundError(DomainException):
    def __init__(self, message="Not supported"):
        super().__init__(message, 400)
