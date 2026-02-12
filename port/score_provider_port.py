from typing import Protocol

from entity.loan import Loan


class ScoreProviderPort(Protocol):
    async def get_score(self, loan: Loan) -> int: ...
