from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from api.v1 import loans, users, webhooks
from config.settings import Settings, settings
from database import dependencies as db_deps
from dependencies.container import build_container
from exception.domain import DomainException
from exception.http_handler import (
    catch_all_handler,
    database_handler,
    domain_handler,
    external_handler,
)
from exception.infrastructure import DatabaseException, ExternalServiceException


def create_app(config: Settings = settings) -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        container = build_container(config)

        await container.database.connect(
            config.database_url,
            min_size=config.database_min_pool,
            max_size=config.database_max_pool,
        )

        app.state.database = container.database
        app.state.user_controller = container.user_controller
        app.state.loan_controller = container.loan_controller
        app.state.payment_controller = container.payment_controller

        try:
            yield
        finally:
            await container.database.disconnect()
            await container.http_client.aclose()

    application = FastAPI(
        title="Loan Service",
        lifespan=lifespan,
        dependencies=[Depends(db_deps.get_db_connection)],
    )

    application.add_exception_handler(DomainException, domain_handler)
    application.add_exception_handler(DatabaseException, database_handler)
    application.add_exception_handler(ExternalServiceException, external_handler)
    application.add_exception_handler(Exception, catch_all_handler)

    application.include_router(users.router)
    application.include_router(loans.router)
    application.include_router(webhooks.router)

    return application


app = create_app()
