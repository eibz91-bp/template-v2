# Architecture Plan v2

Operational document. If you want to know *why* a decision was made, read the corresponding ADR. If you want to know *how* to implement, read this document.

---

## Guiding Principles

> Full detail in ADR.md → Guiding Principles

1. Business does not depend on technology
2. Code reads top to bottom
3. Dependencies go in one direction
4. Layers communicate through contracts
5. Entities know their own rules
6. Errors belong to the domain
7. Decisions are documented and can be challenged
8. Discipline sustains everything else
9. AI accelerates, humans decide
10. Complexity is added when it hurts, not before

---

## Project structure — ADR-016

Each bounded context has 3 layers: `domain/`, `application/`, `infrastructure/`. Cross-cutting concerns live in `shared/`.

```
template/
├── app.py                          # Composition root: create_app() + lifespan
├── config/settings.py              # pydantic-settings with env_prefix
│
├── loan/                           # ← Bounded Context
│   ├── domain/
│   │   ├── entity/                 # @dataclass with own rules
│   │   │   ├── loan.py
│   │   │   └── result.py
│   │   ├── port/                   # typing.Protocol contracts
│   │   │   ├── loan_repository_port.py
│   │   │   ├── loan_query_repository_port.py
│   │   │   └── disburse_provider_port.py
│   │   └── exception/              # Context-specific domain exceptions (if needed)
│   │
│   ├── application/
│   │   ├── use_case/               # 1 class = 1 operation
│   │   │   ├── request_loan.py
│   │   │   ├── evaluate_loan.py
│   │   │   ├── disburse_loan.py
│   │   │   └── get_loan_detail.py
│   │   └── factory/                # Strategy selection
│   │       └── disburse_provider_factory.py
│   │
│   └── infrastructure/
│       ├── adapter/
│       │   ├── persistence/        # SqlAlchemy*Repository implementations
│       │   │   ├── sqlalchemy_loan_repository.py
│       │   │   └── sqlalchemy_loan_query_repository.py
│       │   └── external/           # HTTP service integrations
│       │       ├── stp_disburse_service.py
│       │       └── nvio_disburse_service.py
│       ├── model/                  # SQLAlchemy ORM models
│       │   └── loan_model.py
│       ├── http/
│       │   ├── controller/         # Presentation: receive, delegate, return
│       │   │   └── loan_controller.py
│       │   ├── schema/             # Pydantic request/response DTOs
│       │   │   └── loan_schema.py
│       │   └── api/v1/             # APIRouter endpoints
│       │       └── loans.py
│
├── shared/                         # ← Shared Kernel
│   ├── domain/
│   │   ├── entity/                 # Cross-domain value objects (Money, etc.)
│   │   └── exception/
│   │       ├── base.py             # AppException(message) — no status_code
│   │       └── domain.py           # DomainException → business errors
│   └── infrastructure/
│       ├── database/
│       │   ├── base.py             # DeclarativeBase (shared across all contexts)
│       │   ├── connection.py       # Database: engine + session_factory
│       │   ├── context.py          # session_context + get_current_session (contextvars)
│       │   ├── transaction.py      # transaction_context + explicit commit
│       │   └── dependencies.py     # Depends(get_db_connection) for FastAPI
│       └── exception/
│           ├── infrastructure.py   # DatabaseException, ExternalServiceException
│           ├── decorators.py       # @handle_db_errors, @handle_external_errors
│           └── http_handler.py     # STATUS_MAP: exception type → HTTP code
│
├── dependencies/                   # Global DI
│   ├── container.py                # build_container() → complete wiring
│   └── providers.py                # Depends() that extract from app.state
│
├── migrations/                     # Alembic autogenerate from model/
├── pyproject.toml                  # Poetry + config for flake8, isort, black, pytest, mypy
└── tests/
    ├── unit/
    │   └── loan/                   # Mirrors bounded context structure
    └── integration/
        └── loan/
```

