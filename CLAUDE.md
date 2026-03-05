# CLAUDE.md — Loan Service (FastAPI + Clean Architecture)

## MANDATORY: Before writing or modifying any code

1. Read `ADR.md` — it contains all architectural decisions with justification. Every rule in this file comes from an ADR. If in doubt, the ADR is the source of truth.
2. Read `ARCHITECTURE_PLAN.md` — it contains the implementation patterns, examples, and checklists derived from the ADRs. Use it as the operational guide.
3. If your change introduces a new pattern not covered by an existing ADR, flag it to the user before proceeding.
4. Never contradict an ADR. If the code contradicts an ADR, the code is wrong.

FastAPI microservice for loan management. Clean architecture with bounded contexts and strict layer separation.

## Commands

```bash
poetry run uvicorn app:app --reload          # Run dev server
poetry run pytest tests/unit/ -v             # Unit tests (no DB)
poetry run pytest tests/integration/ -v      # Integration tests (requires DB)
poetry run flake8 .                          # Lint (PEP 8)
poetry run isort .                           # Sort imports
poetry run black .                           # Format code
poetry run mypy .                            # Strict type checking
alembic revision --autogenerate -m "desc"    # Generate migration from model/
alembic upgrade head                         # Apply migrations
poetry add <pkg>                             # Add dependency (never edit pyproject.toml manually)
```

## Architecture Rules

### Bounded Context structure (ADR-016)
Each bounded context has 3 layers: `domain/`, `application/`, `infrastructure/`. Cross-cutting concerns live in `shared/`.

```
<context>/                      # ← Bounded Context
├── domain/                     # Pure business: entities, ports, exceptions
│   ├── entity/                 # @dataclass with own rules
│   ├── port/                   # typing.Protocol contracts
│   └── exception/              # Context-specific domain exceptions (if needed)
├── application/                # Orchestration: use cases, factories
│   ├── use_case/               # 1 class = 1 operation
│   └── factory/                # Strategy selection
└── infrastructure/             # Everything external: DB, HTTP, frameworks
    ├── adapter/persistence/    # SqlAlchemy*Repository
    ├── adapter/external/       # Provider services (Stp*, Nvio*)
    ├── model/                  # SQLAlchemy ORM
    └── http/
        ├── controller/         # Presentation: receive, delegate, return
        ├── schema/             # Pydantic request/response DTOs
        └── api/v1/             # APIRouter endpoints

shared/                         # ← Shared Kernel
├── domain/
│   ├── entity/                 # Cross-domain value objects (Money, etc.)
│   └── exception/              # AppException, DomainException hierarchy
└── infrastructure/
    ├── database/               # base (DeclarativeBase), connection, context, transaction, dependencies
    └── exception/              # infrastructure exceptions, decorators, http_handler
```

### Dependency direction (ADR-009, ADR-012, ADR-016)

Within a bounded context:
```
infrastructure/ ──► application/ ──► domain/
```
- `domain/` never imports from `application/` or `infrastructure/`
- `application/` never imports from `infrastructure/` — depends on ports (Protocols)
- `infrastructure/` implements ports, imports entities for conversion
- Use cases import `transaction_context` from `shared.infrastructure.database.transaction` (the use case is the orchestrator — ADR-003)

Between contexts and shared:
```
<context>/  ──►  shared/          ✓  (any context can import shared)
shared/     ──►  <context>/       ✗  NEVER
loan/       ──►  payment/         ✗  NEVER directly (use domain services or events)
```
- Every bounded context imports from `shared/` — never the reverse
- `shared/` never imports from any bounded context
- A bounded context NEVER directly imports another context's repository, use case, or entity (ADR-016)

### Inter-context communication (ADR-016)

When context A needs data from context B:
1. Context B exposes a domain service (sync) or domain event (async) from its `application/` layer
2. Start simple (direct service call), add events when async decoupling is needed
3. Query repos (ADR-007) are the exception: they may JOIN across models from different contexts at the infrastructure level, since they are read-only and return `dict` (no entity coupling)

### Full async everywhere (ADR-001)
- Every function in the chain must be `async def` + `await`
- Use `httpx.AsyncClient`, never `requests`. Use `asyncpg`, never `psycopg2`
- If a library has no async support, use `asyncio.to_thread()` as last resort

