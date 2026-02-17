# Clean Architecture Template — Showcase

## En qué se basa

Esta arquitectura implementa **Clean Architecture** adaptada a Python y FastAPI, con decisiones pragmáticas documentadas en 12 ADRs. Se inspira en los principios de Robert C. Martin (Uncle Bob) pero rechaza el dogma: adopta lo que agrega valor al contexto actual y descarta lo que introduce complejidad prematura.

**Filosofía:** El código se lee como un libro. Use cases y controllers son cero try/catch — solo lógica de negocio. La infraestructura está aislada detrás de Protocols (interfaces) y decorators.

---

## Stack tecnológico

| Capa | Tecnología | Por qué |
|---|---|---|
| Framework HTTP | FastAPI | Async nativo, OpenAPI automático, `Depends()` para DI |
| Base de datos | asyncpg (raw SQL) | Driver PostgreSQL más rápido en Python, control total del SQL |
| HTTP Client | httpx.AsyncClient | Async, pool de conexiones, API moderna |
| Validación HTTP | Pydantic v2 | Solo en fronteras HTTP (request/response) |
| Entidades | dataclass | Ligeras, sin overhead de validación, mutables para futuro |
| Migraciones | Alembic + raw SQL | Versionamiento sin ORM, SQL escrito a mano |
| Settings | pydantic-settings | Variables de entorno tipadas con prefijo `LOAN_` |
| Tests | pytest + pytest-asyncio | Unit (mocks) + Integration (BD real) |

---

## Estructura del proyecto

```
app.py                          Composition root (58 líneas)

api/v1/
  users.py                      Endpoints de usuarios
  loans.py                      Endpoints de préstamos

dependencies/
  container.py                  Wiring completo del grafo de dependencias
  providers.py                  Funciones Depends() para inyección en endpoints

controller/                     Capa 1 — Traduce HTTP → Use Case → HTTP
use_case/                       Capa 2 — Lógica de negocio pura
repository/                     Capa 3a — Acceso a datos (raw SQL)
service/                        Capa 3b — Integraciones externas (HTTP)

entity/                         Capa 0 — Modelos de dominio (dataclass)
port/                           Contratos — Python Protocols (interfaces)
schema/                         DTOs HTTP — Pydantic (request/response)
factory/                        Selección de implementación en runtime
exception/                      Jerarquía tipada + decorators + handlers

database/
  connection.py                 Pool de conexiones asyncpg
  context.py                    ContextVar — 1 conexión por request
  transaction.py                @transactional + transaction_context()
  dependencies.py               Adapter FastAPI Depends → connection_context

config/settings.py              Variables de entorno con pydantic-settings
migrations/                     Alembic con SQL puro
```

---

## Características principales

### 1. Full Async en toda la cadena

Toda la cadena es `async/await` — desde el endpoint hasta la query SQL y la llamada HTTP externa. No hay bloqueo del event loop en ningún punto.

```
Endpoint → Controller → Use Case → Repository (asyncpg)
                                 → Service (httpx.AsyncClient)
```

Un solo event loop maneja miles de requests concurrentes con ~KB por coroutine (vs ~MB por thread).

### 2. Dependency Injection manual con Container

Sin librerías de DI. El wiring completo vive en `dependencies/container.py` — una función que construye todo el grafo de dependencias en orden y retorna un `Container` frozen dataclass.

```python
@dataclass(frozen=True)
class Container:
    database: Database
    http_client: httpx.AsyncClient
    user_controller: UserController
    loan_controller: LoanController

def build_container(config: Settings) -> Container:
    # Infrastructure → Repositories → Services → Factories → Use Cases → Controllers
    ...
    return Container(database=..., http_client=..., user_controller=..., loan_controller=...)
```

Los singletons viven en `app.state`. Los endpoints los reciben via `Depends()`:

```python
@router.post("/users")
async def register(body: RegisterUserRequest, ctrl: UserController = Depends(get_user_controller)):
    return await ctrl.register(body)
```

**Testeable:** `app.dependency_overrides[get_user_controller] = lambda: mock_controller`

### 3. Interfaces con Python Protocols (duck typing)

