# Architecture Decision Records (ADR)

Record of all architectural decisions discussed, with context, options evaluated, justification, and consequences.

**Format:** Each ADR follows the structure: Context → Options → Decision → Justification → Consequences.

---

## Guiding Principles

This is not about Clean Architecture, hexagonal, or DDD. It is about a set of simple principles that guide every decision in this document:

| # | Principle | What it means | ADRs that reflect it |
|---|---|---|---|
| 1 | **Business does not depend on technology** | Exceptions don't know about HTTP. Entities don't know about SQLAlchemy. Use cases don't know about FastAPI. If you change the framework, the domain doesn't notice | 004, 009, 011, 012 |
| 2 | **Code reads top to bottom** | A use case reads as a sequence: linear guards (preconditions that exit if they fail), then the happy path. Zero try/catch in business logic — exceptions bubble up and the handler translates them. Explicit commit, one pattern per problem. PEP 8 style enforced by tooling | 003, 004, 005, 013 |
| 3 | **Dependencies go in one direction** | Controller → Use Case → Port ← Repository. Inner layers never import from outer ones. If an import goes "outward", something is wrong | 009, 012, 016 |
| 4 | **Layers communicate through contracts** | The use case sees a Protocol, not a concrete class. If the implementation changes, the contract holds. Duck typing with static verification. mypy --strict ensures contracts are fulfilled before running | 009, 014 |
| 5 | **Entities know their own rules** | The entity is an expert on itself: it knows if it can be evaluated, if it can be disbursed. It doesn't know how to save itself, it doesn't know how to call providers. That belongs to the system | 010 |
| 6 | **Errors belong to the domain** | `InvalidOperationError`, not `HTTPException(422)`. The domain throws typed exceptions. Each protocol (HTTP, gRPC, CLI) translates them to its own format | 004 |
| 7 | **Decisions are documented and can be challenged** | Every ADR has rejected options with justification. If the context changes, the decision can be reversed with the same transparency | This document |
| 8 | **Discipline sustains everything else** | Patterns only work if the team follows them. A single sync `requests.post()` breaks async. A single try/catch in a use case breaks consistency. A `def f(x):` without types breaks the safety net. Flake8 + isort + black + mypy in CI = automatic enforcement | All |
| 9 | **AI accelerates, humans decide** | AI generates code, proposes ADRs, writes tests. Humans review, challenge, and have the final word. No architectural decision is accepted just because AI suggested it | All |
| 10 | **Complexity is added when it hurts, not before** | CQRS lite instead of event sourcing. Anemic until the entity needs rules. No outbox until eventual consistency requires it. The right abstraction is the one that solves a real problem, not an imaginary one | 007, 010 |

Each ADR is an instance of these principles applied to a concrete problem.

---



## Summary of decisions

| ADR | Decision | Main rejected alternative |
|---|---|---|
| 001 | Full async | Sync with threads |
| 002 | Session context manager + contextvars + Depends | Middleware |
| 003 | transaction_context + explicit commit | Implicit decorator / dual pattern |
| 004 | Hierarchy + decorators + HTTP handler | Try/catch in every layer |
| 005 | Mixed (Pydantic + ORM model + dataclass + dict) | Pydantic everywhere |
| 006 | SQLAlchemy ORM + Alembic autogenerate | Raw asyncpg / SQLAlchemy Core |
| 007 | CQRS Lite (write + query repos) | JOINs in write repos |
| 008 | Unit (controller/UC) + Integration (repo) | All unit tests with mocks |
| 009 | Python Protocols | ABC / No interfaces |
| 010 | Entities as experts on themselves | Permanently anemic / Full rich entities |
| 011 | schema/ (HTTP) + entity/ (domain) | One model for everything |
| 012 | Manual container + app.state + Depends() | DI Container library / wiring in app.py |
| 013 | PEP 8 + Flake8 + isort + black | Ruff (single tool) |
| 014 | mypy --strict (financial project) | No type checking / basic mypy |
| 015 | Poetry (financial project) | pip + requirements.txt / uv |
| 016 | Bounded Context structure (domain/application/infrastructure) | Flat folders / monolithic layers |

---

## ADR-001: Full Async across the entire chain

**Status:** Accepted

**Context:**
FastAPI runs on an async event loop. If any method in the chain (controller → use case → repository → service) is sync and performs I/O, it blocks the entire event loop. No other request gets processed until it finishes.

**Options considered:**

| Option | Description |
|---|---|
| A) Full async | The entire chain is `async/await`. Async libraries at every layer |
| B) Sync with threads | Use `run_in_executor` to wrap sync calls |
| C) Mixed | Async in controller, sync in repos/services |

**Why NOT the others:**
- **B) Sync with threads:** Introduces context switching overhead. Loses the event loop advantages. Each thread consumes ~8MB of stack. Doesn't scale with thousands of concurrent connections.
- **C) Mixed:** Creates confusion about what is async and what is not. A single `requests.post()` in a service blocks everything. The developer has to remember where it's safe to call sync — prone to silent errors.

**Decision:** Option A — Full async.

**Justification:**
- A single event loop handles thousands of concurrent connections with ~KB per coroutine (vs ~MB per thread)
- If you forget `await`, Python throws a `RuntimeWarning` which with `PYTHONWARNINGS=error::RuntimeWarning` becomes an exception — detectable before production
- The team needs to learn a single mental model: if it crosses the process boundary → `await`

**Consequences:**
- (+) Superior performance under concurrent load
- (+) Consistent mental model across the entire app
- (-) Every new dependency must have async support. If it doesn't exist, `asyncio.to_thread()` as a last resort
- (-) Debugging async can be more complex (longer stack traces)
- (-) The team must learn async/await if they don't know it

**Stack chosen:**

| Layer | Async | Sync (rejected) |
|---|---|---|
| HTTP Framework | FastAPI | Flask |
| Database | SQLAlchemy async + asyncpg | psycopg2 |
| HTTP Client | httpx.AsyncClient | requests |
| Redis | redis.asyncio | redis |
| AWS | aioboto3 | boto3 |

---

## ADR-002: Session Pool per Request via Context Manager

**Status:** Accepted

**Context:**
Repositories are stateless singletons. Each HTTP request needs its own DB session to prevent concurrent requests from interfering with each other. We need a mechanism that works for both HTTP (FastAPI) and non-HTTP (workers, scripts, crons).

**Options considered:**