---

## Dependency rule — ADR-009, ADR-012, ADR-016

Within a bounded context:

```
infrastructure/ ──► application/ ──► domain/
```

- `domain/` never imports from `application/` or `infrastructure/`
- `application/` never imports from `infrastructure/` — depends on ports (Protocols)
- `infrastructure/` implements ports, imports entities for conversion

Between contexts and shared:

```
<context>/  ──►  shared/
loan/       ──►  shared/          ✓
shared/     ──►  loan/            ✗ NEVER
loan/       ──►  payment/         ✗ NEVER (use domain services or events)
```

Full dependency chain:

```
Controller  ──►  Use Case  ──►  Port (Protocol)  ◄──  Repository/Service
                           ──►  Entity
                           ──►  Factory

Entity and Port do not depend on anything external. They are the core.
Domain exceptions are part of the core (entity imports them from shared or own context).
```

```
┌─────────────────────────────────────────────────────────┐
│  FastAPI, SQLAlchemy, httpx (Frameworks)                │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Controller, Repository, Service                │    │
│  │  Schema (Pydantic), Model (ORM)                 │    │
│  │  ── infrastructure/ ──                          │    │
│  │  ┌─────────────────────────────────────────┐    │    │
│  │  │  Use Case, Factory                      │    │    │
│  │  │  ── application/ ──                     │    │    │
│  │  │  ┌─────────────────────────────────┐    │    │    │
│  │  │  │  Entity + Port                  │    │    │    │
│  │  │  │  Exception (domain)             │    │    │    │
│  │  │  │  ── domain/ ──                  │    │    │    │
│  │  │  └─────────────────────────────────┘    │    │    │
│  │  └─────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

---

## Layers and responsibilities

### Entity (`<context>/domain/entity/`) — ADR-010

Dataclass with its own business rules. The entity is an expert on itself.

```python
@dataclass
class Loan:
    id: str
    user_id: str
    amount: float
    status: str
    score: int | None
    created_at: str

    def ensure_can_evaluate(self):
        if self.status != "pending":
            raise InvalidOperationError(
                f"Cannot evaluate loan in '{self.status}' status, expected 'pending'"
            )

    def ensure_can_disburse(self):
        if self.status != "approved":
            raise InvalidOperationError(
                f"Cannot disburse loan in '{self.status}' status, expected 'approved'"
            )

    def determine_evaluation_status(self, score: int, min_score: int) -> str:
        return "approved" if score >= min_score else "rejected"
```

| Can | Cannot |
|---|---|
| Rules about itself (`ensure_can_*`, `determine_*`) | Import repos, services, ports |
| Import domain exceptions (from shared or own context) | Know about HTTP, DB, frameworks |
| Hold pure data (dataclass) | Persist itself (`loan.save()`) |

**User** has no methods because today it has no business rules of its own.

---

### Port (`<context>/domain/port/`) — ADR-009

Contracts with `typing.Protocol`. The use case depends on the Protocol, not the concrete.

```python
class LoanRepositoryPort(Protocol):
    async def get_by_id(self, loan_id: str) -> Loan | None: ...
    async def create(self, user_id: str, amount: float) -> Loan: ...
    async def update_status_if(self, loan_id: str, from_status: str, to_status: str) -> Loan | None: ...
```

**Naming:** Ports use clean contract names with `Port` suffix: `LoanRepositoryPort`, `DisburseProviderPort`.

The repo implements implicitly — no inheritance, duck typing verifiable with `mypy --strict`.

---

### Use Case (`<context>/application/use_case/`) — ADR-003, ADR-010

Orchestration. 1 class = 1 operation. Linear guards + `transaction_context` with explicit commit.

**Type 1 — DB only:**
```python
class RegisterUser:
    async def execute(self, email: str, name: str):
        async with transaction_context() as tx:
            existing = await self.user_repo.get_by_email(email)
            self.ensure_not_exists(existing)
            result = await self.user_repo.create(email, name)
            await tx.commit()
        return result
