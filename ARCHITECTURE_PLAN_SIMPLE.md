# Architecture Plan — Simplified Structure

Operational document. Same principles and ADRs as v2, but with a simplified folder structure that reduces 14 top-level packages to 4.

> For *why* each decision was made, read `ADR.md`. This document covers *how* to implement with fewer folders.

---

## Guiding Principles

> Full detail in ADR.md → Guiding Principles

Same 10 principles apply. The folder simplification changes **where** code lives, not **how** it behaves.

---

## Project structure

```
template/
├── app.py                          # Composition root: create_app() + lifespan + DI wiring
├── config/settings.py              # pydantic-settings with env_prefix
│
├── domain/                         # The core — zero external dependencies
│   ├── loan.py                     # Entity (dataclass) + Port (Protocol)
│   ├── user.py                     # Entity (dataclass) + Port (Protocol)
│   ├── result.py                   # Value objects (Result, etc.)
│   └── exceptions.py               # Full exception hierarchy (no HTTP codes)
│
├── infra/                          # Outer layer — frameworks live here
│   ├── database/                   # Connection, session, transactions
│   │   ├── connection.py           # Database: engine + session_factory
│   │   ├── context.py              # session_context + get_current_session
│   │   └── transaction.py          # transaction_context + explicit commit
│   ├── model/                      # SQLAlchemy ORM models (schema source of truth)
│   │   ├── base.py                 # DeclarativeBase
│   │   ├── user_model.py           # UserModel + to_entity()
│   │   └── loan_model.py           # LoanModel + to_entity()
│   ├── repository/                 # Data access (write + query)
│   │   ├── user_repository.py
│   │   ├── loan_repository.py      # Write: 1 table, returns entities
│   │   └── loan_query_repository.py # Read: JOINs, returns dicts
│   └── service/                    # External integrations + factories
│       ├── score_provider.py
│       ├── stp_disburse.py
│       ├── nvio_disburse.py
│       └── disburse_factory.py     # Strategy selection
│
├── api/                            # HTTP layer — FastAPI lives here
│   ├── deps.py                     # Depends(get_db_connection) + provider functions
│   ├── exceptions.py               # STATUS_MAP + handlers (domain → HTTP code)
│   ├── v1/
│   │   ├── loans.py                # Router + schemas + controller logic
│   │   ├── users.py                # Router + schemas + controller logic
│   │   └── webhooks.py             # Router + schemas + controller logic
│   └── middleware.py               # Future: auth, logging, etc.
│
├── use_case/                       # Business logic — orchestration only
│   ├── register_user.py
│   ├── request_loan.py
│   ├── evaluate_loan.py
│   ├── disburse_loan.py
│   └── pay_loan.py
│
├── migrations/                     # Alembic autogenerate from infra/model/
├── pyproject.toml                  # Poetry + config for ruff, pytest, mypy
└── tests/
    ├── unit/                       # Use case + entity (mocks)
    └── integration/                # Repository + service (real DB)
```

**What merged vs v2:**

| v2 (14 packages) | Simplified (4 packages) | Why |
|---|---|---|
| `entity/` + `port/` | `domain/` | Both are the core with zero deps — same layer |
| `exception/` (5 files) | `domain/exceptions.py` + `api/exceptions.py` | Domain exceptions belong to domain; HTTP mapping belongs to API |
| `controller/` + `schema/` | `api/v1/*.py` | Controllers are HTTP-specific — they belong with the routes |
| `repository/` + `model/` + `service/` + `factory/` | `infra/` | All are outer-layer implementations of domain ports |
| `database/` | `infra/database/` | Database is infrastructure |
| `dependencies/container.py` + `providers.py` | `app.py` + `api/deps.py` | Wiring in app.py, providers in api/ |

---

## Dependency rule

```
api/  ──►  use_case/  ──►  domain/ (Entity + Port)  ◄──  infra/
```

