import pytest

from user.infrastructure.adapter.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
from loan.infrastructure.adapter.persistence.sqlalchemy_loan_repository import SqlAlchemyLoanRepository


@pytest.mark.usefixtures("db")
async def test_create_and_get_loan(db):
    user_repo = SqlAlchemyUserRepository()
    loan_repo = SqlAlchemyLoanRepository()

    user = await user_repo.create("loan@test.com", "Loan User")
    loan = await loan_repo.create(user.id, 5000.00)

    assert loan.status == "pending"
    assert loan.amount == 5000.00
    assert loan.score is None

    fetched = await loan_repo.get_by_id(loan.id)
    assert fetched is not None
    assert fetched.user_id == user.id


@pytest.mark.usefixtures("db")
async def test_update_status_if(db):
    user_repo = SqlAlchemyUserRepository()
    loan_repo = SqlAlchemyLoanRepository()

    user = await user_repo.create("status@test.com", "Status User")
    loan = await loan_repo.create(user.id, 3000.00)

    updated = await loan_repo.update_status_if(loan.id, "pending", "scoring")
    assert updated is not None
    assert updated.status == "scoring"

    # Second attempt should fail (status already changed)
    not_updated = await loan_repo.update_status_if(loan.id, "pending", "scoring")
    assert not_updated is None


@pytest.mark.usefixtures("db")
async def test_save_evaluation(db):
    user_repo = SqlAlchemyUserRepository()
    loan_repo = SqlAlchemyLoanRepository()

    user = await user_repo.create("eval@test.com", "Eval User")
    loan = await loan_repo.create(user.id, 2000.00)

    # Must be in 'scoring' status first
    await loan_repo.update_status_if(loan.id, "pending", "scoring")

    evaluated = await loan_repo.save_evaluation(loan.id, 750, "approved")
    assert evaluated is not None
    assert evaluated.score == 750
    assert evaluated.status == "approved"


@pytest.mark.usefixtures("db")
async def test_get_nonexistent_loan(db):
    loan_repo = SqlAlchemyLoanRepository()
    result = await loan_repo.get_by_id("00000000-0000-0000-0000-000000000000")
    assert result is None
