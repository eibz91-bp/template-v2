from exception.decorators import handle_external_errors
from entity.loan import Loan


class ScoreProviderService:
    def __init__(self, http_client, url: str):
        self.http_client = http_client
        self.url = url

    @handle_external_errors
    async def get_score(self, loan: Loan) -> int:
        response = await self.http_client.post(
            self.url,
            json={"user_id": loan.user_id, "amount": loan.amount},
        )
        response.raise_for_status()
        return response.json()["score"]