```

**Type 2 — DB + external service:**
```python
class DisburseLoan:
    async def execute(self, loan_id: str, provider_name: str):
        loan = await self.loan_repo.get_by_id(loan_id)
        self.ensure_exists(loan, "Loan not found")
        loan.ensure_can_disburse()                      # ← entity validates

        async with transaction_context() as tx:         # TX 1: intermediate status
            updated = await self.loan_repo.update_status_if(loan_id, "approved", "disbursing")
            self.ensure_was_updated(updated)
            await tx.commit()

        provider = self.factory.get(provider_name)      # outside TX
        result = await provider.execute(loan)

        async with transaction_context() as tx:         # TX 2: final result
            await self.loan_repo.update_status(loan_id, "disbursed")
            await tx.commit()

        return result
```

**Type 3 — Read only:**
```python
class GetLoanDetail:
    async def execute(self, loan_id: str):
        detail = await self.loan_query_repo.get_with_user(loan_id)
        self.ensure_exists(detail, "Loan not found")
        return detail
```

| Can | Cannot |
|---|---|
| Call repos and services (via Port) | Know about HTTP/FastAPI |
| Linear guards (`ensure_*`) | Try/catch |
| `transaction_context()` + `tx.commit()` | Write SQL |
| Delegate to `entity.ensure_can_*()` | Logic that belongs to the entity |

**Imports:** Use cases import from `shared.infrastructure.database.transaction` (orchestration) and from their own context's `domain/port/` and `domain/entity/`. Never from their own context's `infrastructure/`.

---

### Controller (`<context>/infrastructure/http/controller/`) — ADR-012

Receives HTTP request, delegates to use case, returns response.

```python
class LoanController:
    async def disburse(self, loan_id: str, request: DisburseLoanRequest):
        result = await self.disburse_loan.execute(loan_id, request.provider)
        return DisburseLoanResponse(status=result.status, reference=result.reference)

    async def detail(self, loan_id: str):
        detail = await self.get_loan_detail.execute(loan_id)
        return LoanDetailResponse.model_validate(detail)    # dict → Pydantic
```

Zero business logic. Zero try/catch.

---

### Repository (`<context>/infrastructure/adapter/persistence/`) — ADR-006, ADR-007

SQLAlchemy ORM. Write repo = 1 table. Query repo = JOINs.

**Naming:** Persistence adapters use technology prefix: `SqlAlchemyLoanRepository`, `SqlAlchemyLoanQueryRepository`.

**Write repo:**
```python
class SqlAlchemyLoanRepository:
    @handle_db_errors
    async def get_by_id(self, loan_id: str) -> Loan | None:
        session = get_current_session()
        result = await session.execute(
            select(LoanModel).where(LoanModel.id == loan_id)
        )
        model = result.scalars().first()
        return model.to_entity() if model else None     # ← model.to_entity()

    @handle_db_errors
    async def create(self, user_id: str, amount: float) -> Loan:
        session = get_current_session()
        model = LoanModel(user_id=user_id, amount=amount, status="pending")
        session.add(model)
        await session.flush()                            # ← flush, not commit
        return model.to_entity()
```

**Query repo (JOINs, returns dict):**
```python
class SqlAlchemyLoanQueryRepository:
    @handle_db_errors
    async def get_with_user(self, loan_id: str) -> dict | None:
        session = get_current_session()
        result = await session.execute(
            select(LoanModel.id, LoanModel.amount, LoanModel.status,
                   UserModel.name.label("user_name"))
            .join(UserModel, LoanModel.user_id == UserModel.id)
            .where(LoanModel.id == loan_id)
        )
        row = result.first()
        return dict(row._mapping) if row else None
