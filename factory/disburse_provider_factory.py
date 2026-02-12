from exception.domain import ImplementationNotFoundError


class DisburseProviderFactory:
    def __init__(self, implementations: dict):
        self.implementations = implementations

    def get(self, name: str):
        implementation = self.implementations.get(name)
        if not implementation:
            raise ImplementationNotFoundError(f"Disburse provider '{name}' not supported")
        return implementation