| Option | Description |
|---|---|
| A) Middleware | FastAPI middleware that acquires a session before each request |
| B) Depends + Context Manager | Reusable `session_context` + FastAPI `Depends` as adapter |
| C) Session per query | Each repo method acquires and releases its own session |

**Why NOT the others:**
- **A) Middleware:** Only works for HTTP. Workers, scripts, and crons need a different mechanism. Also, it acquires a session for ALL endpoints — including `/health` which doesn't touch the DB, wasting pool connections.
- **C) Session per query:** Impossible to do transactions that span multiple repos (the UPDATE from one repo and the INSERT from another don't share a session). Also more overhead from acquire/release on each query.

**Decision:** Option B — `session_context` (context manager) + `contextvars` + FastAPI `Depends` as adapter.

**Justification:**
- **A single mechanism** for everything: HTTP uses `Depends(get_db_connection)` which internally calls `session_context`. Workers/scripts call `async with session_context(database)` directly
- **Doesn't waste connections:** Only endpoints that have `Depends` acquire a session
- **Testable:** `app.dependency_overrides` for FastAPI tests, direct `session_context` for integration tests
- **Transactions possible:** All repos in a request see the same session via `contextvars`, enabling atomic transactions

**Consequences:**
- (+) Repos are pure singletons (no `__init__` with DB)
- (+) Workers, scripts, and crons use the same mechanism as HTTP
- (+) Configurable pool (pool_size, max_overflow) based on load
- (-) `contextvars` is implicit — if a developer calls a repo outside a `session_context`, they get a clear `RuntimeError` but at runtime, not at compile time
- (-) The developer must understand that `get_current_session()` returns the current request's session, not a global session

---

## ADR-003: Transactions — Context Manager with explicit commit

**Status:** Accepted

**Context:**
A use case can call multiple repositories. If one fails after another has already inserted data, the DB is left in an inconsistent state. We need atomicity. But not all use cases are equal — some only touch the DB, others call third parties and need the response before deciding what to save.

**Options considered:**

| Option | Description |
|---|---|
| A) Manual transaction | Each use case manages its own `async with conn.transaction()` with begin/commit/rollback |
| B) Single decorator | `@transactional` wraps the entire `execute()` — implicit commit |
| C) Decorator + Context Manager | `@transactional` for simple ones, `transaction_context` for complex ones |
| D) Single Context Manager | `transaction_context` for all, explicit commit always |

**Why NOT the others:**
- **A) Manual transaction:** Repeated boilerplate in every use case. Easy to forget the rollback. The use case gets filled with infrastructure code.
- **B) Single decorator:** Doesn't work for use cases that call third parties (Type 2). If you wrap everything in a transaction and the HTTP call to the third party takes 5 seconds, the connection stays blocked for 5 seconds with a lock on the table. Under load, the pool runs out. Also, the commit is invisible — hidden inside the decorator.
- **C) Decorator + Context Manager:** Works, but introduces two distinct patterns. The developer must choose which to use. The decorator hides the commit — a single explicit pattern is clearer.

**Decision:** Option D — `transaction_context()` with explicit `await tx.commit()` for all use cases.

**Justification:**

A single pattern for all types of use cases:

| Type | Example | Pattern |
|---|---|---|
| Type 1: DB only | RegisterUser, RequestLoan | 1 `transaction_context` block + `tx.commit()` |
| Type 2: DB + external service | EvaluateLoan, DisburseLoan | 2 `transaction_context` blocks, external call between them |
| Type 3: Read only | GetLoanDetail | No transaction |

For Type 2, the pattern is:
1. Transaction 1: mark intermediate status (idempotent) + `tx.commit()`
2. Call to third party (outside transaction)
3. Transaction 2: save result + `tx.commit()`

Example (all types read the same way):
```python
async with transaction_context() as tx:
    await self.loan_repo.update_status(loan_id, "disbursed")
    await tx.commit()
```

**Consequences:**
- (+) A single pattern — the developer doesn't have to choose between mechanisms
- (+) Every commit is visible in the code — zero hidden behavior
- (+) Automatic rollback if an exception occurs before commit (the context manager handles it)
- (+) Intermediate statuses (`scoring`, `disbursing`) + reconciliation = safety net for Type 2
- (-) Slightly more verbose than a decorator for simple use cases (3 extra lines)
- (-) If the developer forgets `await tx.commit()`, the transaction is silently lost

---

## ADR-004: Exception Handling — Hierarchy + Decorators + HTTP Handler

**Status:** Accepted

**Context:**
Without an error strategy, each developer puts try/catch wherever they see fit. DB errors get exposed to the client (`IntegrityError`). Inconsistent responses (`{"error": "..."}` vs `{"message": "..."}` vs stack traces). Use cases and controllers full of try/catch that obscure business logic.

Domain exceptions do not contain HTTP status codes. The mapping from exception to status code lives exclusively in `shared/infrastructure/exception/http_handler.py`. This allows the same exceptions to be used in non-HTTP contexts (SQS consumers, CLI, workers, gRPC) without coupling to HTTP.

**Options considered:**

| Option | Description |
|---|---|
| A) Try/catch in every layer | Each layer catches and re-throws its errors |
| B) Single global handler | One catch-all in FastAPI translates everything |
| C) Hierarchy + Decorators + Handler | Typed exceptions + decorators in repos/services + HTTP handler |

**Why NOT the others:**
- **A) Try/catch in every layer:** Controller has try/catch, use case has try/catch, repo has try/catch. 3 levels of catch for a single error. The code becomes unreadable. If someone forgets a catch, the error bubbles up untranslated.
- **B) Single global handler:** Works, but the handler needs `isinstance` checks to know what type of error it is. If the repo throws `IntegrityError`, the global handler needs to know about SQLAlchemy — direct coupling between the HTTP handler and the DB library.

**Decision:** Option C — Typed hierarchy (without status codes) + Infrastructure decorators + HTTP Handler with `STATUS_MAP`.

