from typing import Protocol

from loan.domain.entity.loan import Loan
from loan.domain.entity.result import Result


class DisburseProviderPort(Protocol):
    async def execute(self, loan: Loan) -> Result: ...
