from fastapi import Request

from controller.loan_controller import LoanController
from controller.payment_controller import PaymentController
from controller.user_controller import UserController


def get_user_controller(request: Request) -> UserController:
    return request.app.state.user_controller


def get_loan_controller(request: Request) -> LoanController:
    return request.app.state.loan_controller


def get_payment_controller(request: Request) -> PaymentController:
    return request.app.state.payment_controller
