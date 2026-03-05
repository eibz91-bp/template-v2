from shared.domain.exception.base import AppException


class DomainException(AppException):
    pass


class EntityNotFoundError(DomainException):
    def __init__(self, message="Not found"):
        super().__init__(message)


class AlreadyExistsError(DomainException):
    def __init__(self, message="Already exists"):
        super().__init__(message)


class AlreadyProcessedError(DomainException):
    def __init__(self, message="Already processed"):
        super().__init__(message)


class InvalidOperationError(DomainException):
    def __init__(self, message="Invalid operation"):
        super().__init__(message)


class InvalidTransitionError(DomainException):
    def __init__(self, message="Invalid transition"):
        super().__init__(message)


class ImplementationNotFoundError(DomainException):
    def __init__(self, message="Not supported"):
        super().__init__(message)