Same rule as v2, but now it maps directly to folder imports:
- `domain/` imports nothing external
- `use_case/` imports only `domain/` and `infra.database.transaction`
- `infra/` imports `domain/` (for entities and ports)
- `api/` imports everything (it's the outermost layer)

```
┌──────────────────────────────────────┐
│  api/  (FastAPI, Pydantic schemas)  │
│  ┌──────────────────────────────┐   │
│  │  infra/  (SQLAlchemy, httpx) │   │
│  │  ┌──────────────────────┐    │   │
│  │  │  use_case/           │    │   │
│  │  │  ┌──────────────┐    │    │   │
│  │  │  │  domain/      │    │    │   │
│  │  │  └──────────────┘    │    │   │
│  │  └──────────────────────┘    │   │
│  └──────────────────────────────┘   │
└──────────────────────────────────────┘
```

---

## Key differences from v2

### 1. Entity + Port live together in `domain/`

```python
# domain/loan.py — entity AND port in the same file

from dataclasses import dataclass
from typing import Protocol

from domain.exceptions import InvalidOperationError


@dataclass
class Loan:
    id: str
    user_id: str
    amount: float
    status: str
    score: int | None
    created_at: str

    def ensure_can_evaluate(self) -> None:
        if self.status != "pending":
            raise InvalidOperationError(
                f"Cannot evaluate loan in '{self.status}' status"
            )

    def ensure_can_disburse(self) -> None:
        if self.status != "approved":
            raise InvalidOperationError(
                f"Cannot disburse loan in '{self.status}' status"
            )

    def determine_evaluation_status(self, score: int, min_score: int) -> str:
        return "approved" if score >= min_score else "rejected"


class LoanRepositoryPort(Protocol):
    async def get_by_id(self, loan_id: str) -> Loan | None: ...
    async def create(self, user_id: str, amount: float) -> Loan: ...
    async def update_status_if(
        self, loan_id: str, from_status: str, to_status: str,
    ) -> Loan | None: ...
    async def update_status(self, loan_id: str, status: str) -> None: ...


class LoanQueryRepositoryPort(Protocol):
    async def get_with_user(self, loan_id: str) -> dict | None: ...
```

**Why together:** Entity and Port are both part of the domain core. Neither depends on external frameworks. A Port describes what the domain *needs* — it's a domain contract, not infrastructure.

### 2. Controller + Schema merge into route files

```python
# api/v1/loans.py — router + schemas + delegation in one file

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_loan_use_cases

router = APIRouter(prefix="/loans", tags=["loans"])


# --- Schemas (HTTP boundary only) ---

class RequestLoanRequest(BaseModel):
    user_id: str
    amount: float

class LoanResponse(BaseModel):
    id: str
    user_id: str
    amount: float
    status: str
    score: int | None = None


# --- Endpoints (controller logic inlined) ---

@router.post("")
async def request_loan(
    body: RequestLoanRequest,
    use_cases = Depends(get_loan_use_cases),
):
    loan = await use_cases.request_loan.execute(body.user_id, body.amount)
    return LoanResponse(**asdict(loan))

@router.post("/{loan_id}/evaluate")
async def evaluate_loan(
    loan_id: str,
    use_cases = Depends(get_loan_use_cases),
):
    loan = await use_cases.evaluate_loan.execute(loan_id)
    return LoanResponse(**asdict(loan))
```

**Why inlined:** The controller was a class that only delegated — one-liner methods. When the "controller" is `return await use_case.execute(...)`, a separate class adds a file without adding value.

### 3. All exceptions in one domain file

```python
# domain/exceptions.py — full hierarchy, no HTTP codes

class AppException(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

class DomainException(AppException): pass
class EntityNotFoundError(DomainException): ...
class AlreadyExistsError(DomainException): ...
class AlreadyProcessedError(DomainException): ...
class InvalidOperationError(DomainException): ...
class InvalidTransitionError(DomainException): ...
class ImplementationNotFoundError(DomainException): ...

class InfrastructureException(AppException): pass
class DatabaseException(InfrastructureException): ...
class ExternalServiceException(InfrastructureException): ...
class ProviderError(ExternalServiceException): ...
class ProviderTimeoutError(ExternalServiceException): ...
```

```python
# api/exceptions.py — HTTP mapping (only file that knows about status codes)

DOMAIN_STATUS_MAP = {
    EntityNotFoundError: 404,
    AlreadyExistsError: 409,
    AlreadyProcessedError: 409,
    InvalidOperationError: 422,
    InvalidTransitionError: 422,
    ImplementationNotFoundError: 400,
}
```

### 4. DI wiring in app.py

```python
# app.py — composition root with inline wiring

from contextlib import asynccontextmanager
from fastapi import FastAPI

from config.settings import Settings, settings


def create_app(config: Settings = settings) -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # --- Build dependency graph (was container.py) ---
        database = Database()
        http_client = httpx.AsyncClient(timeout=config.http_timeout)
        await database.connect(config.database_url)

        user_repo = UserRepository()
        loan_repo = LoanRepository()
        # ... services, factories ...

        app.state.database = database
        app.state.request_loan = RequestLoan(user_repo, loan_repo)
        app.state.evaluate_loan = EvaluateLoan(loan_repo, score_provider, ...)
        # ... etc ...

        try:
            yield
        finally:
            await database.disconnect()
            await http_client.aclose()

    application = FastAPI(title="Loan Service", lifespan=lifespan)
    # exception handlers + routers
    return application
```

**Why inline:** With 5-10 use cases, a separate `container.py` is overhead. When the app grows past ~15 use cases, extract to `container.py` again (principle 10: complexity when it hurts).

---

## What stays exactly the same

All ADR patterns are preserved — only the file organization changes:

| Pattern | v2 | Simplified | Behavior identical? |
|---|---|---|---|
| Full async (ADR-001) | Same | Same | Yes |
| session_context + contextvars (ADR-002) | `database/` | `infra/database/` | Yes |
| transaction_context + explicit commit (ADR-003) | Same | Same | Yes |
| Exception hierarchy + decorators (ADR-004) | `exception/` (5 files) | `domain/exceptions.py` + `api/exceptions.py` | Yes |
| Mixed data types (ADR-005) | Same | Same | Yes |
| ORM + Alembic (ADR-006) | `model/` | `infra/model/` | Yes |
| CQRS Lite (ADR-007) | `repository/` | `infra/repository/` | Yes |
| Unit + Integration tests (ADR-008) | Same | Same | Yes |
| Protocols (ADR-009) | `port/` | `domain/*.py` | Yes |
| Entity as expert (ADR-010) | `entity/` | `domain/*.py` | Yes |
| Schema vs Entity (ADR-011) | `schema/` + `entity/` | `api/v1/*.py` + `domain/*.py` | Yes |
| Manual DI (ADR-012) | `dependencies/` | `app.py` + `api/deps.py` | Yes |
| Ruff + mypy (ADR-013, 014) | Same | Same | Yes |
| Poetry (ADR-015) | Same | Same | Yes |

---

## Use Case layer — unchanged

Use cases remain in their own top-level folder. They are the heart of the app and their patterns don't change:

- Type 1 (DB only): single `transaction_context`
- Type 2 (DB + external): two `transaction_context` blocks
- Type 3 (read only): no transaction
- Zero try/catch, linear guards, entity delegates

---

## Data types between layers — ADR-005

```
POST request  →  api/v1/*.py (Pydantic)      validates input
                     │
Route handler    loose fields                 passes to use case
                     │
Use case         domain/*.py (dataclass)      autocomplete, types, logic
                     │
Repository       infra/model/*.py (ORM)       .to_entity() on the model
                     │
Query repo       dict                         JOINs, pass-through
                     │
Route handler    api/v1/*.py (Pydantic)       serializes output
                     │
Response JSON
```

---

## Tooling — ADR-013, ADR-014, ADR-015

Same commands, unchanged:

| Tool | Purpose | Command |
|---|---|---|
| Poetry | Dependencies + deterministic lock | `poetry add`, `poetry install` |
| Ruff | PEP 8 + linting | `poetry run ruff check .` |
| mypy | Strict typing (`--strict`) | `poetry run mypy .` |
| pytest | Unit + Integration tests | `poetry run pytest tests/unit/ -v` |
| Alembic | Autogenerated migrations | `alembic revision --autogenerate -m "..."` |

---

## Testing — ADR-008

| Layer | Test type | What it needs |
|---|---|---|
| Route handler | Unit | Mock of the use case |
| Use Case | Unit | Mock of repos + patch `transaction_context` |
| Entity | Unit | Nothing (pure methods) |
| Repository | Integration | Real DB + `session_context` + rollback |
| Service | Integration | Mock HTTP (`httpx_mock`) |

---

## Adding a new domain (checklist)

Reduced from 13 steps to 8:

1. `domain/new.py` — `@dataclass` entity + `Protocol` port
2. `infra/model/new_model.py` — SQLAlchemy ORM + `to_entity()`
3. `alembic revision --autogenerate -m "create new table"`
4. `infra/repository/new_repository.py` — `@handle_db_errors` on every method
5. `use_case/action_new.py` — guards + `transaction_context` + `tx.commit()`
6. `api/v1/new.py` — router + Pydantic schemas + endpoint handlers
7. `app.py` — wire use case in lifespan + `include_router`
8. `tests/unit/test_action_new.py` — mock repos, patch `transaction_context`

---

## When to graduate back to v2 structure

This simplified structure works well for small-to-medium services (~5-15 use cases). Consider splitting back to the full v2 structure when:

- Route files exceed ~150 lines (extract schemas to `api/schemas/`)
- `app.py` lifespan exceeds ~50 lines of wiring (extract to `container.py`)
- Entity files exceed ~100 lines (entity + port is too much in one file)
- Multiple teams work on different domains (folder-per-domain becomes better)
- You need non-HTTP entry points (CLI, workers) that share controllers

The migration from simplified → v2 is mechanical: split files, move imports, no logic changes.
