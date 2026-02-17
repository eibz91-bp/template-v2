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

## Project structure

```
template/
├── app.py                        # Composition root: create_app() + lifespan
├── config/settings.py            # pydantic-settings with env_prefix
│
├── api/v1/                       # HTTP endpoints (APIRouter per domain)
├── controller/                   # Presentation: receive, delegate, return
├── use_case/                     # Business logic: guards + transactions
├── entity/                       # Domain: dataclass with own rules
├── port/                         # Contracts: Protocol (typing.Protocol)
│
├── repository/                   # Data access (SQLAlchemy ORM)
├── service/                      # External integrations (httpx)
├── factory/                      # Strategy selection without if/else
├── model/                        # SQLAlchemy ORM: single source of truth for the schema
├── schema/                       # HTTP DTOs: Pydantic request/response
│
├── exception/                    # Typed hierarchy (no HTTP codes)
│   ├── base.py                   # AppException(message) — no status_code
│   ├── domain.py                 # DomainException → business errors
│   ├── infrastructure.py         # DatabaseException, ExternalServiceException
│   ├── decorators.py             # @handle_db_errors, @handle_external_errors
│   └── http_handler.py           # STATUS_MAP: exception type → HTTP code
│
├── database/                     # Connection, session, transactions
│   ├── connection.py             # Database: engine + session_factory
│   ├── context.py                # session_context + get_current_session (contextvars)
│   ├── transaction.py            # transaction_context + explicit commit
│   └── dependencies.py           # Depends(get_db_connection) for FastAPI
│
├── dependencies/                 # Manual DI
│   ├── container.py              # build_container() → complete wiring
│   └── providers.py              # Depends() that extract from app.state
│
├── migrations/                   # Alembic autogenerate from model/
├── pyproject.toml                # Poetry + config for ruff, pytest, mypy
└── tests/
    ├── unit/                     # Controller + Use Case (mocks)
    └── integration/              # Repository + Service (real DB)
```

---

## Dependency rule

```
Controller  ──►  Use Case  ──►  Port (Protocol)  ◄──  Repository
                           ──►  Port (Protocol)  ◄──  Service
                           ──►  Factory
                           ──►  Entity

Entity and Port do not depend on anything external. They are the core.
Domain exceptions are part of the core (entity imports them).
```

```
┌─────────────────────────────────────────────┐
│  FastAPI, SQLAlchemy, httpx (Frameworks)    │
│  ┌─────────────────────────────────────┐    │
│  │  Controller, Repository, Service    │    │
│  │  Schema (Pydantic), Model (ORM)     │    │
│  │  ┌─────────────────────────────┐    │    │
│  │  │  Use Case                   │    │    │
│  │  │  ┌─────────────────────┐    │    │    │
│  │  │  │  Entity + Port      │    │    │    │
│  │  │  │  Exception (domain) │    │    │    │
│  │  │  └─────────────────────┘    │    │    │
│  │  └─────────────────────────────┘    │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

---

## Layers and responsibilities

### Entity (`entity/`) — ADR-010

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
| Import domain exceptions | Know about HTTP, DB, frameworks |
| Hold pure data (dataclass) | Persist itself (`loan.save()`) |

**User** has no methods because today it has no business rules of its own.

---

### Port (`port/`) — ADR-009

Contracts with `typing.Protocol`. The use case depends on the Protocol, not the concrete.

```python
class LoanRepositoryPort(Protocol):
    async def get_by_id(self, loan_id: str) -> Loan | None: ...
    async def create(self, user_id: str, amount: float) -> Loan: ...
    async def update_status_if(self, loan_id: str, from_status: str, to_status: str) -> Loan | None: ...
```

The repo implements implicitly — no inheritance, duck typing verifiable with `mypy --strict`.

---

### Use Case (`use_case/`) — ADR-003, ADR-010

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

---

### Controller (`controller/`) — ADR-012

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

### Repository (`repository/`) — ADR-006, ADR-007

SQLAlchemy ORM. Write repo = 1 table. Query repo = JOINs.

**Write repo:**
```python
class LoanRepository:
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
class LoanQueryRepository:
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

---

### Model (`model/`) — ADR-006

SQLAlchemy ORM. Single source of truth for the schema. Alembic autogenerate from here.

```python
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

Migrations: `alembic revision --autogenerate -m "description"` → detects changes automatically.

---

### Service (`service/`) — ADR-001

External integrations. `@handle_external_errors` translates httpx errors.

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

### Factory (`factory/`) — eliminates if/else

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

### Schema (`schema/`) — ADR-011

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

### Exception (`exception/`) — ADR-004

Typed hierarchy **without HTTP status codes**. The mapping lives in `http_handler.py`.

```
AppException(message)
├── DomainException
│   ├── EntityNotFoundError       → 404 (via STATUS_MAP)
│   ├── AlreadyExistsError        → 409
│   ├── AlreadyProcessedError     → 409
│   ├── InvalidOperationError     → 422
│   ├── InvalidTransitionError    → 422
│   └── ImplementationNotFoundError → 400
├── DatabaseException             → 503
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

