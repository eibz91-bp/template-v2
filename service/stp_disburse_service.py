from exception.decorators import handle_external_errors
from entity.loan import Loan
from entity.result import Result


class StpDisburseService:
    def __init__(self, http_client, url: str):
        self.http_client = http_client
        self.url = url

    @handle_external_errors
    async def execute(self, loan: Loan) -> Result:
        response = await self.http_client.post(
            self.url,
            json={"loan_id": loan.id, "amount": loan.amount, "user_id": loan.user_id},
        )
        response.raise_for_status()
        return Result(status="disbursed", reference=response.json()["reference"])