### Session and transactions (ADR-002, ADR-003)
- Repos get sessions via `get_current_session()` from `shared.infrastructure.database.context` — never accept session as parameter
- Repos call `session.flush()`, never `session.commit()` — the use case owns the commit
- Always use `transaction_context()` with explicit `await tx.commit()`:
```python
async with transaction_context() as tx:
    await self.repo.create(...)
    await tx.commit()
```
- **Type 1** (DB only): one `transaction_context` block
- **Type 2** (DB + external): two `transaction_context` blocks, external call between them
- **Type 3** (read only): no transaction needed

### Exception handling (ADR-004)
- Zero try/catch in use cases and controllers — exceptions bubble up
- Domain exceptions (`shared/domain/exception/domain.py`) have no HTTP status codes
- Repos use `@handle_db_errors` decorator (`shared/infrastructure/exception/decorators.py`)
- Services use `@handle_external_errors` decorator
- HTTP mapping lives only in `shared/infrastructure/exception/http_handler.py` via `DOMAIN_STATUS_MAP` / `INFRA_STATUS_MAP`
- New exception = create class in `shared/domain/exception/domain.py` or `shared/infrastructure/exception/infrastructure.py` + add to STATUS_MAP in `http_handler.py`

### Data types between layers (ADR-005)
| Layer | Type | Location |
|---|---|---|
| HTTP request/response | Pydantic `BaseModel` | `<context>/infrastructure/http/schema/` |
| DB mapping | SQLAlchemy ORM model | `<context>/infrastructure/model/` |
| Domain | `@dataclass` | `<context>/domain/entity/` |
| JOIN/pass-through | `dict` | returned by query repos |

- Rule: does the use case access fields for logic? → dataclass via `model.to_entity()`. Just passing through? → dict
- `schema/` = HTTP, `entity/` = domain, `model/` = DB — never confuse them

### Repository patterns (ADR-006, ADR-007)
- **Write repo** (`<context>/infrastructure/adapter/persistence/sqlalchemy_*_repository.py`): one table, returns entities via `model.to_entity()`
- **Query repo** (`<context>/infrastructure/adapter/persistence/sqlalchemy_*_query_repository.py`): JOINs allowed (even cross-context models), returns `dict`
- Always decorate repo methods with `@handle_db_errors`
- Use `session.add()` + `session.flush()` for creates (not commit)
- Use `update().returning(Model)` for conditional updates
- Catch `IntegrityError → AlreadyExistsError` when it has business meaning; let decorator handle the rest

### Naming conventions (ADR-016)
| Concept | Pattern | Example |
|---|---|---|
| Port | `<Entity><Action>Port` | `LoanRepositoryPort` |
| Persistence adapter | `SqlAlchemy<Entity>Repository` | `SqlAlchemyLoanRepository` |
| External adapter | `<Provider><Action>Service` | `StpDisburseService` |
| Entity | `<Entity>` | `Loan` |
| Use case | `<Action><Entity>` | `DisburseLoan` |
| Controller | `<Entity>Controller` | `LoanController` |
| Schema | `<Action><Entity>Request/Response` | `DisburseLoanRequest` |
| ORM model | `<Entity>Model` | `LoanModel` |

### Entity rules (ADR-010)
- Entities are `@dataclass` in `<context>/domain/entity/` — pure data + rules about themselves
- Entity can: `ensure_can_*()`, `determine_*()`, import domain exceptions
- Entity cannot: persist itself, call repos/services, know about HTTP or DB
- If a rule is about the entity's own state → put it in the entity, not the use case

### Schema vs Entity (ADR-011)
- `schema/` = Pydantic, HTTP boundary only (request validation + response serialization)
- `entity/` = dataclass, domain only (use case logic + autocomplete)
- Never use Pydantic models inside use cases. Never use entities in HTTP responses directly

### DI wiring (ADR-012)
- All wiring in `dependencies/container.py` — `build_container()` returns a frozen `Container` dataclass
- Singletons stored in `app.state` via lifespan in `app.py`
- Endpoints inject via `Depends()` from `dependencies/providers.py`
- Repos are stateless singletons — no `__init__` with DB/session
- Adding a dependency: wire in `container.py` → add provider in `providers.py` → add router in `app.py`