```

**Key rules:**
- `session.flush()` in repo, `tx.commit()` in use case
- `@handle_db_errors` always (safety net → `DatabaseException`)
- `IntegrityError → AlreadyExistsError` as a targeted override when it has business meaning

**Imports:**
```python
from shared.infrastructure.database.context import get_current_session
from shared.infrastructure.exception.decorators import handle_db_errors
from loan.domain.entity.loan import Loan
from loan.infrastructure.model.loan_model import LoanModel
```

---

### Model (`<context>/infrastructure/model/`) — ADR-006

SQLAlchemy ORM. Single source of truth for the schema. Alembic autogenerate from here.

`Base` (DeclarativeBase) lives in `shared/infrastructure/database/base.py` — all contexts import from there.

```python
from shared.infrastructure.database.base import Base

class LoanModel(Base):
    __tablename__ = "loans"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True,
                                     server_default=text("gen_random_uuid()"))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'pending'"))
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def to_entity(self) -> Loan:
        return Loan(id=str(self.id), user_id=str(self.user_id), ...)
```

**Migrations:** `alembic revision --autogenerate -m "description"` → detects changes automatically. Alembic `env.py` imports `Base` from `shared/infrastructure/database/base.py` and all models from each context's `infrastructure/model/` to discover tables across bounded contexts.

---

### Service (`<context>/infrastructure/adapter/external/`) — ADR-001

External integrations. `@handle_external_errors` translates httpx errors.

**Naming:** External adapters use provider prefix: `StpDisburseService`, `NvioDisburseService`.

```python
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
```

Interchangeable services share the same signature (`execute(loan) -> Result`) → Strategy pattern.

---

### Factory (`<context>/application/factory/`) — eliminates if/else

```python
class DisburseProviderFactory:
    def __init__(self, implementations: dict):
        self.implementations = implementations

    def get(self, name: str):
        implementation = self.implementations.get(name)
        if not implementation:
            raise ImplementationNotFoundError(f"Disburse provider '{name}' not supported")
        return implementation
```

Adding a provider = registering it in `dependencies/container.py`. Without touching existing code.

---

### Schema (`<context>/infrastructure/http/schema/`) — ADR-011

Pydantic. HTTP boundary only. Request validation + response serialization.

```python
class RequestLoanRequest(BaseModel):
    user_id: str
    amount: float

class LoanResponse(BaseModel):
    id: str
    user_id: str
    amount: float
    status: str
    score: int | None = None
```

Don't confuse: `schema/` = HTTP, `entity/` = domain, `model/` = DB.

---

### Exception (`shared/domain/exception/` + `shared/infrastructure/exception/`) — ADR-004

Typed hierarchy **without HTTP status codes**. The mapping lives in `http_handler.py`.

```
AppException(message)                          # shared/domain/exception/base.py
├── DomainException                            # shared/domain/exception/domain.py
│   ├── EntityNotFoundError       → 404 (via STATUS_MAP)
│   ├── AlreadyExistsError        → 409
│   ├── AlreadyProcessedError     → 409
│   ├── InvalidOperationError     → 422
│   ├── InvalidTransitionError    → 422
│   └── ImplementationNotFoundError → 400
├── DatabaseException             → 503        # shared/infrastructure/exception/infrastructure.py
└── ExternalServiceException      → 502
    ├── ProviderError             → 502
    └── ProviderTimeoutError      → 504
```

**Error flow:**
```
Born in repo/service
  → @handle_db_errors / @handle_external_errors translates to the hierarchy
  → Bubbles up through use case and controller (nobody catches it)
  → HTTP handler in app.py translates to JSONResponse via STATUS_MAP
```

---

### Database (`shared/infrastructure/database/`) — ADR-002, ADR-003

One pool/engine/session_factory for the entire app. All bounded contexts share it.

```
Database (engine + session_factory)     ← singleton in shared/
    │
    ▼
session_context(database)               ← 1 session per request via contextvars
    │
    ├── HTTP: Depends(get_db_connection) automatic
    └── Non-HTTP: async with session_context(database) explicit
    │
    ▼