**Justification:**
- **`AppException` only has `message`**, no `status_code`. Exceptions are protocol-agnostic
- **`shared/infrastructure/exception/http_handler.py`** uses `DOMAIN_STATUS_MAP` and `INFRA_STATUS_MAP` (dicts) to translate exception type → HTTP status code. Each future protocol (gRPC, CLI, SQS) can have its own handler without touching the exceptions
- **Decorators (`@handle_db_errors`, `@handle_external_errors`)** in `shared/infrastructure/exception/decorators.py` translate library errors to the app's hierarchy. The repo can do a targeted try/catch for errors with business meaning (e.g.: `IntegrityError → AlreadyExistsError`). Everything else → decorator → `DatabaseException`
- **Use cases and controllers:** ZERO try/catch. They only throw guards (`if not entity: raise EntityNotFoundError`). They read like a book
- **HTTP Handler:** Catches by category (`DomainException`, `DatabaseException`, `ExternalServiceException`, `Exception`). One handler per category, zero `isinstance`. The `STATUS_MAP` centralizes the mapping

**Consequences:**
- (+) Clean use cases and controllers — business logic only
- (+) Consistent HTTP responses always
- (+) Exceptions are reusable across any protocol (HTTP, gRPC, CLI, SQS workers)
- (+) Infrastructure errors are never exposed to the client (generic 503 for DB, 502/504 for external)
- (-) The hierarchy must be kept coherent — if someone throws `Exception` directly, it falls to the catch-all (500)
- (-) The decorators catch `AppException` and let it pass through — if someone doesn't understand this, it can be confusing
- (-) Adding a new exception requires two steps: create the class + add it to the HTTP handler's `STATUS_MAP`

---

## ADR-005: Data types between layers — Mixed Approach

**Status:** Accepted

**Context:**
Repositories return data from the DB. Without conversion, everything remains as ORM objects — no separation between infrastructure and domain. But converting EVERYTHING to Pydantic or dataclass has unnecessary cost for data that is just passed through without processing.

**Options considered:**

| Option | Description |
|---|---|
| A) Pydantic everywhere | All data is converted to Pydantic model |
| B) Dict everywhere | Everything stays as Record/dict |
| C) Mixed | Pydantic at HTTP boundaries, dataclass for domain, dict for pass-through |

**Why NOT the others:**
- **A) Pydantic everywhere:** Validation overhead on every conversion. A JOIN that returns 20 columns needs a model with 20 fields just to pass data to the response. Pydantic v2 is fast, but not free — and most of those fields are never accessed in the use case.
- **B) Dict everywhere:** The use case accesses `loan["status"]` — no autocomplete, no types, `loan["statos"]` fails at runtime. For data that the use case needs to manipulate, this is unacceptable.

**Decision:** Option C — Mixed approach.

**Justification:**

| Data | Type | Where it lives | Why |
|---|---|---|---|
| HTTP Request | Pydantic | `<context>/infrastructure/http/schema/` | Automatic input validation |
| ORM Model | SQLAlchemy Model | `<context>/infrastructure/model/` | Table mapping, `to_entity()` for conversion |
| Domain Entity | dataclass | `<context>/domain/entity/` | Autocomplete, types, future logic |
| Pass-through data (JOINs) | dict | — | No unnecessary conversion |
| HTTP Response | Pydantic | `<context>/infrastructure/http/schema/` | Controlled serialization |

**Simple rule:** Does the use case access fields of the data to perform logic? → dataclass (via `model.to_entity()`). Does it just pass it to the response? → dict.

**Consequences:**
- (+) Autocomplete and types where they matter (use cases)
- (+) No overhead for data that is just passed through
- (+) `model.to_entity()` centralizes the Model→Entity conversion in the ORM model
- (-) Two return types in repos (dataclass for write, dict for query) — the developer must know which to use
- (-) `schema/`, `model/` and `entity/` are 3 layers — clear distinction: model=DB, entity=domain, schema=HTTP

---

## ADR-006: SQLAlchemy ORM + Alembic autogenerate

**Status:** Accepted

**Context:**
We need to access PostgreSQL and version schema changes. The decision between ORM and raw queries affects the entire data layer, migrations, and the team's mental model. We want a single source of truth for the DB schema that serves both for queries and for automatic migrations.

**Options considered:**

| Option | Description |
|---|---|
| A) Raw queries with asyncpg | Direct SQL, positional parameters ($1, $2), Alembic with manual `op.execute()` |
| B) SQLAlchemy Core (query builder) | Query builder without ORM, no mapped models |
| C) Full SQLAlchemy ORM | Mapped models, session management, query builder, Alembic autogenerate |

**Why NOT the others:**
- **A) Raw queries with asyncpg:** The schema ends up scattered across 3 places: SQL migrations, queries in repos, and conversions in entities. Each table change requires touching all 3. Without autogenerate, migrations are manual. SQL errors are only detected at runtime.
- **B) SQLAlchemy Core:** Solves the query builder but doesn't give mapped models. Without `to_entity()` on the model, conversion remains scattered. No autogenerate (requires ORM models for that).

**Decision:** Option C — Full SQLAlchemy ORM with mapped models, `async_sessionmaker`, and Alembic autogenerate.

**Justification:**

The `<context>/infrastructure/model/` layer is the **single source of truth** for the schema:

| Aspect | How it works |
|---|---|
| Queries in repos | `select(UserModel).where(UserModel.id == id)` — typed, errors at import |
| Migrations | `alembic revision --autogenerate` from models — detects changes automatically |
| Model→Entity conversion | `model.to_entity()` on the ORM model — centralized |
| Engine + session | `create_async_engine()` + `async_sessionmaker()` with asyncpg as driver |
| Creates | `session.add(model)` + `session.flush()` — flush in repo, commit in use case |
| Conditional updates | `update(LoanModel).where(...).values(...).returning(LoanModel)` — native RETURNING |
| Constraint errors | `sqlalchemy.exc.IntegrityError` → `AlreadyExistsError` in the repo |

**Key design decisions:**

1. **`expire_on_commit=False`** in sessionmaker — without this, accessing attributes after commit throws `MissingGreenlet`
2. **`session.flush()`** in repos (not commit) — the use case controls the commit via `transaction_context`
3. **`server_default=text("gen_random_uuid()")`** for UUIDs — the server generates IDs, not Python
4. **Entities remain as pure dataclasses** — `model/` and `entity/` are separate layers, repos convert model→entity
5. **`update().returning(LoanModel)`** — SQLAlchemy 2.0+ with PostgreSQL supports RETURNING in ORM

**File structure:**

```
shared/infrastructure/database/
└── base.py                              # DeclarativeBase (shared across all contexts)

<context>/infrastructure/model/
├── __init__.py                          # Exports context models
├── user_model.py                        # UserModel + to_entity()
└── loan_model.py                        # LoanModel + to_entity()
```