### Database (ADR-002, ADR-006)
- `Base` (DeclarativeBase) lives in `shared/infrastructure/database/base.py` — all contexts import from there
- One pool/engine/session_factory for the entire app — all bounded contexts share it
- Alembic `env.py` imports `Base` from shared and all models from each context's `infrastructure/model/` to discover tables across bounded contexts

### Code style and typing (ADR-013, ADR-014)
- PEP 8 enforced by Flake8 + isort + black, line length 88
- `mypy --strict`: every function must have type annotations — no implicit `Any`
- `asyncio_mode = "auto"` in pytest — no need for `@pytest.mark.asyncio`

## Checklist: Adding a New Bounded Context

1. Create folders: `<context>/domain/entity/`, `<context>/domain/port/`, `<context>/application/use_case/`, `<context>/infrastructure/adapter/persistence/`, `<context>/infrastructure/model/`, `<context>/infrastructure/http/controller/`, `<context>/infrastructure/http/schema/`, `<context>/infrastructure/http/api/v1/`
2. Add `__init__.py` in each folder
3. Update `migrations/env.py` — import all models from `<context>/infrastructure/model/` so Alembic discovers the new tables

## Checklist: Adding a New Entity (within a bounded context)

1. `<context>/domain/entity/new.py` — `@dataclass` with own rules (if any)
2. `<context>/infrastructure/model/new_model.py` — SQLAlchemy ORM + `to_entity()` method
3. `alembic revision --autogenerate -m "create new table"`
4. `<context>/domain/port/new_repository_port.py` — `typing.Protocol`
5. `<context>/infrastructure/adapter/persistence/sqlalchemy_new_repository.py` — `@handle_db_errors` on every method
6. `<context>/application/use_case/action_new.py` — guards + `transaction_context` + `tx.commit()`
7. `<context>/infrastructure/http/schema/new_schema.py` — Pydantic request/response
8. `<context>/infrastructure/http/controller/new_controller.py` — delegates to use case, zero logic
9. `<context>/infrastructure/http/api/v1/new.py` — `APIRouter` with endpoints
10. `dependencies/container.py` — wire everything
11. `dependencies/providers.py` — add provider function
12. `app.py` — `include_router`
13. `tests/unit/<context>/test_action_new.py` — mock repos, patch `transaction_context`

## Testing Rules (ADR-008)

| Layer | Test type | Mock strategy |
|---|---|---|
| Controller | Unit | `AsyncMock` the use case |
| Use Case | Unit | `AsyncMock` repos/services, `@patch("<context>.application.use_case.x.transaction_context")` |
| Entity | Unit | Nothing — pure methods, no mocks |
| Repository | Integration | Real DB + `session_context` + rollback |
| Service | Integration | `httpx_mock` for HTTP, not DB mocks |

- Never mock `session.execute()` — it only proves the mock is correct, not the query
- Patch `transaction_context` at the use case module level: `@patch("loan.application.use_case.disburse_loan.transaction_context")`
- Use entity fixtures with all fields populated
- Test guards: not found, invalid state, already processed

## Common Mistakes to Avoid

- **try/catch in use cases** — use linear guards (`ensure_*`) instead, let exceptions bubble
- **`session.commit()` in a repo** — repos flush, use cases commit via `transaction_context`
- **HTTP status codes in exceptions** — domain exceptions only have `message`; mapping is in `http_handler.py`
- **Pydantic model in a use case** — use entities (dataclass) inside business logic
- **Sync I/O anywhere** — a single `requests.post()` blocks the entire event loop
- **Importing repo/service directly in use case** — depend on the Protocol (port), inject the concrete via DI
- **JOINs in write repos** — JOINs go in query repos; write repos are single-table CRUD
- **Forgetting `@handle_db_errors`** — every repo method needs it; every service method needs `@handle_external_errors`
- **Forgetting `await tx.commit()`** — transaction is silently lost without it
- **Manually editing `pyproject.toml`** — use `poetry add` / `poetry add --group dev`
- **Importing across bounded contexts at domain/application level** — context A never imports context B's repos, use cases, or entities; use domain services or events (ADR-016)
- **Importing infrastructure from application** — use cases depend on ports (Protocols), never on concrete repos