get_current_session()                   ← repos (any context) get the request's session
    │
    ▼
transaction_context()                   ← use case controls commit/rollback
    await tx.commit()                   ← always explicit
```

---

### DI Container (`dependencies/`) — ADR-012

Global wiring. Imports from all bounded contexts and shared.

```python
# dependencies/container.py — complete wiring in a single file
def build_container(config: Settings) -> Container:
    database = Database()
    http_client = httpx.AsyncClient(timeout=config.http_timeout)

    # Loan context
    loan_repo = SqlAlchemyLoanRepository()
    loan_query_repo = SqlAlchemyLoanQueryRepository()
    stp_service = StpDisburseService(http_client, config.stp_url)
    # ... factories, use cases ...

    return Container(
        database=database,
        http_client=http_client,
        loan_controller=LoanController(request_loan, evaluate_loan, ...),
    )
```

```python
# dependencies/providers.py — injection via Depends()
def get_loan_controller(request: Request) -> LoanController:
    return request.app.state.loan_controller
```

```python
# loan/infrastructure/http/api/v1/loans.py — module-level endpoint
@router.post("/loans/{loan_id}/disburse")
async def disburse_loan_endpoint(
    loan_id: str, body: DisburseLoanRequest,
    ctrl: LoanController = Depends(get_loan_controller),
):
    return await ctrl.disburse(loan_id, body)
```

---

## Request flow

```
POST /loans/l-1/disburse { provider: "stp" }
       │
       ▼
  Depends(get_db_connection)           ← opens session from pool (shared/)
       │
       ▼
  FastAPI validates schema (Pydantic)  ← loan/infrastructure/http/schema/
       │
       ▼
  await ctrl.disburse(loan_id, body)   ← loan/infrastructure/http/controller/
       │
       ▼
  await use_case.execute("l-1", "stp") ← loan/application/use_case/
       │
       ├──► await loan_repo.get_by_id()    ← loan/infrastructure/adapter/persistence/
       ├──► self.ensure_exists(loan)        ← system guard
       ├──► loan.ensure_can_disburse()      ← loan/domain/entity/ guard
       │
       ├──► TX 1: update_status_if("approved", "disbursing") + commit
       │
       ├──► factory.get("stp")              ← loan/application/factory/
       │       └──► StpDisburseService       ← loan/infrastructure/adapter/external/
       ├──► await provider.execute(loan)    ← HTTP to third party (outside TX)
       │
       ├──► TX 2: update_status("disbursed") + commit
       │
       └──► return Result(status, reference)
       │
       ▼
  DisburseLoanResponse { status, reference }
       │
       ▼
  Session returned to pool              ← automatic
```

---

## Data types between layers — ADR-005

```
POST request  →  schema/ (Pydantic)     validates input        [infrastructure/http/schema/]
                     │
Controller       loose fields            passes to use case     [infrastructure/http/controller/]
                     │
Use case         entity/ (dataclass)     autocomplete, logic    [domain/entity/]
                     │
Repository       model/ (SQLAlchemy)     .to_entity()           [infrastructure/model/]
                     │
Query repo       dict                    JOINs, pass-through    [infrastructure/adapter/persistence/]
                     │
Controller       schema/ (Pydantic)      serializes output      [infrastructure/http/schema/]
                     │