Alembic `env.py` imports `Base` from `shared/infrastructure/database/base.py` and all models from each context's `infrastructure/model/` to enable autogenerate across bounded contexts.

**Consequences:**
- (+) Single source of truth for the schema: `<context>/infrastructure/model/`
- (+) Autogenerated migrations — detects changes automatically
- (+) Typed queries — column errors are detected at import, not at runtime
- (+) asyncpg remains the driver (SQLAlchemy uses it internally) — same performance
- (-) Extra layer of ORM models (`model/`) in addition to entities (`entity/`)
- (-) The team needs to learn SQLAlchemy 2.0 query syntax
- (-) Session management (flush vs commit, expire_on_commit) has gotchas that need to be documented

---

## ADR-007: CQRS Lite — Separation of read and write repos

**Status:** Accepted

**Context:**
We said "1 repo = 1 table". But when a use case needs data from multiple tables (e.g.: loan + user data), you fall into N+1 queries: 1 query for loans + N queries for each user. 100 loans = 101 queries. The solution is a JOIN, but a JOIN crosses tables — it violates "1 repo = 1 table".

**Options considered:**

| Option | Description |
|---|---|
| A) JOINs in write repos | Allow JOINs in the existing repos |
| B) Separate read repos | `SqlAlchemyLoanRepository` (write, 1 table) + `SqlAlchemyLoanQueryRepository` (read, JOINs) |
| C) Full CQRS | 2 DB pools (primary + replica), event sourcing |

**Why NOT the others:**
- **A) JOINs in write repos:** Mixes responsibilities. A `SqlAlchemyLoanRepository` with CRUD + complex JOINs grows uncontrollably. Doesn't prepare for future scaling.
- **C) Full CQRS:** Requires 2 DB nodes (primary + replica), event sourcing or change data capture, eventual consistency handling. Excessive complexity for the current state. We don't have a DB replica today.

**Decision:** Option B — CQRS lite (separation at the code level).

**Justification:**
- **Today:** Both repos (`SqlAlchemyLoanRepository` and `SqlAlchemyLoanQueryRepository`) use `get_current_session()` and the same pool. The separation is code-level ONLY
- **Future:** The day a DB replica is added:
  1. A second pool pointing to the replica is created
  2. `SqlAlchemyLoanQueryRepository` switches to `get_read_session()`
  3. Use cases and controllers are not touched
- **Clarity:** Write repos are pure CRUD (1 table, easy to understand). Query repos are complex queries (JOINs, aggregations, dashboards)

**Consequences:**
- (+) Eliminates N+1 queries with JOINs in query repos
- (+) Write repos stay simple (1 class = 1 table)
- (+) Ready for DB replica without refactoring
- (+) Use cases declare what type of data they need (write port vs query port)
- (-) More classes (2 repos per entity instead of 1)
- (-) The developer must decide if a new query goes in the write repo or query repo
- (-) Without a real replica, the separation is "cosmetic only" today — the future benefit is speculative

---

## ADR-008: Testing — Unit for logic + Integration for data

**Status:** Accepted

**Context:**
Everything is a singleton. Repos use `get_current_session()` from contextvars. You can't unit test a repo without a real DB because the ORM queries are the logic. But for use cases and controllers, a repo mock is enough.

**Options considered:**

| Option | Description |
|---|---|
| A) All unit tests | Mock session, execute, scalars — prove that "it calls execute with these params" |
| B) All integration tests | Real DB for everything, including use cases and controllers |
| C) Mixed | Unit tests for controller/use case (mocks), integration for repo/service (real DB) |

**Why NOT the others:**
- **A) All unit tests:** Mocking `session.execute()` only proves that you wrote the mock correctly. A typo in a column name passes all unit tests and fails in production. The decorators (`@handle_db_errors`) are never exercised with real errors.
- **B) All integration tests:** Slow. Requires the DB to be running for any test. A test for "if the user doesn't exist, throw an error" doesn't need a DB — it's pure logic. CI becomes slower and more fragile.

**Decision:** Option C — Mixed with combined coverage.

**Justification:**

| Layer | Test type | What it needs |
|---|---|---|
| Controller | Unit | Mock of the use case (constructor injection) |
| Use Case | Unit | Mock of the repo/factory (constructor injection) |
| Repository | Integration | Real DB + `session_context` + rollback |
| Service | Integration | Mock HTTP (`httpx_mock`), not mock DB |
| Decorators | Integration | Real DB (for real SQLAlchemy errors) |

- **Unit tests:** Fast (~ms), no DB. Test business logic: guards, orchestration, delegation
- **Integration tests:** With real DB. Test ORM queries, conversions, constraints, decorators. Fixture with `session_context` + rollback for isolation
- **Combined coverage:** `pytest tests/unit --cov` + `pytest tests/integration --cov --cov-append` + `coverage report`

**Consequences:**
- (+) Unit tests are fast — can be run on every save
- (+) Integration tests test what really matters in repos: the ORM queries
- (+) Combined coverage reflects real code coverage
- (-) You need a test DB (Docker Compose)
- (-) For use cases with `transaction_context`, the context manager is patched in unit tests
- (-) Two test suites = more CI configuration

---

## ADR-009: Interfaces with Python Protocols (typing.Protocol)

**Status:** Accepted

**Context:**
In Clean Architecture, inner layers (use case) must not depend on outer layers (concrete repository). The use case must depend on an abstraction. Python offers several ways to define contracts.

**Options considered:**

| Option | Description |
|---|---|
| A) No interfaces | The use case receives the concrete repo. DI by constructor without abstraction |
| B) ABC (Abstract Base Class) | `class LoanRepoABC(ABC)` with `@abstractmethod`. The repo inherits |
| C) Protocol (duck typing) | `class LoanRepositoryPort(Protocol)`. The repo fulfills it by signature, without inheritance |

**Why NOT the others:**
- **A) No interfaces:** The use case directly imports `LoanRepository`. If you want to change the implementation, you touch the use case. If you want to test, the mock must mimic the concrete class. There is no Dependency Inversion.
- **B) ABC:** Requires inheritance (`class LoanRepository(LoanRepoABC)`). If you add a method to the ABC, ALL concrete repos break until they implement it. More rigid. Python is not Java — mandatory inheritance feels unnatural.

**Decision:** Option C — Python Protocols (structural duck typing).