### DI Container (`dependencies/`) — ADR-012

```python
# dependencies/container.py — complete wiring in a single file
def build_container(config: Settings) -> Container:
    database = Database()
    http_client = httpx.AsyncClient(timeout=config.http_timeout)

    user_repo = UserRepository()
    loan_repo = LoanRepository()
    # ... services, factories, use cases ...

    return Container(
        database=database,
        http_client=http_client,
        user_controller=UserController(register_user),
        loan_controller=LoanController(request_loan, evaluate_loan, ...),
    )
```

```python
# dependencies/providers.py — injection via Depends()
def get_loan_controller(request: Request) -> LoanController:
    return request.app.state.loan_controller
```

```python
# api/v1/loans.py — module-level endpoint
@router.post("/loans/{loan_id}/disburse")
async def disburse_loan_endpoint(
    loan_id: str, body: DisburseLoanRequest,
    ctrl: LoanController = Depends(get_loan_controller),
):
    return await ctrl.disburse(loan_id, body)
```

---

### Database (`database/`) — ADR-002, ADR-003

```
Database (engine + session_factory)     ← singleton
    │
    ▼
session_context(database)               ← 1 session per request via contextvars
    │
    ├── HTTP: Depends(get_db_connection) automatic
    └── Non-HTTP: async with session_context(database) explicit
    │
    ▼
get_current_session()                   ← repos get the request's session
    │
    ▼
transaction_context()                   ← use case controls commit/rollback
    await tx.commit()                   ← always explicit
```

---

## Request flow

```
POST /loans/l-1/disburse { provider: "stp" }
       │
       ▼
  Depends(get_db_connection)           ← opens session from pool
       │
       ▼
  FastAPI validates schema (Pydantic)  ← DisburseLoanRequest
       │
       ▼
  await ctrl.disburse(loan_id, body)   ← controller delegates
       │
       ▼
  await use_case.execute("l-1", "stp") ← orchestrates
       │
       ├──► await loan_repo.get_by_id()    ← SQLAlchemy ORM → model.to_entity()
       ├──► self.ensure_exists(loan)        ← system guard
       ├──► loan.ensure_can_disburse()      ← entity guard
       │
       ├──► TX 1: update_status_if("approved", "disbursing") + commit
       │
       ├──► factory.get("stp")              ← sync, dict lookup
       │       └──► StpDisburseService
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
POST request  →  schema/ (Pydantic)     validates input
                     │
Controller       loose fields            passes to use case
                     │
Use case         entity/ (dataclass)     autocomplete, types, logic
                     │
Repository       model/ (SQLAlchemy)     .to_entity() on the ORM model
                     │
Query repo       dict                    JOINs, pass-through without conversion
                     │
Controller       schema/ (Pydantic)      serializes output
                     │
Response JSON
```

**Rule:** Does the use case access fields to perform logic? → dataclass. Does it just pass it through? → dict.

---

## Tooling — ADR-013, ADR-014, ADR-015

| Tool | Purpose | Command |
|---|---|---|
| Poetry | Dependencies + deterministic lock | `poetry add`, `poetry install` |
| Ruff | PEP 8 + linting | `poetry run ruff check .` |
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

---

## Patterns in use

| Pattern | Where | Example |
|---|---|---|
| Singleton | `dependencies/container.py` | Controllers, use cases, repos — stateless |
| Factory | `factory/` | `DisburseProviderFactory.get("stp")` |
| Strategy | `service/` | `StpDisburseService` and `NvioDisburseService` with same signature |
| Protocol (Interface) | `port/` | `LoanRepositoryPort` — verifiable duck typing |
| DI Container | `dependencies/` | `build_container()` manual wiring |
| Application Factory | `app.py` | `create_app(config)` — testable |

---

## Adding a new domain (checklist)

1. `entity/new.py` — dataclass with own rules (if any)
2. `model/new_model.py` — SQLAlchemy ORM + `to_entity()`
3. `alembic revision --autogenerate -m "create new table"`
4. `port/new_repository_port.py` — Protocol
5. `repository/new_repository.py` — implementation with `@handle_db_errors`
6. `use_case/action_new.py` — logic + `transaction_context`
7. `schema/new_schema.py` — request/response Pydantic
8. `controller/new_controller.py` — delegates to use case
9. `api/v1/new.py` — APIRouter with endpoints
10. `dependencies/container.py` — wiring
11. `dependencies/providers.py` — provider function
12. `app.py` — `include_router`
13. `tests/unit/test_action_new.py` — mocks
