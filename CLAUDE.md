# CLAUDE.md — Loan Service (FastAPI + Clean Architecture)

FastAPI microservice for loan management. Clean architecture with bounded contexts and strict layer separation. See `ADR.md` for justification, `ARCHITECTURE_PLAN.md` for detailed patterns.

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
loan/                           # ← Bounded Context
├── domain/                     # Pure business: entities, ports, exceptions
│   ├── entity/
│   ├── port/
│   └── exception/
├── application/                # Orchestration: use cases, factories
│   ├── use_case/
│   └── factory/
└── infrastructure/             # Everything external: DB, HTTP, frameworks
    ├── adapter/persistence/    # SqlAlchemy*Repository
    ├── adapter/external/       # Provider services (Stp*, Nvio*)
    ├── model/                  # SQLAlchemy ORM
    └── http/
        ├── controller/
        ├── schema/
        └── api/v1/

shared/                         # ← Shared Kernel
├── domain/exception/           # AppException, DomainException hierarchy
└── infrastructure/
    ├── database/               # base (DeclarativeBase), connection, context, transaction, dependencies
    └── exception/              # infrastructure exceptions, decorators, http_handler
```

### Dependency direction (ADR-009, ADR-012, ADR-016)
```
infrastructure/ ──► application/ ──► domain/
```
- `domain/` never imports from `application/` or `infrastructure/`
- `application/` never imports from `infrastructure/` — depends on ports (Protocols)
- Use cases import `transaction_context` from `shared.infrastructure.database.transaction`
- A bounded context NEVER imports from another bounded context directly
- `shared/` never imports from any bounded context

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
- **Query repo** (`<context>/infrastructure/adapter/persistence/sqlalchemy_*_query_repository.py`): JOINs allowed, returns `dict`
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

### Code style and typing (ADR-013, ADR-014)
- PEP 8 enforced by Flake8 + isort + black, line length 88
- `mypy --strict`: every function must have type annotations — no implicit `Any`
- `asyncio_mode = "auto"` in pytest — no need for `@pytest.mark.asyncio`

## Checklist: Adding a New Domain (within a bounded context)

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
- **Importing across bounded contexts** — context A never imports context B's repos/use cases; use domain services or events
- **Importing infrastructure from application** — use cases depend on ports (Protocols), never on concrete repos