**Justification:**
- **No inheritance:** `SqlAlchemyLoanRepository` doesn't inherit from anything. It fulfills the Protocol simply by having the same methods with the same signatures
- **Statically verifiable:** `mypy --strict` detects if a repo doesn't fulfill a Protocol before running
- **Pure DI:** `dependencies/container.py` instantiates the concrete and passes it to the use case. The use case only sees the Protocol. If you change the implementation, you only touch `container.py`
- **Pythonic:** Protocols are the Python equivalent of interfaces — duck typing with static verification

**Consequences:**
- (+) Use cases decoupled from concrete implementations
- (+) Trivial tests: any mock that has the same methods fulfills the Protocol
- (+) mypy/pyright detect incompatibilities before runtime
- (-) Without mypy, Protocol errors are invisible — works the same as without interfaces
- (-) One more layer of files (`<context>/domain/port/`) to maintain
- (-) Protocols must be updated when a repo's signature changes

---

## ADR-010: Entity Model — Entities as experts on themselves

**Status:** Accepted

**Context:**
Entities need to encapsulate the business rules that are inherent to themselves. The question is: what logic belongs to the entity and what to the use case?

**Philosophy:** The entity is an expert on itself, not on the system. If the rule "only approved loans can be disbursed" changes, it changes in the entity — not in N use cases. But the entity doesn't know how to save itself, doesn't know how to call providers, doesn't know how to look up other data.

**Options considered:**

| Option | Description |
|---|---|
| A) Full rich entities | Entities handle persistence, transitions, and coordination |
| B) Permanently anemic | Data only, all logic in use cases |
| C) Entities as experts on themselves | The entity encapsulates rules about itself; the use case orchestrates the system |

**Why NOT the others:**
- **A) Full rich entities:** The entity ends up knowing about repos, services, and transactions. Violates Single Responsibility. Makes testing difficult (you need to mock infrastructure inside the entity).
- **B) Permanently anemic:** If `loan.status != "approved"` is validated in 3 different use cases, any change to that rule requires touching all 3. The rule belongs to the entity, not the system.

**Decision:** Option C — Entities as experts on themselves.

**Justification:**

| Responsibility | Where it lives | Example |
|---|---|---|
| Can I be evaluated? | **Entity** | `loan.ensure_can_evaluate()` |
| Can I be disbursed? | **Entity** | `loan.ensure_can_disburse()` |
| What is my result given a score? | **Entity** | `loan.determine_evaluation_status(score, min)` |
| Does it exist in the DB? | **Use case** | `self.ensure_exists(loan, msg)` |
| Did the concurrent update take effect? | **Use case** | `self.ensure_was_updated(result)` |
| In what order do I call repos and services? | **Use case** | transaction orchestration |

- **What goes in the entity:** Validations of own state, transitions, decisions based on its own attributes
- **What does NOT go in the entity:** Persistence, external calls, looking up other data, orchestration
- **User has no methods** because today it has no business rules of its own — if it did, they would be added there
- Example: `loan.ensure_can_disburse()` in the entity vs `self.ensure_approved()` in the use case — the rule belongs to the loan, not the use case

**Consequences:**
- (+) Business rules inherent to the entity live in a single place — DRY
- (+) Use cases read as pure orchestration: find, validate, transact
- (+) Testable: the entity is tested without mocks (it's a dataclass with pure methods)
- (+) Entities grow organically when the domain requires it
- (-) Requires judgment: distinguishing "entity rule" vs "system rule"
- (-) Entities import domain exceptions — acceptable because exceptions are part of the domain

---

## ADR-011: Separation of Schema (HTTP DTOs) vs Entity (Domain)

**Status:** Accepted

**Context:**
Initially we had `schema/` with Pydantic models that served both for HTTP validation and for representing domain entities. This mixed concerns: a `Loan` model had request fields (`provider`), response fields (`id`, `status`), and domain fields (`score`).

**Options considered:**

| Option | Description |
|---|---|
| A) One model for everything | Pydantic model used in HTTP and in use cases |
| B) Separate schema/ and entity/ | schema/ only for HTTP DTOs, entity/ for domain |
| C) Pydantic for everything but separated | Pydantic for HTTP and Pydantic for domain (without dataclass) |

**Why NOT the others:**
- **A) One model for everything:** The model needs optional fields to cover request, response AND domain. `amount: float | None` because the response doesn't always include it, but the domain always has it. Confusion about which fields are required in which context.
- **C) Pydantic for everything:** Pydantic validation has a cost. In the domain we don't need to re-validate data that already comes from the DB. Also, Pydantic models are immutable by default — if the entity needs to mutate (future: rich entities), that's unnecessary friction.

**Decision:** Option B — `<context>/infrastructure/http/schema/` for HTTP DTOs (Pydantic), `<context>/domain/entity/` for domain (dataclass).

**Justification:**
- **schema/ (`<context>/infrastructure/http/schema/`):** Pydantic BaseModel. Only validates requests and serializes responses. Lives at the HTTP boundary
- **entity/ (`<context>/domain/entity/`):** Python dataclass. Pure domain data. Used inside use cases for autocomplete and types. Conversion from DB lives in `model.to_entity()`
- **Clear separation:** HTTP concerns (validation, serialization) don't contaminate the domain. The domain doesn't know about Pydantic or SQLAlchemy

**Consequences:**
- (+) Each layer has its appropriate data type
- (+) Entities can grow into rich entities without Pydantic constraints
- (+) HTTP schemas can change without affecting the domain
- (-) More files (entity/ + schema/ in different layers instead of just schema/)
- (-) Conversion needed: `asdict(entity)` → `Response(**asdict(entity))`. Minimal cost

---

## ADR-012: Dependency Injection — Manual Container + app.state + Depends()

**Status:** Accepted

**Context:**
Each class needs its dependencies (repos, services, factories). We need an injection mechanism that is testable, doesn't couple classes to each other, and scales as the app grows.

**Options considered:**

| Option | Description |
|---|---|
| A) FastAPI Depends for everything | Use `Depends()` to inject repos, use cases, etc. |
| B) Constructor injection + wiring in app.py | Each class receives deps in `__init__`, all wiring in app.py |
| C) DI Container library | python-inject, dependency-injector, etc. |
| D) Manual container + app.state + Depends() | Wiring in `container.py`, singletons in `app.state`, injection via `Depends()` |

