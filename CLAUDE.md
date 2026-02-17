# CLAUDE.md — Loan Service (FastAPI + Clean Architecture)

FastAPI microservice for loan management. Clean architecture with strict layer separation. See `ADR.md` for justification, `ARCHITECTURE_PLAN.md` for detailed patterns.

## Commands

```bash
poetry run uvicorn app:app --reload          # Run dev server
poetry run pytest tests/unit/ -v             # Unit tests (no DB)
poetry run pytest tests/integration/ -v      # Integration tests (requires DB)
poetry run ruff check .                      # Lint (PEP 8 + async rules)
poetry run mypy .                            # Strict type checking
alembic revision --autogenerate -m "desc"    # Generate migration from model/
alembic upgrade head                         # Apply migrations
poetry add <pkg>                             # Add dependency (never edit pyproject.toml manually)
```

## Architecture Rules

### Dependency direction (ADR-009, ADR-012)
```
Controller → Use Case → Port (Protocol) ← Repository/Service
```
- Inner layers (`entity/`, `port/`) never import from outer layers
- Use cases never import FastAPI, SQLAlchemy, or httpx
- If an import goes "outward", something is wrong

### Full async everywhere (ADR-001)
- Every function in the chain must be `async def` + `await`
- Use `httpx.AsyncClient`, never `requests`. Use `asyncpg`, never `psycopg2`
- If a library has no async support, use `asyncio.to_thread()` as last resort

### Session and transactions (ADR-002, ADR-003)
- Repos get sessions via `get_current_session()` from `database/context.py` — never accept session as parameter
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
- Domain exceptions (`exception/domain.py`) have no HTTP status codes
- Repos use `@handle_db_errors` decorator (`exception/decorators.py`)
- Services use `@handle_external_errors` decorator
- HTTP mapping lives only in `exception/http_handler.py` via `DOMAIN_STATUS_MAP` / `INFRA_STATUS_MAP`
- New exception = create class in `exception/domain.py` or `exception/infrastructure.py` + add to STATUS_MAP in `exception/http_handler.py`

### Data types between layers (ADR-005)
| Layer | Type | Location |
|---|---|---|
| HTTP request/response | Pydantic `BaseModel` | `schema/` |
| DB mapping | SQLAlchemy ORM model | `model/` |
| Domain | `@dataclass` | `entity/` |
| JOIN/pass-through | `dict` | returned by query repos |

- Rule: does the use case access fields for logic? → dataclass via `model.to_entity()`. Just passing through? → dict
- `schema/` = HTTP, `entity/` = domain, `model/` = DB — never confuse them

### Repository patterns (ADR-006, ADR-007)
- **Write repo** (`repository/loan_repository.py`): one table, returns entities via `model.to_entity()`
- **Query repo** (`repository/loan_query_repository.py`): JOINs allowed, returns `dict`
- Always decorate repo methods with `@handle_db_errors`
- Use `session.add()` + `session.flush()` for creates (not commit)
- Use `update().returning(Model)` for conditional updates
- Catch `IntegrityError → AlreadyExistsError` when it has business meaning; let decorator handle the rest

### Entity rules (ADR-010)
- Entities are `@dataclass` in `entity/` — pure data + rules about themselves
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
- PEP 8 enforced by Ruff: `select = ["E", "W", "F", "ASYNC"]`, line length 88
- `mypy --strict`: every function must have type annotations — no implicit `Any`
- `asyncio_mode = "auto"` in pytest — no need for `@pytest.mark.asyncio`

## Checklist: Adding a New Domain

1. `entity/new.py` — `@dataclass` with own rules (if any)
2. `model/new_model.py` — SQLAlchemy ORM + `to_entity()` method
3. `alembic revision --autogenerate -m "create new table"`
4. `port/new_repository_port.py` — `typing.Protocol`
5. `repository/new_repository.py` — `@handle_db_errors` on every method
6. `use_case/action_new.py` — guards + `transaction_context` + `tx.commit()`
7. `schema/new_schema.py` — Pydantic request/response
8. `controller/new_controller.py` — delegates to use case, zero logic
9. `api/v1/new.py` — `APIRouter` with endpoints
10. `dependencies/container.py` — wire everything
11. `dependencies/providers.py` — add provider function
12. `app.py` — `include_router`
13. `tests/unit/test_action_new.py` — mock repos, patch `transaction_context`

## Testing Rules (ADR-008)

| Layer | Test type | Mock strategy |
|---|---|---|
| Controller | Unit | `AsyncMock` the use case |
| Use Case | Unit | `AsyncMock` repos/services, `@patch("use_case.x.transaction_context")` |
| Entity | Unit | Nothing — pure methods, no mocks |
| Repository | Integration | Real DB + `session_context` + rollback |
| Service | Integration | `httpx_mock` for HTTP, not DB mocks |

- Never mock `session.execute()` — it only proves the mock is correct, not the query
- Patch `transaction_context` at the use case module level: `@patch("use_case.disburse_loan.transaction_context")`
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
