from fastapi import FastAPI, Depends
import httpx

from config.settings import settings
from database.connection import Database
from database import dependencies as db_deps
from exception.domain import DomainException
from exception.infrastructure import DatabaseException, ExternalServiceException
from exception.handler import (
    catch_all_handler,
    database_handler,
    domain_handler,
    external_handler,
)

# --- Database ---
database = Database()
db_deps.database = database

# --- HTTP Client ---
http_client = httpx.AsyncClient(timeout=settings.http_timeout)

# --- Repositories ---
from repository.user_repository import UserRepository
from repository.loan_repository import LoanRepository
from repository.loan_query_repository import LoanQueryRepository
from repository.outbox_repository import OutboxRepository

user_repo = UserRepository()
loan_repo = LoanRepository()
loan_query_repo = LoanQueryRepository()
outbox_repo = OutboxRepository()

# --- Services ---
from service.score_provider_service import ScoreProviderService
from service.stp_disburse_service import StpDisburseService
from service.nvio_disburse_service import NvioDisburseService

score_provider = ScoreProviderService(http_client, settings.score_provider_url)
stp_disburse = StpDisburseService(http_client, settings.stp_url)
nvio_disburse = NvioDisburseService(http_client, settings.nvio_url)

# --- Factories ---
from factory.disburse_provider_factory import DisburseProviderFactory

disburse_factory = DisburseProviderFactory({
    "stp": stp_disburse,
    "nvio": nvio_disburse,
})

# --- Use Cases ---
from use_case.register_user import RegisterUser
from use_case.request_loan import RequestLoan
from use_case.evaluate_loan import EvaluateLoan
from use_case.disburse_loan import DisburseLoan
from use_case.get_loan_detail import GetLoanDetail

register_user = RegisterUser(user_repo)
request_loan = RequestLoan(user_repo, loan_repo)
evaluate_loan = EvaluateLoan(loan_repo, score_provider, settings.score_min_threshold)
disburse_loan = DisburseLoan(loan_repo, disburse_factory, outbox_repo)
get_loan_detail = GetLoanDetail(loan_query_repo)

# --- Controllers ---
from controller.user_controller import UserController
from controller.loan_controller import LoanController

user_controller = UserController(register_user)
loan_controller = LoanController(request_loan, evaluate_loan, disburse_loan, get_loan_detail)

# --- FastAPI ---
from schema.user_schema import RegisterUserRequest
from schema.loan_schema import RequestLoanRequest, DisburseLoanRequest

app = FastAPI(
    title="Loan Service",
    dependencies=[Depends(db_deps.get_db_connection)],
)

app.add_exception_handler(DomainException, domain_handler)
app.add_exception_handler(DatabaseException, database_handler)
app.add_exception_handler(ExternalServiceException, external_handler)
app.add_exception_handler(Exception, catch_all_handler)


@app.on_event("startup")
async def startup():
    await database.connect(
        settings.database_url,
        min_size=settings.database_min_pool,
        max_size=settings.database_max_pool,
    )


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()
    await http_client.aclose()


# --- Endpoints ---
@app.post("/users")
async def register_user_endpoint(request: RegisterUserRequest):
    return await user_controller.register(request)


@app.post("/loans")
async def request_loan_endpoint(request: RequestLoanRequest):
    return await loan_controller.request(request)


@app.post("/loans/{loan_id}/evaluate")
async def evaluate_loan_endpoint(loan_id: str):
    return await loan_controller.evaluate(loan_id)


@app.post("/loans/{loan_id}/disburse")
async def disburse_loan_endpoint(loan_id: str, request: DisburseLoanRequest):
    return await loan_controller.disburse(loan_id, request)


@app.get("/loans/{loan_id}")
async def get_loan_detail_endpoint(loan_id: str):
    return await loan_controller.detail(loan_id)