**Why NOT the others:**
- **A) FastAPI Depends for everything:** Couples everything to the framework. Use cases shouldn't know about FastAPI. Also, `Depends()` creates instances per request — we want singletons for controllers, use cases, and repos.
- **B) Wiring in app.py:** Works for small apps, but app.py grows linearly with each dependency. Endpoints as closures capture all local variables. Doesn't scale well.
- **C) DI Container library:** Adds a dependency and complexity we don't need. No magic auto-discovery or special decorators.

**Decision:** Option D — Manual container (`dependencies/container.py`) + `app.state` + `Depends()` providers.

**Justification:**

The architecture separates 3 responsibilities:

| Responsibility | File | What it does |
|---|---|---|
| Wiring (building the graph) | `dependencies/container.py` | `build_container(config)` → instantiates everything in order, returns a `Container` frozen dataclass |
| Storage (available singletons) | `app.state` | Lifespan saves controllers and database in `app.state` |
| Injection (endpoints receive deps) | `dependencies/providers.py` | `Depends()` functions that extract from `app.state` |
| Endpoints (HTTP) | `<context>/infrastructure/http/api/v1/*.py` | Module-level `APIRouter`, use `Depends(get_*_controller)` |
| Composition root | `app.py` | `create_app()` — lifespan + exception handlers + include routers |

**Flow:**
1. `create_app(config)` → creates the app with lifespan
2. Lifespan calls `build_container(config)` → builds the entire graph
3. Lifespan saves singletons in `app.state`
4. Endpoints use `Depends(get_user_controller)` → reads from `app.state`

**Testable in 3 ways:**
- **Unit tests:** `UseCase(AsyncMock())` — direct constructor injection
- **Integration tests:** `create_app(test_config)` — full app with test config
- **Targeted override:** `app.dependency_overrides[get_user_controller] = lambda: mock` — replaces a singleton

**Consequences:**
- (+) Zero extra dependencies — everything is native FastAPI
- (+) Trivial tests: `UseCase(AsyncMock())` and done
- (+) Wiring visible in a single file (`container.py`), app.py stays thin (~58 lines)
- (+) Module-level endpoints (not closures), decoupled from the factory
- (+) Adding a dependency = lines in `container.py` + provider function + `include_router`
- (+) `create_app(config)` allows multiple instances with different config
- (-) No auto-wiring: adding a new domain requires touching `container.py`, `providers.py`, and adding a router
- (-) `app.state` is not typed — attribute errors are only detected at runtime

---

## ADR-013: Code style — PEP 8 + Flake8 + isort + black

**Status:** Accepted

**Context:**
Without a style standard, each developer writes differently: tabs vs spaces, unordered imports, 200-character lines. Code reviews fill up with cosmetic comments instead of discussing logic. We need an automated standard that the team doesn't have to memorize.

**Options considered:**

| Option | Description |
|---|---|
| A) No linter | Each developer follows PEP 8 "by eye", corrected in code review |
| B) Flake8 + isort + black | Classic stack: linting, import sorting, and formatting |
| C) Ruff | A single linter/formatter that replaces flake8, isort, black, pyflakes, pycodestyle |

**Why NOT the others:**
- **A) No linter:** Code reviews become style discussions. "Put a space here", "that line is too long". Unproductive and subjective.
- **C) Ruff:** Single tool, but younger ecosystem. Less battle-tested in enterprise. Flake8 + isort + black is the proven standard with broader plugin ecosystem and team familiarity.

**Decision:** Option B — PEP 8 as standard, enforced by Flake8 (linting) + isort (import sorting) + black (formatting).

**Justification:**
- **PEP 8** is the de facto Python standard. We don't invent our own rules
- **Flake8** detects style errors, unused imports, undefined variables. Extensible via plugins (`flake8-async` for async rules)
- **isort** sorts imports automatically — no manual ordering. Compatible with black via `profile = "black"`
- **black** reformats code deterministically — zero style debates. "Any color you like, as long as it's black"
- **All three** can run in pre-commit, in CI, and on every editor save
- **Line length 88** (black default) — balance between readability and screen utilization
- **Config** centralized in `pyproject.toml` for all three tools

**Rules enabled (Flake8):**

| Code | What it covers |
|---|---|
| `E` | PEP 8 style errors (indentation, whitespace, line length) |
| `W` | PEP 8 warnings |
| `F` | Pyflakes (unused imports, undefined variables, shadowing) |
| `ASYNC` | Async-specific rules via flake8-async (missing await, blocking calls) |

**Consequences:**
- (+) Zero style discussions in code reviews
- (+) Battle-tested tools with broad ecosystem and plugin support
- (+) Deterministic formatting with black — same input always produces same output
- (+) isort + black compatible via `profile = "black"` — no conflicts
- (-) Three tools to install and configure instead of one
- (-) Slightly slower than Ruff — but fast enough for pre-commit and CI
- (-) Line length 88 can feel short for long ORM queries — solved with line breaks, not by disabling the rule

---

## ADR-014: Strict typing — mypy --strict (financial project)

**Status:** Accepted

**Scope:** This ADR is specific to this project. The strict typing decision is justified by the financial context of the system. Other projects may opt for gradual typing.

**Context:**
This is a financial system that handles loans, amounts, scores, and statuses. An `amount` that arrives as `str` instead of `float` is a bug that can approve a loan that should be rejected. A `score` that is `None` when `int` is expected is a silent error that changes a financial decision. In a generic CRUD system, gradual typing is acceptable. In a financial system, a type error can have real monetary impact.

**Options considered:**

| Option | Description |
|---|---|
| A) No type checking | Optional type hints, documentation only. No static verification |
| B) Basic mypy | `mypy .` without strict flags. Verifies what it can, ignores what's missing |
| C) mypy --strict | All functions typed, no implicit `Any`, no ignored untyped imports |

**Why NOT the others:**
- **A) No type checking:** `loan.amount` could be `str`, `float`, `None`, or `Decimal` — depending on who sets it. In a financial system, this is unacceptable. A test can pass with `amount=1000` but fail in production with `amount="1000"` — and the error is discovered when money has already been disbursed.
- **B) Basic mypy:** Verifies partially. A function without type hints passes without error. The developer can "escape" the type system simply by not adding hints. Creates false confidence — "mypy passes" but didn't verify the critical functions.

**Decision:** Option C — `mypy --strict` in CI. Every parameter, return, and variable explicitly typed.

