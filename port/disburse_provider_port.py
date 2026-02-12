from typing import Protocol

from entity.loan import Loan
from entity.result import Result


class DisburseProviderPort(Protocol):
    async def execute(self, loan: Loan) -> Result: ...