Los use cases dependen de Protocols, no de clases concretas. Sin herencia, sin ABCs.

```python
# port/loan_repository_port.py
class LoanRepositoryPort(Protocol):
    async def get_by_id(self, loan_id: str) -> Loan | None: ...
    async def create(self, user_id: str, amount: float) -> Loan: ...

# use_case/request_loan.py — no importa LoanRepository, solo el Protocol
class RequestLoan:
    def __init__(self, user_repo: UserRepositoryPort, loan_repo: LoanRepositoryPort): ...
```

`mypy --strict` verifica que las implementaciones cumplan los Protocols sin necesidad de herencia.

### 4. Transacciones con commit explícito

Un solo patrón para todos los use cases: `transaction_context()` + `await tx.commit()`.

| Tipo de Use Case | Patrón | Commit |
|---|---|---|
| Solo BD (RegisterUser, RequestLoan) | 1 bloque `transaction_context` | `await tx.commit()` al final |
| BD + servicio externo (EvaluateLoan, DisburseLoan) | 2 bloques, llamada externa entre ellos | `await tx.commit()` en cada bloque |
| Solo lectura (GetLoanDetail) | Sin transacción | N/A |

El patrón para operaciones con servicios externos evita mantener transacciones abiertas durante llamadas HTTP:

```python
# Transaction 1: marcar estado intermedio
async with transaction_context() as tx:
    await self.loan_repo.update_status_if(loan_id, "pending", "scoring")
    await tx.commit()

# Llamada externa (fuera de transacción — puede tardar segundos)
score = await self.score_provider.get_score(loan)

# Transaction 2: guardar resultado
async with transaction_context() as tx:
    result = await self.loan_repo.save_evaluation(loan_id, score, new_status)
    await tx.commit()
```

### 5. Exception handling: jerarquía + decorators + handlers

Cero try/catch en use cases y controllers. La cadena es:

```
Repo/Service                Use Case              FastAPI Handler
@handle_db_errors    →      raise EntityNotFound   →  domain_handler → 404
@handle_external_errors →   raise InvalidOp        →  domain_handler → 422
asyncpg error        →      DatabaseException(503) →  database_handler → 503
httpx timeout        →      ProviderTimeout(504)   →  external_handler → 504
cualquier otra       →      Exception              →  catch_all → 500
```

Los decorators en repos/services traducen errores de librerías a la jerarquía de la app. Los use cases solo lanzan guardas: `if not entity: raise EntityNotFoundError`.

### 6. Conexión por request con ContextVars

Un pool de conexiones singleton. Cada request adquiere una conexión del pool via `Depends()`, la almacena en un `ContextVar`, y todos los repos del mismo request la comparten automáticamente.

```
Request llega → Depends(get_db_connection) → pool.acquire() → ContextVar
                                                                  ↓
                UserRepo.create() ← get_current_connection() ←────┘
                LoanRepo.create() ← get_current_connection() ←────┘
                                                                  ↓
Request termina → pool.release() ← ContextVar.reset()
```

Esto permite transacciones atómicas que cruzan múltiples repos y funciona tanto para HTTP (via Depends) como para workers/scripts (via `async with connection_context(database)`).

### 7. CQRS Lite

Repos de escritura separados de repos de lectura:

- `LoanRepository` — CRUD, 1 tabla, retorna `Loan` (dataclass)
- `LoanQueryRepository` — JOINs, múltiples tablas, retorna `dict`

Hoy ambos usan el mismo pool. El día que haya una réplica de lectura, solo cambia la conexión del query repo — sin tocar use cases ni controllers.

### 8. Factory + Strategy para eliminación de if/else

La selección de proveedor de dispersión no es un if/else en el use case:

```python
# container.py — registro
disburse_factory = DisburseProviderFactory({"stp": stp_service, "nvio": nvio_service})

# use_case — selección
provider = self.factory.get(provider_name)  # → StpDisburseService o NvioDisburseService
result = await provider.execute(loan)
```

Nuevo proveedor = 1 clase + 1 línea en container. El use case no cambia.

### 9. Application Factory con Lifespan

`create_app(config)` permite crear instancias de la app con diferentes configuraciones:

```python
def create_app(config: Settings = settings) -> FastAPI:
    # Lifespan: build container → connect DB → wire app.state → yield → cleanup
    ...
app = create_app()  # uvicorn app:app
```

Sin side effects al importar. Sin globals mutables. Sin `@app.on_event` deprecado.

---

## Tipos de dato entre capas

| Frontera | Tipo | Ejemplo |
|---|---|---|
| Request HTTP → Controller | Pydantic BaseModel | `RegisterUserRequest` |
| Controller → Use Case | Primitivos | `email: str, name: str` |
| Use Case ↔ Repository | dataclass / dict | `Loan` (write) / `dict` (query) |
| Repository ↔ asyncpg | Record → dataclass/dict | `Loan.from_record(record)` |
| Controller → Response HTTP | Pydantic BaseModel | `UserResponse` |

**Regla:** Si el use case accede a campos para hacer lógica → dataclass. Si solo pasa datos al response → dict.

---

## Flujo completo de un request

```
POST /loans/{id}/disburse  {"provider": "stp"}
        │
        ▼
   FastAPI Router (api/v1/loans.py)
        │  Depends(get_db_connection)  →  acquire connection → ContextVar
        │  Depends(get_loan_controller) →  app.state.loan_controller
        │
        ▼
   LoanController.disburse(loan_id, body)
        │  body.provider → "stp"
        │
        ▼
   DisburseLoan.execute(loan_id, "stp")
        │
        ├─ loan_repo.get_by_id(loan_id)         ← get_current_connection()
        │  ensure_exists(loan)                    ← guarda: 404 si no existe
        │  ensure_approved(loan)                  ← guarda: 422 si no es approved
        │
        ├─ TX1: update_status_if("approved" → "disbursing")
        │       await tx.commit()
        │
        ├─ factory.get("stp") → StpDisburseService
        │  provider.execute(loan) → HTTP POST a STP  (fuera de transacción)
        │
        ├─ TX2: update_status("disbursed")
        │       await tx.commit()
        │
        ▼
   LoanController → DisburseLoanResponse
        │
        ▼
   FastAPI → JSON Response  (connection released al pool)
```

---

## Patrones de diseño utilizados

| Patrón | Implementación | Dónde |
|---|---|---|
| **Dependency Injection** | Constructor injection + Container manual | `dependencies/container.py` |
| **Factory** | `DisburseProviderFactory` → selección por nombre | `factory/` |
| **Strategy** | STP y Nvio implementan `DisburseProviderPort` | `service/` |
| **Protocol (Interface)** | Python `typing.Protocol` — duck typing tipado | `port/` |
| **Repository** | Encapsula SQL detrás de métodos async | `repository/` |
| **CQRS Lite** | Write repos (CRUD) + Query repos (JOINs) | `repository/` |
| **Decorator** | `@handle_db_errors`, `@handle_external_errors` | `exception/` |
| **Application Factory** | `create_app(config)` con Lifespan | `app.py` |
| **Singleton** | Todos los objetos creados una vez en Container | `dependencies/container.py` |

---

## Fortalezas

### Testabilidad
- **Unit tests sin BD:** `UseCase(AsyncMock())` — constructor injection hace que mockear sea trivial
- **Integration tests aislados:** `connection_context` + rollback por test
- **dependency_overrides:** Reemplazar cualquier singleton en tests de FastAPI sin tocar código

### Simplicidad y legibilidad
- **Use cases se leen como libro:** Sin try/catch, sin imports de infraestructura, solo lógica de negocio
- **Wiring visible en un solo archivo:** `container.py` muestra todo el grafo de dependencias
- **12 ADRs documentan cada decisión** con contexto, alternativas evaluadas y consecuencias

### Performance
- **Full async:** Miles de requests concurrentes con un solo event loop
- **asyncpg:** Driver PostgreSQL más rápido en Python, con pool configurable
- **Raw SQL:** Sin overhead de ORM, el SQL que escribes es el que se ejecuta
- **Connection pool:** Conexiones pre-alocadas, sin overhead de handshake por request