**Justification:**
- **`--strict` includes:** `--disallow-untyped-defs`, `--disallow-any-generics`, `--warn-return-any`, `--no-implicit-optional`, among others
- **Errors at import, not at runtime:** `loan.amount + "10"` is detected before running. Not in production at 3am
- **Protocols (ADR-009) benefit directly:** mypy verifies that the implementation fulfills the Protocol statically
- **Complements Pydantic (ADR-011):** Pydantic validates at runtime (HTTP boundaries). mypy validates at development time (all internal code)

**What it means for the developer:**
```python
# This does NOT pass mypy --strict
def calculate_fee(amount, rate):
    return amount * rate

# This DOES pass
def calculate_fee(amount: float, rate: float) -> float:
    return amount * rate
```

**Consequences:**
- (+) Type errors detected before commit — not in production
- (+) Superior autocomplete in IDEs — everything is typed
- (+) Implicit documentation — the signature says what it expects and what it returns
- (+) Financial protection — a `None` where `float` is expected never reaches money calculations
- (-) More verbose — every function needs hints, including internal helpers
- (-) Libraries without stubs require `type: ignore` or custom stubs
- (-) Learning curve with generics, Protocols, and overloads
- (-) Slower CI (~seconds extra for `mypy --strict`)

---

## ADR-015: Dependency management — Poetry (financial project)

**Status:** Accepted

**Scope:** This ADR is specific to this project. The choice of Poetry over pip is justified by the financial context of the system, where exact build reproducibility is a requirement, not a preference.

**Context:**
A financial system that disburses loans cannot have different behavior between what the developer tested and what runs in production. If `httpx==0.28.0` was tested locally but `httpx==0.28.1` gets installed in production (because there was no lock file), a behavior change in the library can alter a response from a disbursement provider. In a generic CRUD, this is a minor bug. Here it can mean real money incorrectly disbursed.

**Options considered:**

| Option | Description |
|---|---|
| A) pip + requirements.txt | `pip freeze > requirements.txt`. Manual lock. No dependency groups |
| B) pip-tools | `pip-compile` generates `requirements.txt` from `requirements.in`. Deterministic lock |
| C) Poetry | `pyproject.toml` for declaration + `poetry.lock` for lock. Dev/prod groups. Dependency resolver |
| D) uv | New Rust-based package manager. Fast, pip-compatible. Own lock file |

**Why NOT the others:**
- **A) pip + requirements.txt:** `pip freeze` captures EVERYTHING in the environment — including transitive dependencies mixed with direct ones. Doesn't distinguish dev from prod (`pytest` gets installed in production). No conflict resolver: if two packages require incompatible versions of a third, `pip install` installs them anyway and fails at runtime.
- **B) pip-tools:** Solves the lock, but maintains the `requirements.txt` model. Two files (`requirements.in` + `requirements.txt`) instead of the standard `pyproject.toml`. No native groups — you need a separate `requirements-dev.in`.
- **D) uv:** Promising and fast, but young ecosystem. Lower adoption in enterprise teams. Installation speed isn't the bottleneck for this project — resolver reliability is.

**Decision:** Option C (Poetry) — `pyproject.toml` + `poetry.lock`.

**Justification:**

| Aspect | How Poetry solves it |
|---|---|
| Deterministic lock | `poetry.lock` pins ALL versions (direct + transitive). `poetry install` installs exactly what was tested |
| Dev/prod separation | `[tool.poetry.group.dev.dependencies]` — `pytest`, `flake8`, `isort`, `black`, `mypy` never reach the production image |
| Conflict resolver | If `fastapi` requires `pydantic>=2.0` and another package requires `pydantic<2.0`, Poetry fails at resolution — not at runtime |
| PEP standard | `pyproject.toml` is the standard (PEP 621). Config for ruff, pytest, mypy — all in a single file |
| Reproducibility | `poetry install --no-dev` in Docker = exactly what was tested in CI |

**Usage rules:**
- `poetry.lock` is **always committed** — it is the reproducibility guarantee
- `poetry add <pkg>` to add dependencies (never manually edit `pyproject.toml` and run `poetry lock`)
- `poetry add --group dev <pkg>` for development dependencies
- In Docker: `poetry install --only main --no-interaction` — no dev deps, no prompts

**Consequences:**
- (+) Reproducible build — what passes CI is exactly what runs in production
- (+) Version conflicts detected when adding dependencies, not when deploying
- (+) A single configuration file (`pyproject.toml`) for the entire toolchain
- (+) Clean dev/prod separation — lighter and more secure production image
- (-) Poetry is slower than pip/uv for installation (~seconds extra in CI)
- (-) The team needs to learn Poetry commands (`poetry add`, `poetry lock`, `poetry shell`)
- (-) Dependency resolution can be slow with many packages — mitigable with `--no-update` in CI

---

## ADR-016: Bounded Context Structure — domain / application / infrastructure

**Status:** Accepted

**Context:**
As the microservice grows, a flat folder structure (`entity/`, `use_case/`, `repository/`, `service/`, etc.) mixes all domains together. A loan entity, a payment entity, and a user entity all live in the same `entity/` folder. When the team needs to understand "everything about loans", they have to hunt across 10+ top-level folders. Adding a second bounded context (e.g., payments) makes the flat structure unsustainable — files from different contexts interleave.

We need a structure that:
1. Groups code by business domain (bounded context), not by technical layer
2. Maintains strict dependency direction within each context
3. Supports multiple bounded contexts in a single microservice
4. Shares cross-cutting infrastructure (database connection, base exceptions) without duplication

**Options considered:**

| Option | Description |
|---|---|
| A) Flat folders | Current: `entity/`, `use_case/`, `repository/` — all domains mixed |
| B) Monolithic layers | `domain/`, `application/`, `infrastructure/` at root — one set of layers, all domains inside |
| C) Bounded contexts with 3 layers | `loan/domain/`, `loan/application/`, `loan/infrastructure/` — each context owns its layers + `shared/` kernel |

**Why NOT the others:**
- **A) Flat folders:** Works for a single small domain but doesn't scale. Adding payments means `entity/loan.py` and `entity/payment.py` in the same folder. No clear boundary between contexts. Imports between contexts are invisible — any file can import any other.
- **B) Monolithic layers:** Better separation by layer but still mixes domains. `domain/entity/loan.py` and `domain/entity/payment.py` share the same folder. Doesn't enforce boundaries between contexts. A payment use case can silently import a loan repository port.

**Decision:** Option C — Bounded contexts with 3 layers each + shared kernel.

