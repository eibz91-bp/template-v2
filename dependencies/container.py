from dataclasses import dataclass

import httpx

from config.settings import Settings
from controller.loan_controller import LoanController
from controller.payment_controller import PaymentController
from controller.user_controller import UserController
from database.connection import Database
from factory.disburse_provider_factory import DisburseProviderFactory
from repository.loan_query_repository import LoanQueryRepository
from repository.loan_repository import LoanRepository
from repository.payment_repository import PaymentRepository
from repository.user_repository import UserRepository
from service.nvio_disburse_service import NvioDisburseService
from service.score_provider_service import ScoreProviderService
from service.stp_disburse_service import StpDisburseService
from use_case.disburse_loan import DisburseLoan
from use_case.evaluate_loan import EvaluateLoan
from use_case.get_loan_detail import GetLoanDetail
from use_case.pay_loan import PayLoan
from use_case.register_user import RegisterUser
from use_case.request_loan import RequestLoan


@dataclass(frozen=True)
class Container:
    database: Database
    http_client: httpx.AsyncClient
    user_controller: UserController
    loan_controller: LoanController
    payment_controller: PaymentController


def build_container(config: Settings) -> Container:
    # --- Infrastructure ---
    database = Database()
    http_client = httpx.AsyncClient(timeout=config.http_timeout)

    # --- Repositories ---
    user_repo = UserRepository()
    loan_repo = LoanRepository()
    loan_query_repo = LoanQueryRepository()
    payment_repo = PaymentRepository()

    # --- Services ---
    score_provider = ScoreProviderService(http_client, config.score_provider_url)
    stp_disburse = StpDisburseService(http_client, config.stp_url)
    nvio_disburse = NvioDisburseService(http_client, config.nvio_url)

    # --- Factories ---
    disburse_factory = DisburseProviderFactory({
        "stp": stp_disburse,
        "nvio": nvio_disburse,
    })

    # --- Use Cases ---
    register_user = RegisterUser(user_repo)
    request_loan = RequestLoan(user_repo, loan_repo)
    evaluate_loan = EvaluateLoan(
        loan_repo, score_provider, config.score_min_threshold,
    )
    disburse_loan = DisburseLoan(loan_repo, disburse_factory)
    get_loan_detail = GetLoanDetail(loan_query_repo)
    pay_loan = PayLoan(loan_repo, payment_repo)

    return Container(
        database=database,
        http_client=http_client,
        user_controller=UserController(register_user),
        loan_controller=LoanController(
            request_loan, evaluate_loan, disburse_loan, get_loan_detail,
        ),
        payment_controller=PaymentController(pay_loan),
    )