### Separación de concerns
- **Ports desacoplan capas:** Use cases no importan repos concretos
- **Schemas vs Entities:** HTTP concerns separados del dominio
- **Exception decorators:** Repos/services traducen errores sin contaminar use cases
- **CQRS Lite:** Lecturas complejas no contaminan repos de escritura

### Escalabilidad de código
- **Nuevo dominio:** Crear entity + port + repo + use case + controller + schema + router → `include_router()`
- **Nuevo proveedor:** Crear service + registrar en factory (1 línea en container)
- **Nueva query compleja:** Agregar método al query repo sin tocar el write repo
- **Réplica de BD:** Cambiar conexión del query repo, sin tocar use cases

---

## Debilidades

### Verbosidad
- **Muchos archivos para un CRUD simple:** entity + port + repo + use case + controller + schema = 6 archivos mínimo por dominio
- **Wiring manual:** Cada nueva dependencia requiere líneas en `container.py` — sin auto-discovery
- **Conversiones entre tipos:** `asyncpg.Record → dataclass → Pydantic` tiene costo (mínimo pero existe)

### Curva de aprendizaje
- **Modelo mental async:** El equipo debe entender event loop, `await`, y por qué no usar librerías sync
- **ContextVars:** El mecanismo de conexión por request es implícito — errores solo detectables en runtime
- **Dos patrones de transacción:** El developer debe elegir correctamente entre `@transactional` y `transaction_context()`

### Rigidez en algunas decisiones
- **Atados a PostgreSQL:** Raw SQL sin capa de abstracción elimina portabilidad entre BDs
- **Sin ORM:** No hay lazy loading, no hay auto-migrations, no hay query builder
- **Entidades anémicas hoy:** La lógica de negocio vive en use cases — si crece demasiado, hay que migrar a entidades ricas

### Overhead operacional
- **BD de test necesaria:** Integration tests requieren PostgreSQL real (Docker Compose)
- **Migraciones manuales:** Sin auto-generación — el developer escribe upgrade() y downgrade()

### Protocolos sin runtime enforcement
- **Sin mypy, los Protocols son invisibles:** Si no se corre mypy, una implementación que no cumple el Protocol compila y falla en runtime
- **Duck typing:** Errores de firma se detectan tarde si no hay CI con type checking

---

## Decisiones arquitectónicas (ADRs)

| # | Decisión | Alternativa rechazada |
|---|---|---|
| 001 | Full async en toda la cadena | Sync con threads |
| 002 | Connection pool + ContextVars + Depends | Middleware / Conexión por query |
| 003 | `@transactional` + `transaction_context()` | Decorator único para todo |
| 004 | Jerarquía excepciones + decorators + handler global | Try/catch en cada capa |
| 005 | Tipos mixtos (Pydantic + dataclass + dict) | Pydantic everywhere |
| 006 | Alembic + raw SQL | SQLAlchemy ORM + autogenerate |
| 007 | CQRS Lite (write + query repos) | JOINs en write repos |
| 008 | Unit (controller/UC) + Integration (repo) | Todo unit test con mocks |
| 009 | Python Protocols (duck typing) | ABC / Sin interfaces |
| 010 | Modelo anémico progresivo | Entidades ricas desde inicio |
| 011 | Raw queries con asyncpg | SQLAlchemy ORM |
| 012 | Schema (HTTP) + Entity (dominio) separados | Un modelo para todo |
| 013 | Constructor injection + container manual | DI Container library |

---

## Cuándo usar esta arquitectura

**Buen fit:**
- Microservicios con lógica de negocio no trivial
- Equipos que necesitan testabilidad y mantenibilidad a largo plazo
- Proyectos con integraciones a servicios externos (scoring, pagos, notificaciones)
- Equipos que prefieren control explícito sobre magia/auto-discovery

**No es buen fit:**
- CRUDs simples sin lógica de negocio (overkill — usar FastAPI directo)
- Prototipos rápidos donde la velocidad de desarrollo importa más que la estructura
- Equipos sin experiencia en async Python (la curva de aprendizaje es significativa)
- Proyectos que necesitan portabilidad entre BDs (el raw SQL es específico de PostgreSQL)