**Justification:**

Each bounded context follows the same internal structure:

```
<context>/
├── domain/           # Pure business: entities, ports, domain exceptions
│   ├── entity/       # @dataclass with own rules
│   ├── port/         # typing.Protocol contracts
│   └── exception/    # Context-specific domain exceptions (if needed)
│
├── application/      # Orchestration: use cases, factories
│   ├── use_case/     # 1 class = 1 operation
│   └── factory/      # Strategy selection
│
└── infrastructure/   # Everything external: DB, HTTP, frameworks
    ├── adapter/
    │   ├── persistence/   # SqlAlchemy*Repository implementations
    │   └── external/      # HTTP service integrations
    ├── model/             # SQLAlchemy ORM models
    ├── http/
    │   ├── controller/    # Presentation: receive, delegate, return
    │   ├── schema/        # Pydantic request/response DTOs
    │   └── api/v1/        # APIRouter endpoints
```

**Full project structure:**

```
template/
├── app.py                          # Composition root: create_app() + lifespan
├── config/settings.py              # pydantic-settings with env_prefix
│
├── loan/                           # ← Bounded Context
│   ├── domain/
│   │   ├── entity/loan.py          # Loan dataclass
│   │   ├── entity/result.py        # Result dataclass
│   │   ├── port/loan_repository_port.py
│   │   ├── port/loan_query_repository_port.py
│   │   └── port/disburse_provider_port.py
│   ├── application/
│   │   ├── use_case/request_loan.py
│   │   ├── use_case/evaluate_loan.py
│   │   ├── use_case/disburse_loan.py
│   │   ├── use_case/get_loan_detail.py
│   │   └── factory/disburse_provider_factory.py
│   └── infrastructure/
│       ├── adapter/persistence/sqlalchemy_loan_repository.py
│       ├── adapter/persistence/sqlalchemy_loan_query_repository.py
│       ├── adapter/external/stp_disburse_service.py
│       ├── adapter/external/nvio_disburse_service.py
│       ├── model/loan_model.py
│       ├── http/controller/loan_controller.py
│       ├── http/schema/loan_schema.py
│       └── http/api/v1/loans.py
│
├── shared/                         # ← Shared Kernel
│   ├── domain/
│   │   ├── entity/                 # Cross-domain value objects (Money, etc.)
│   │   └── exception/
│   │       ├── base.py             # AppException(message)
│   │       └── domain.py           # DomainException hierarchy
│   └── infrastructure/
│       ├── database/
│       │   ├── base.py             # DeclarativeBase (shared across all contexts)
│       │   ├── connection.py       # Database: engine + session_factory
│       │   ├── context.py          # session_context + get_current_session
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
├── pyproject.toml
└── tests/
    ├── unit/
    │   └── loan/                   # Mirrors bounded context structure
    └── integration/
        └── loan/
```

**Naming conventions:**

| Concept | Name pattern | Example | Location |
|---|---|---|---|
| Port (contract) | `<Entity><Action>Port` | `LoanRepositoryPort` | `<context>/domain/port/` |
| Persistence adapter | `SqlAlchemy<Entity>Repository` | `SqlAlchemyLoanRepository` | `<context>/infrastructure/adapter/persistence/` |
| External adapter | `<Provider><Action>Service` | `StpDisburseService` | `<context>/infrastructure/adapter/external/` |
| Entity | `<Entity>` | `Loan` | `<context>/domain/entity/` |
| Use case | `<Action><Entity>` | `DisburseLoan` | `<context>/application/use_case/` |
| Controller | `<Entity>Controller` | `LoanController` | `<context>/infrastructure/http/controller/` |
| Schema | `<Action><Entity>Request/Response` | `DisburseLoanRequest` | `<context>/infrastructure/http/schema/` |
| ORM model | `<Entity>Model` | `LoanModel` | `<context>/infrastructure/model/` |

**Dependency direction within a bounded context:**

```
infrastructure/ ──► application/ ──► domain/
                                      │
                              Entity + Port + Exception
                              (depend on nothing external)
```

- `domain/` never imports from `application/` or `infrastructure/`
- `application/` never imports from `infrastructure/` — depends on ports (Protocols)
- `infrastructure/` implements ports, imports entities for conversion

**Shared kernel rules:**

- `shared/` contains infrastructure used by ALL contexts: database connection/session/transaction, base exception hierarchy, error decorators, HTTP handler
- Every bounded context imports from `shared/` — never the reverse
- `shared/` never imports from any bounded context
- Cross-domain value objects (e.g., `Money`) live in `shared/domain/entity/`
- Database is ONE pool/engine/session_factory — contexts share the connection, each has its own models and repos

**Inter-context communication rules:**

- A bounded context NEVER directly imports another context's repository or use case
- If context A needs data from context B: context B exposes a domain service (sync) or domain event (async)
- Domain services live in the providing context's `application/` layer
- Start simple (direct service call), add events when async decoupling is needed

**Import examples:**

```python
# loan/infrastructure/adapter/persistence/sqlalchemy_loan_repository.py
from shared.infrastructure.database.context import get_current_session
from shared.infrastructure.exception.decorators import handle_db_errors
from loan.domain.entity.loan import Loan
from loan.infrastructure.model.loan_model import LoanModel

# loan/application/use_case/disburse_loan.py
from shared.infrastructure.database.transaction import transaction_context
from loan.domain.port.loan_repository_port import LoanRepositoryPort
from loan.domain.port.disburse_provider_port import DisburseProviderPort

# loan/infrastructure/http/controller/loan_controller.py
from loan.infrastructure.http.schema.loan_schema import DisburseLoanRequest, DisburseLoanResponse
```

**Consequences:**
- (+) Clear boundaries: "everything about loans" is in `loan/`
- (+) Adding a new bounded context = creating a new top-level folder with the same 3-layer structure
- (+) Dependency violations between contexts are visible in imports
- (+) Each context can evolve independently — different complexity levels per context
- (+) Shared infrastructure avoids duplication of database/exception boilerplate
- (+) Naming conventions make adapter technology explicit (`SqlAlchemy*`, `Stp*`)
- (-) Deeper folder nesting than flat structure
- (-) More `__init__.py` files to maintain
- (-) Moving from flat to bounded context requires a migration of all imports
- (-) Small contexts (e.g., a simple CRUD with 1 entity) may feel over-structured — acceptable trade-off for consistency

---