Response JSON
```

**Rule:** Does the use case access fields to perform logic? → dataclass. Does it just pass it through? → dict.

---

## Tooling — ADR-013, ADR-014, ADR-015

| Tool | Purpose | Command |
|---|---|---|
| Poetry | Dependencies + deterministic lock | `poetry add`, `poetry install` |
| Flake8 | PEP 8 linting | `poetry run flake8 .` |
| isort | Import sorting | `poetry run isort .` |
| black | Code formatting | `poetry run black .` |
| mypy | Strict typing (`--strict`) | `poetry run mypy .` |
| pytest | Unit + Integration tests | `poetry run pytest tests/unit/ -v` |
| Alembic | Autogenerated migrations | `alembic revision --autogenerate -m "..."` |

---

## Testing — ADR-008

| Layer | Type | What it needs |
|---|---|---|
| Controller | Unit | Mock of the use case |
| Use Case | Unit | Mock of the repo/factory + patch `transaction_context` |
| Entity | Unit | Nothing (pure methods) |
| Repository | Integration | Real DB + `session_context` + rollback |
| Service | Integration | Mock HTTP (`httpx_mock`) |

```bash
poetry run pytest tests/unit/ -v        # fast, no DB
poetry run pytest tests/integration/ -v # requires DB
```

**Patch paths reflect bounded context structure:**
```python
@patch("loan.application.use_case.disburse_loan.transaction_context")
```

---

## Naming conventions — ADR-016

| Concept | Name pattern | Example |
|---|---|---|
| Port | `<Entity><Action>Port` | `LoanRepositoryPort` |
| Persistence adapter | `SqlAlchemy<Entity>Repository` | `SqlAlchemyLoanRepository` |
| External adapter | `<Provider><Action>Service` | `StpDisburseService` |
| Entity | `<Entity>` | `Loan` |
| Use case | `<Action><Entity>` | `DisburseLoan` |
| Controller | `<Entity>Controller` | `LoanController` |
| Schema | `<Action><Entity>Request/Response` | `DisburseLoanRequest` |
| ORM model | `<Entity>Model` | `LoanModel` |

---

## Patterns in use

| Pattern | Where | Example |
|---|---|---|
| Singleton | `dependencies/container.py` | Controllers, use cases, repos — stateless |
| Factory | `<context>/application/factory/` | `DisburseProviderFactory.get("stp")` |
| Strategy | `<context>/infrastructure/adapter/external/` | `StpDisburseService` and `NvioDisburseService` with same signature |
| Protocol (Interface) | `<context>/domain/port/` | `LoanRepositoryPort` — verifiable duck typing |
| DI Container | `dependencies/` | `build_container()` manual wiring |
| Application Factory | `app.py` | `create_app(config)` — testable |
| Bounded Context | Top-level folders | `loan/`, `payment/` — isolated domains |
| Shared Kernel | `shared/` | Database, base exceptions — cross-cutting |

---

## Adding a new bounded context (checklist)

1. Create folder: `<context>/domain/entity/`, `<context>/domain/port/`, `<context>/application/use_case/`, `<context>/infrastructure/adapter/persistence/`, `<context>/infrastructure/model/`, `<context>/infrastructure/http/controller/`, `<context>/infrastructure/http/schema/`, `<context>/infrastructure/http/api/v1/`
2. Add `__init__.py` in each folder
3. Update `migrations/env.py` — import all models from `<context>/infrastructure/model/` so Alembic discovers the new tables

### Per entity within the context:

1. `<context>/domain/entity/new.py` — dataclass with own rules (if any)
2. `<context>/infrastructure/model/new_model.py` — SQLAlchemy ORM + `to_entity()`
3. `alembic revision --autogenerate -m "create new table"`
4. `<context>/domain/port/new_repository_port.py` — Protocol
5. `<context>/infrastructure/adapter/persistence/sqlalchemy_new_repository.py` — implementation with `@handle_db_errors`
6. `<context>/application/use_case/action_new.py` — logic + `transaction_context`
7. `<context>/infrastructure/http/schema/new_schema.py` — request/response Pydantic
8. `<context>/infrastructure/http/controller/new_controller.py` — delegates to use case
9. `<context>/infrastructure/http/api/v1/new.py` — APIRouter with endpoints
10. `dependencies/container.py` — wiring
11. `dependencies/providers.py` — provider function
12. `app.py` — `include_router`
13. `tests/unit/<context>/test_action_new.py` — mocks
