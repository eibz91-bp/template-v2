# Plan de Arquitectura — Clean Architecture Template

## Principios

- El código se lee como un libro (de arriba a abajo, sin saltar entre archivos)
- Minimizar `if` en controllers y use cases — usar patrones (Factory, Strategy)
- Guardas simples permitidas (`if not x: raise`)
- Use cases y controllers son **singletons stateless**
- Repositorios usan **raw queries**
- **Full async** en toda la cadena (controller → use case → repository → service)
- Flujo: `Controller → UseCase → Repository / Service`

---

## Estructura de directorios

```
template/
│
├── app.py                       # Entry point: DI container + FastAPI
│
├── entity/                      # Capa 0: Entidades de dominio (dataclass)
│
├── port/                        # Contratos: Protocols que definen qué necesita cada capa
│
├── controller/                  # Capa 1: Presentación
│
├── use_case/                    # Capa 2: Lógica de negocio
│
├── repository/                  # Capa 3: Acceso a datos (raw queries)
│
├── service/                     # Capa 3: Integraciones externas
│
├── factory/                     # Patrones para eliminar if/else
│
├── schema/                      # DTOs HTTP: request/response (Pydantic)
│
├── exception/                   # Excepciones de dominio
│
├── database/                    # Conexión y sesión de BD
│
└── config/                      # Variables de entorno
```

---

## Capas y responsabilidades

### Capa 0 — Entity (`entity/`)

Entidades de dominio. Representan los objetos centrales del negocio.

**Hoy:** Son dataclasses con datos y factory methods (`from_record`). No tienen lógica de negocio (modelo anémico).

**Futuro:** Si la lógica de negocio crece, las entidades pueden incorporar comportamiento (validaciones, transiciones de estado, reglas de negocio que no dependen de infraestructura).

```python
# entity/loan.py — hoy (datos solamente)
from dataclasses import dataclass

@dataclass
class Loan:
    id: str
    client_id: str
    amount: float
    status: str

    @classmethod
    def from_record(cls, record):
        return cls(
            id=record["id"],
            client_id=record["client_id"],
            amount=float(record["amount"]),
            status=record["status"],
        )
```

```python
# entity/loan.py — futuro (con comportamiento, cuando se necesite)
@dataclass
class Loan:
    id: str
    client_id: str
    amount: float
    status: str

    def can_be_disbursed(self) -> bool:
        return self.status == "approved" and self.amount > 0

    def approve(self):
        if self.status != "pending":
            raise InvalidTransitionError("Can only approve pending loans")
        self.status = "approved"

    @classmethod
    def from_record(cls, record):
        ...
```

```python
# entity/result.py — resultado de operaciones externas
@dataclass
class Result:
    status: str
    reference: str | None = None
```

**Nota:** No agregar comportamiento a las entidades hasta que sea necesario. Si un `ensure_exists` en el use case basta, no mover esa lógica a la entidad. Las entidades crecen orgánicamente cuando la lógica de negocio lo justifica.

**Puede:**
- Contener datos del dominio
- Tener factory methods (`from_record`)
- Tener lógica de negocio que solo dependa de sus propios datos (futuro)

**No puede:**
- Importar repos, services, ni infraestructura
- Conocer HTTP, BD, ni frameworks
- Depender de nada externo (es el centro de la arquitectura)

---

### Port (`port/`)

Contratos (Protocols) que definen qué necesita cada capa. El use case define **qué métodos necesita** del repo/service. El repo/service los implementa.

```python
# port/loan_repository_port.py
from typing import Protocol
from entity.loan import Loan

class LoanRepositoryPort(Protocol):
    async def get_by_id(self, loan_id: str) -> Loan | None: ...
    async def create(self, client_id: str, amount: float) -> Loan: ...
    async def update_status_if(self, loan_id: str, from_status: str, to_status: str) -> Loan | None: ...
```

```python
# port/loan_query_repository_port.py
class LoanQueryRepositoryPort(Protocol):
    async def get_with_client(self, loan_id: str) -> dict | None: ...
    async def get_dashboard_summary(self) -> list[dict]: ...
```

```python
# port/provider_port.py
from entity.result import Result

class ProviderPort(Protocol):
    async def execute(self, entity) -> Result: ...
```

**El use case depende del protocol, no del concreto:**
```python
# use_case/disburse_loan.py
from port.loan_repository_port import LoanRepositoryPort

class DisburseLoan:
    def __init__(self, repo: LoanRepositoryPort, factory):
        self.repo = repo          # tipo: Protocol, no la clase concreta
        self.factory = factory
```

**El repo implementa el protocol implícitamente:**
```python
# repository/loan_repository.py
class LoanRepository:    # no hereda de nada — cumple el Protocol por duck typing
    async def get_by_id(self, loan_id: str) -> Loan | None:
        ...
```

**Verificación estática (opcional pero recomendada):**
```bash
# mypy o pyright detectan si el repo no cumple el protocol
mypy --strict
# Error: LoanRepository is missing method "update_status_if"
```

**Cuándo crear un protocol:**
- Cuando el use case necesita un repo o service → siempre
- Cuando el factory retorna implementaciones intercambiables → siempre (ej: `ProviderPort`)
- Para utilidades internas (logger, config) → no necesario

**No puede:**
- Tener implementación (solo firmas)
- Importar clases concretas (repos, services)
- Depender de infraestructura (asyncpg, httpx)

---

### Capa 1 — Controller (`controller/`)

Punto de entrada HTTP. Recibe, valida formato, delega, retorna.

**Puede:**
- Recibir requests HTTP
- Validar datos con schemas (Pydantic)
- Llamar use cases
- Retornar responses

**No puede:**
- Tener lógica de negocio
- Acceder a repositorios directamente
- Usar if/else para ramificar flujos

```python
class ExampleController:
    def __init__(self, some_use_case):
        self.some_use_case = some_use_case

    async def execute(self, request: SomeRequest):
        result = await self.some_use_case.execute(request.field_a, request.field_b)
        return SomeResponse(id=result.id, status=result.status)
```

---

### Capa 2 — Use Case (`use_case/`)

Orquesta la lógica de negocio. **1 clase = 1 operación.**

**Puede:**
- Llamar repositorios
- Llamar servicios externos
- Llamar factories para obtener implementaciones
- Usar guardas simples (`if not x: raise`)

**No puede:**
- Conocer HTTP ni FastAPI
- Escribir SQL
- Usar if/else para ramificar lógica de negocio

```python
from port.some_repository_port import SomeRepositoryPort

class SomeUseCase:
    def __init__(self, some_repository: SomeRepositoryPort, some_factory):
        self.some_repository = some_repository    # Protocol, no clase concreta
        self.some_factory = some_factory

    async def execute(self, entity_id, action_type):
        entity = await self.some_repository.get_by_id(entity_id)
        self.ensure_exists(entity, "Entity not found")

        handler = self.some_factory.get(action_type)         # sync — dict lookup
        result = await handler.execute(entity)

        await self.some_repository.update_status(entity_id, result.status)
        return result

    def ensure_exists(self, entity, message):
        if not entity:
            raise EntityNotFoundError(message)
```

---

### Capa 3a — Repository (`repository/`)

Acceso a datos con raw queries. **1 clase = 1 tabla/entidad** (para write repos). Los query repos (lectura) pueden hacer JOINs — ver decisión #7.

**Puede:**
- Ejecutar SQL (raw queries)
- Retornar diccionarios o dataclasses

**No puede:**
- Tener lógica de negocio
- Llamar servicios externos
- Conocer use cases ni controllers

```python
from database.context import get_current_connection

class SomeRepository:
    # Sin __init__ — singleton stateless, obtiene conexión de contextvars

    @handle_db_errors
    async def get_by_id(self, entity_id):
        conn = get_current_connection()
        return await conn.fetchrow("SELECT * FROM some_table WHERE id = $1", entity_id)

    @handle_db_errors
    async def create(self, field_a, field_b):
        conn = get_current_connection()
        return await conn.fetchrow(
            """INSERT INTO some_table (field_a, field_b, status)
               VALUES ($1, $2, 'pending')
               RETURNING *""",
            field_a, field_b
        )

    @handle_db_errors
    async def update_status(self, entity_id, status):
        conn = get_current_connection()
        await conn.execute(
            "UPDATE some_table SET status = $1 WHERE id = $2",
            status, entity_id
        )
```

---

### Capa 3b — Service (`service/`)

Comunicación con servicios externos. **1 clase = 1 integración.**

**Puede:**
- Hacer HTTP calls a APIs externas
- Usar SDKs de terceros

**No puede:**
- Tener lógica de negocio
- Acceder a la base de datos

```python
class ProviderAService:
    def __init__(self, http_client):
        self.http_client = http_client

    @handle_external_errors
    async def execute(self, entity):
        response = await self.http_client.post(PROVIDER_A_URL, json=entity)
        return Result(status="completed", reference=response.json()["id"])

class ProviderBService:
    def __init__(self, http_client):
        self.http_client = http_client

    @handle_external_errors
    async def execute(self, entity):
        response = await self.http_client.post(PROVIDER_B_URL, json=entity)
        return Result(status="completed", reference=response.json()["id"])
```

Todos los servicios intercambiables comparten el mismo método (`execute`) → Strategy pattern.

---

### Factory (`factory/`)

Elimina if/else mapeando nombres a implementaciones.

```python
class SomeFactory:
    def __init__(self, implementations: dict):
        self.implementations = implementations

    def get(self, name):
        implementation = self.implementations.get(name)
        if not implementation:
            raise ImplementationNotFoundError(f"'{name}' not supported")
        return implementation
```

Agregar una opción nueva = registrarla en `app.py`, sin tocar código existente.

---

### Schema (`schema/`)

DTOs HTTP exclusivamente. Solo Pydantic. Solo para validar requests y serializar responses. Las entidades de dominio viven en `entity/`.

```python
# schema/some_schema.py
class SomeRequest(BaseModel):
    field_a: str
    field_b: float

class SomeResponse(BaseModel):
    id: str
    status: str
```

**No confundir con `entity/`:**
- `schema/` → Pydantic, frontera HTTP, validación de input/output
- `entity/` → Dataclass, dominio, lógica interna

---

### Exception (`exception/`)

Jerarquía de excepciones con status code HTTP asociado. Ver decisión #4 para la implementación completa.

```python
class AppException(Exception):                    # base de toda la app
    def __init__(self, message, status_code=500):
        self.message = message
        self.status_code = status_code

class DomainException(AppException):               # errores de negocio (4xx)
    def __init__(self, message, status_code=400):
        super().__init__(message, status_code)

class EntityNotFoundError(DomainException):        # 404
    def __init__(self, message="Not found"):
        super().__init__(message, 404)

class InvalidTransitionError(DomainException):       # 422
    def __init__(self, message="Invalid transition"):
        super().__init__(message, 422)

class ImplementationNotFoundError(DomainException): # 400
    def __init__(self, message="Not supported"):
        super().__init__(message, 400)
```

---

### DI Container (`app.py`)

Todo se cablea aquí. Singletons creados una vez al inicio. Las clases concretas se instancian aquí y se inyectan como sus protocols.

```python
from fastapi import FastAPI, Depends
from database.connection import Database
from database import dependencies as db_deps
import httpx

# Database — pool singleton
database = Database()
db_deps.database = database

# HTTP Client — singleton reutilizable
http_client = httpx.AsyncClient(timeout=30.0)

# Repositories — concretos, cumplen los Protocols
some_repository = SomeRepository()            # implementa SomeRepositoryPort
other_repository = OtherRepository()          # implementa OtherRepositoryPort
some_query_repository = SomeQueryRepository() # implementa SomeQueryRepositoryPort

# Services — concretos, cumplen ProviderPort
provider_a = ProviderAService(http_client)    # implementa ProviderPort
provider_b = ProviderBService(http_client)    # implementa ProviderPort

# Factories
some_factory = SomeFactory({
    "provider_a": provider_a,
    "provider_b": provider_b,
    # nuevo proveedor = nueva línea aquí
})

# Use Cases — reciben Protocols, no clases concretas
some_use_case = SomeUseCase(some_repository, some_factory)
other_use_case = OtherUseCase(other_repository)
detail_use_case = GetDetailUseCase(some_query_repository)

# Controllers — singletons
some_controller = SomeController(some_use_case, other_use_case, detail_use_case)

# FastAPI — Depends global adquiere conexión por request
app = FastAPI(dependencies=[Depends(db_deps.get_db_connection)])

@app.on_event("startup")
async def startup():
    await database.connect("postgresql://user:pass@localhost:5432/mydb")

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()
    await http_client.aclose()

@app.post("/endpoint")
async def some_endpoint(request: SomeRequest):
    return await some_controller.execute(request)
```

**Nota:** `app.py` es el único lugar donde se conocen las clases concretas. Use cases, controllers y factories solo ven los Protocols.

---

## Flujo genérico de un request

```
POST /endpoint { field_a, field_b }
       │
       ▼
  Depends(get_db_connection)          ← adquiere conexión del pool
       │
       ▼
  FastAPI valida schema (Pydantic)
       │
       ▼
  await Controller.execute()          ← delega, no decide
       │
       ▼
  await UseCase.execute()             ← orquesta
       │
       ├──► await Repository.get_by_id()  ← raw query (get_current_connection)
       ├──► ensure_exists()                ← guarda (único if, sync)
       ├──► Factory.get(type)              ← sin if/else, mapeo directo (sync)
       │         └──► retorna Service
       ├──► await Service.execute(entity)  ← llamada externa async
       └──► await Repository.update()      ← raw query
       │
       ▼
  Response { id, status }
       │
       ▼
  Conexión devuelta al pool            ← automático al salir del Depends
```

---

## Patrones

| Patrón | Dónde | Propósito |
|---|---|---|
| **Singleton** | `app.py` | 1 instancia por componente, performance |
| **Factory** | `factory/` | Eliminar if/else al seleccionar implementaciones |
| **Strategy** | `service/` | Servicios intercambiables con misma interfaz |
| **Dependency Injection** | Constructor de cada clase | Desacoplamiento y testabilidad |
| **Protocol (Interface)** | `port/` | Contrato entre capas, verificable estáticamente |

---

## Regla de dependencias

```
Controller  ──►  UseCase  ──►  Port (Protocol)  ◄──  Repository (implementa)
                          ──►  Port (Protocol)  ◄──  Service (implementa)
                          ──►  Factory
                          ──►  Entity

Entity y Port no dependen de nada. Son el centro.
Nunca al revés. Nunca saltar capas.
```

```
Capas (de afuera hacia adentro):

  ┌─────────────────────────────────────────────┐
  │  FastAPI, asyncpg, httpx (Frameworks)       │
  │  ┌─────────────────────────────────────┐    │
  │  │  Controller, Repository, Service    │    │
  │  │  Schema (Pydantic DTOs)             │    │
  │  │  ┌─────────────────────────────┐    │    │
  │  │  │  Use Case                   │    │    │
  │  │  │  ┌─────────────────────┐    │    │    │
  │  │  │  │  Entity + Port      │    │    │    │
  │  │  │  │  (centro, sin deps) │    │    │    │
  │  │  │  └─────────────────────┘    │    │    │
  │  │  └─────────────────────────────┘    │    │
  │  └─────────────────────────────────────┘    │
  └─────────────────────────────────────────────┘
```

---

## Restricciones por capa

### Controller
| Restricción | Razón |
|---|---|
| No `if/else` para decidir flujos | El controller delega, no decide. Si necesitas ramificar, usa un Factory en el use case |
| No acceder a repositorios | Saltarse el use case acopla presentación con datos |
| No lógica de negocio | Si mueves lógica aquí, ya no puedes reusar el use case desde otro entry point (CLI, cron, queue) |
| No instanciar dependencias | Las recibe por constructor (DI). Si crea sus propias dependencias, no puedes testear ni reemplazar |

### Use Case
| Restricción | Razón |
|---|---|
| No `if/else` para ramificar lógica | Usa Factory/Strategy. Los if/else crecen con cada variante nueva y violan Open/Closed |
| Guardas simples sí permitidas | `if not entity: raise` es una validación, no una ramificación de flujo |
| No conocer HTTP/FastAPI | Si importas Request/Response aquí, el use case queda atado al framework |
| No escribir SQL | Eso es responsabilidad del repository. El use case solo dice "dame el dato" |
| 1 clase = 1 operación | Si un use case hace 2 cosas, es difícil de testear, nombrar y reusar |

### Repository
| Restricción | Razón |
|---|---|
| No lógica de negocio | Si pones reglas en el query, no puedes cambiar de BD sin reescribir lógica |
| No llamar servicios externos | Mezclar BD con HTTP calls crea acoplamiento y hace imposible transaccionar correctamente |
| No conocer use cases ni controllers | Las capas internas no conocen a las externas |
| Write repo: 1 clase = 1 tabla | Mantiene cohesión. Si un repo toca 3 tablas, es difícil de entender y mantener |
| Query repo: puede hacer JOINs | Repos de lectura pueden cruzar tablas para evitar N+1 (ver decisión #7) |

### Service
| Restricción | Razón |
|---|---|
| No lógica de negocio | Un service es un adaptador: traduce entre tu sistema y el mundo externo |
| No acceder a BD | Si necesita datos, los recibe como parámetro desde el use case |
| Misma interfaz entre servicios intercambiables | Si `ProviderA.execute()` y `ProviderB.run()` tienen firmas distintas, no puedes usar Factory/Strategy |

### Factory
| Restricción | Razón |
|---|---|
| No lógica de negocio | Solo mapea nombre → implementación |
| No instanciar dentro del factory | Las implementaciones se inyectan en el constructor. El factory solo las retorna |

### Entity
| Restricción | Razón |
|---|---|
| No importar repos, services, ni infra | Es el centro de la arquitectura, no depende de nada externo |
| No conocer HTTP, BD, ni frameworks | Si importas asyncpg aquí, la entidad queda atada a infraestructura |
| Solo lógica que dependa de sus propios datos | `loan.can_be_disbursed()` OK, `loan.save()` NO (eso es del repo) |

### Port
| Restricción | Razón |
|---|---|
| Solo firmas, sin implementación | Es un contrato, no código ejecutable |
| No importar clases concretas | Si importas `LoanRepository`, ya no es una abstracción |
| No depender de infra (asyncpg, httpx) | Los tipos del Protocol son de dominio (`Loan`, `str`), no de librerías |

---

## Patrones de diseño — Cuándo usar cada uno

### Factory Pattern

**Problema que resuelve:** Tienes múltiples implementaciones de algo y necesitas elegir una según un parámetro. Sin factory terminas con:
```python
# MAL — crece con cada variante nueva
if provider == "a":
    service = ProviderAService()
elif provider == "b":
    service = ProviderBService()
elif provider == "c":    # ← cada nueva opción = otro elif
    service = ProviderCService()
```

**Cuándo usarlo:**
- Necesitas seleccionar una implementación en runtime según un valor (string, enum, etc.)
- El número de opciones puede crecer con el tiempo
- Quieres agregar opciones sin modificar código existente

**Cuándo NO usarlo:**
- Solo hay 1 implementación y no va a haber más
- La selección es una guarda simple (`if not x: raise`)

**Cómo se ve en esta arquitectura:**
```python
# factory/
class SomeFactory:
    def __init__(self, implementations: dict):
        self.implementations = implementations

    def get(self, name):
        impl = self.implementations.get(name)
        if not impl:
            raise ImplementationNotFoundError(f"'{name}' not supported")
        return impl

# app.py — registro
factory = SomeFactory({
    "a": provider_a,       # instancias creadas arriba con http_client
    "b": provider_b,
    # agregar opción = agregar línea
})
```

---

### Strategy Pattern

**Problema que resuelve:** Tienes varias formas de hacer lo mismo y necesitas que sean intercambiables. Sin strategy, la lógica de cada variante queda mezclada en un solo método lleno de if/else.

**Cuándo usarlo:**
- Múltiples servicios externos que hacen lo mismo con APIs distintas
- Algoritmos intercambiables (ej: distintas formas de calcular un score, distintos métodos de pago)
- Quieres poder testear cada variante por separado

**Cuándo NO usarlo:**
- Solo hay una forma de hacerlo
- Las "variantes" difieren en 1 línea — ahí un parámetro basta

**Cómo se ve en esta arquitectura:**
```python
# service/ — todos comparten la misma interfaz
class ProviderAService:
    async def execute(self, entity):
        # lógica específica de provider A
        return Result(status="completed")

class ProviderBService:
    async def execute(self, entity):
        # lógica específica de provider B
        return Result(status="completed")

# use_case/ — no le importa cuál es, solo llama execute()
handler = self.some_factory.get(provider_name)
result = await handler.execute(entity)
```

**Relación con Factory:** El Factory selecciona cuál Strategy usar. Trabajan juntos.

---

### Singleton Pattern

**Problema que resuelve:** Crear objetos es costoso (conexiones de BD, HTTP clients, etc.) y no necesitas uno nuevo por cada request.

**Cuándo usarlo:**
- Controllers, Use Cases, Repositories y Services que son **stateless**
- Conexiones de base de datos (connection pools)
- HTTP clients reutilizables

**Cuándo NO usarlo:**
- El objeto guarda estado entre llamadas (ej: un contador, un cache mutable que no es thread-safe)
- Necesitas una instancia fresca por request (ej: un objeto que acumula datos del request actual)

**Cómo se ve en esta arquitectura:**
```python
# app.py — se instancia una vez, se reutiliza para siempre
some_repository = SomeRepository()              # sin params, usa contextvars
some_use_case = SomeUseCase(some_repository)
some_controller = SomeController(some_use_case)

# cada request reutiliza la misma instancia
@app.post("/endpoint")
async def endpoint(request: SomeRequest):
    return await some_controller.execute(request)  # misma instancia siempre
```

**Riesgo:** Si alguien mete `self.temp_data = ...` en un use case, ese dato persiste entre requests. Todo debe ser stateless.

---

### Chain of Responsibility Pattern

**Problema que resuelve:** Necesitas pasar un request por una serie de pasos (validaciones, transformaciones, autorizaciones) donde cada paso puede aprobar, rechazar o pasar al siguiente.

**Cuándo usarlo:**
- Pipeline de validaciones donde cada validación es independiente
- Middlewares (auth → logging → rate limit → handler)
- Cuando el número de pasos puede crecer y no quieres un bloque de if/else

**Cuándo NO usarlo:**
- Solo tienes 1-2 validaciones simples — un método basta
- Los pasos no son independientes entre sí

**Cómo se ve en esta arquitectura:**
```python
# Cada handler decide si procesa o pasa al siguiente
class ValidationHandler:
    def __init__(self, next_handler=None):
        self.next_handler = next_handler

    def handle(self, request):
        # validación específica
        self.validate(request)
        if self.next_handler:
            return self.next_handler.handle(request)
        return request

# Se encadenan
chain = AuthValidation(
    SchemaValidation(
        BusinessRuleValidation()
    )
)
chain.handle(request)
```

---

### Command Pattern

**Problema que resuelve:** Necesitas encapsular una acción como un objeto para poder encolarlo, deshacerlo, loguearlo o ejecutarlo después.

**Cuándo usarlo:**
- Sistemas de colas (SQS, RabbitMQ) donde encolas una acción para ejecutar después
- Necesitas un historial de acciones (audit log)
- Quieres poder hacer undo/redo

**Cuándo NO usarlo:**
- La acción se ejecuta inmediatamente y no necesitas historial
- Es un CRUD simple sin lógica de encolamiento

**Cómo se ve en esta arquitectura:**
```python
class SomeCommand:
    def __init__(self, entity_id, action_data):
        self.entity_id = entity_id
        self.action_data = action_data

    def execute(self):
        # ejecutar la acción

    def undo(self):
        # revertir la acción
```

**Nota:** En esta arquitectura, los Use Cases ya son muy similares al Command pattern (cada uno encapsula una operación con `execute()`). No necesitas un Command separado a menos que necesites undo o encolamiento.

---

### State Pattern

**Problema que resuelve:** Un objeto se comporta diferente según su estado actual. Sin state pattern terminas con:
```python
# MAL — cada método revisa el estado
def process(entity):
    if entity.status == "pending":
        # lógica para pending
    elif entity.status == "approved":
        # lógica para approved
    elif entity.status == "rejected":
        # lógica para rejected
```

**Cuándo usarlo:**
- Una entidad tiene un ciclo de vida con estados claros (pending → approved → disbursed → completed)
- El comportamiento cambia significativamente según el estado
- Las transiciones entre estados tienen reglas (no puedes ir de "pending" a "completed" directamente)

**Cuándo NO usarlo:**
- La entidad tiene 2 estados simples (activo/inactivo) — un booleano basta
- El estado solo se guarda pero no cambia el comportamiento

**Cómo se ve en esta arquitectura:**
```python
# Cada estado es una clase
class PendingState:
    def process(self, entity):
        # solo pending puede ser aprobado
        return ApprovedState()

    def cancel(self, entity):
        return CancelledState()

class ApprovedState:
    def process(self, entity):
        # aprobar ya no aplica, avanza a disbursed
        return DisbursedState()

    def cancel(self, entity):
        raise InvalidTransitionError("Cannot cancel approved entity")

# El use case no necesita if/else para saber qué hacer
state = state_factory.get(entity.status)
new_state = state.process(entity)
```

---

## Decisiones técnicas

### #1 — Full Async

**Decisión:** Toda la cadena es `async/await`. De controller a repository, sin excepciones.

**Por qué:** FastAPI corre en un event loop. Si un método en la cadena es sync, bloquea el event loop y ningún otro request se procesa hasta que termine.

**Stack async:**

| Capa | Librería async | Equivalente sync (NO usar) |
|---|---|---|
| HTTP Framework | `FastAPI` (async def) | Flask |
| Base de datos (PostgreSQL) | `asyncpg` | `psycopg2` |
| HTTP Client (APIs externas) | `httpx.AsyncClient` | `requests`, `httpx.Client` |
| Redis | `redis.asyncio` | `redis` |
| AWS (SQS, S3, etc.) | `aioboto3` | `boto3` |
| Mensajería (RabbitMQ) | `aio-pika` | `pika` |

**Regla:** Antes de agregar una dependencia, verificar que tenga soporte async. Si solo existe en sync, buscar alternativa async o wrappear con `asyncio.to_thread()` como último recurso.

---

### Cómo se ve async en cada capa

**Endpoint (FastAPI):**
```python
@app.post("/endpoint")
async def some_endpoint(request: SomeRequest):
    return await some_controller.execute(request)
#     ▲                                  ▲
#  async def                           await
```

**Controller:**
```python
class SomeController:
    async def execute(self, request: SomeRequest):
        result = await self.some_use_case.execute(request.field_a)
        return SomeResponse(id=result.id, status=result.status)
```

**Use Case:**
```python
class SomeUseCase:
    async def execute(self, entity_id):
        entity = await self.repository.get_by_id(entity_id)
        self.ensure_exists(entity, "Not found")        # sync OK — no hace I/O
        handler = self.factory.get(action_type)         # sync OK — dict lookup
        result = await handler.execute(entity)
        await self.repository.update_status(entity_id, result.status)
        return result
```

**Repository:**
```python
class SomeRepository:
    @handle_db_errors
    async def get_by_id(self, entity_id):
        conn = get_current_connection()
        return await conn.fetchrow("SELECT * FROM some_table WHERE id = $1", entity_id)
```

**Service (HTTP externo):**
```python
class ProviderAService:
    async def execute(self, entity):
        response = await self.http_client.post(PROVIDER_A_URL, json=entity)
        return Result(status="completed", reference=response.json()["id"])
```

---

### Qué necesita `await` y qué NO

| Operación | Necesita `await`? | Por qué |
|---|---|---|
| Query a base de datos | **SI** | I/O de red |
| HTTP call a API externa | **SI** | I/O de red |
| Leer/escribir archivo | **SI** | I/O de disco |
| Publicar mensaje a SQS/Redis | **SI** | I/O de red |
| Dict lookup (`factory.get(name)`) | **NO** | Operación en memoria |
| Validación (`if not entity: raise`) | **NO** | Operación en memoria |
| Crear un objeto/dataclass | **NO** | Operación en memoria |
| `json.dumps()` / `json.loads()` | **NO** | CPU, sin I/O |
| Pydantic validation | **NO** | CPU, sin I/O |
| Cálculos / lógica pura | **NO** | CPU, sin I/O |

**Regla simple:** Si cruza la frontera del proceso (red, disco, otro servicio) → `await`. Si es operación en memoria → sync normal.

---

### Errores comunes con async

**1. Olvidar `await` — el bug silencioso**
```python
# MAL — no explota, pero retorna un coroutine object, no el resultado
entity = self.repository.get_by_id(entity_id)
print(entity)  # <coroutine object get_by_id at 0x...>

# BIEN
entity = await self.repository.get_by_id(entity_id)
```

Python NO lanza error si olvidas `await`. Solo muestra un warning en logs que es fácil de ignorar. **Activar siempre:** `python -W error::RuntimeWarning` o `PYTHONWARNINGS=error::RuntimeWarning` para que el warning se convierta en excepción. También usar linters como `ruff` con reglas async (`ASYNC` rules) para detectarlo antes de correr.

**2. Llamar librería sync dentro de async**
```python
# MAL — bloquea el event loop
async def execute(self, entity):
    response = requests.post(url, json=entity)     # requests es SYNC
    return response

# BIEN — usar librería async
async def execute(self, entity):
    response = await self.http_client.post(url, json=entity)  # httpx async
    return response
```

**3. Último recurso: wrappear sync en thread**
```python
# Solo si NO existe alternativa async para la librería
import asyncio

async def execute(self, entity):
    result = await asyncio.to_thread(sync_library.call, entity)
    return result
```
`asyncio.to_thread()` mueve la llamada sync a un thread aparte para no bloquear el event loop. Usar solo cuando no hay alternativa async.

**4. Método `async def` que no hace `await` a nada**
```python
# INNECESARIO — si no hay I/O, no necesita ser async
async def ensure_exists(self, entity, message):
    if not entity:
        raise EntityNotFoundError(message)

# MEJOR — dejarlo sync
def ensure_exists(self, entity, message):
    if not entity:
        raise EntityNotFoundError(message)
```

Se puede llamar un método sync dentro de un método async sin problema. Solo necesitas `async def` cuando el método hace `await` internamente.

---

### #2 — Connection Pool + Session por Request

**Problema:** Los repositories son singletons, pero cada request necesita su propia conexión a BD. No puedes compartir una conexión entre requests concurrentes.

**Decisión:** El pool es singleton. La conexión se adquiere por request via un **context manager** compartido con `contextvars`. Para HTTP se usa `FastAPI Depends`. Para non-HTTP (scripts, workers, background tasks) se llama el context manager directamente.

**Por qué context manager + Depends y no Middleware:**
- Un solo mecanismo para todo (HTTP y non-HTTP)
- No desperdicia conexiones en endpoints que no tocan BD (ej: `/health`)
- Testeable con `app.dependency_overrides`

---

### Qué es un connection pool

```
Sin pool:                              Con pool:
Request 1 → abrir conexión (50ms)      Request 1 → tomar del pool (0.1ms)
Request 2 → abrir conexión (50ms)      Request 2 → tomar del pool (0.1ms)
Request 3 → abrir conexión (50ms)      Request 3 → tomar del pool (0.1ms)
Request 1 → cerrar conexión            Request 1 → devolver al pool
Request 2 → cerrar conexión            Request 2 → devolver al pool
```

El pool mantiene N conexiones abiertas y las reutiliza. `asyncpg` lo maneja nativamente con `create_pool()`.

---

### Arquitectura de conexión

```
┌──────────────────────────────────────────────────────┐
│  app.py (startup)                                    │
│  pool = asyncpg.create_pool(DATABASE_URL)  ← SINGLETON (1 pool para toda la app)
└───────────────────────┬──────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
   Request 1        Request 2       Request 3
   conn = pool      conn = pool     conn = pool
   .acquire()       .acquire()      .acquire()
        │               │               │
        ▼               ▼               ▼
   contextvars      contextvars     contextvars
   (conn aislada)   (conn aislada)  (conn aislada)
        │               │               │
   ┌────┴────┐     ┌────┴────┐     ┌────┴────┐
   │ repo_a  │     │ repo_a  │     │ repo_a  │  ← mismos singletons
   │ repo_b  │     │ repo_b  │     │ repo_b  │  ← pero cada request
   └─────────┘     └─────────┘     └─────────┘     ve su propia conn
```

---

### Componentes

**database/connection.py** — Pool singleton
```python
import asyncpg

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self, database_url, min_size=5, max_size=20):
        self.pool = await asyncpg.create_pool(
            database_url,
            min_size=min_size,    # conexiones mínimas abiertas desde el inicio
            max_size=max_size,    # tope máximo, requests extra esperan en cola
        )

    async def disconnect(self):
        await self.pool.close()
```

**database/context.py** — Context manager + contextvars
```python
from contextlib import asynccontextmanager
from contextvars import ContextVar

current_connection: ContextVar = ContextVar("current_connection")

def get_current_connection():
    """Obtiene la conexión del request actual. Error claro si no hay."""
    try:
        return current_connection.get()
    except LookupError:
        raise RuntimeError(
            "No database connection available. "
            "Use 'async with connection_context(database)' or "
            "ensure Depends(get_db_connection) is configured."
        )

@asynccontextmanager
async def connection_context(database):
    """Adquiere una conexión del pool y la pone en contextvars.
    Un solo mecanismo usado por HTTP (via Depends) y non-HTTP (via async with)."""
    async with database.pool.acquire() as conn:
        token = current_connection.set(conn)
        try:
            yield conn
        finally:
            current_connection.reset(token)
```

**database/dependencies.py** — Adapter para FastAPI Depends
```python
from database.context import connection_context

database = None    # se setea en app.py

async def get_db_connection():
    async with connection_context(database):
        yield
```

---

### Cómo el repository obtiene la conexión

```python
# repository/some_repository.py
from database.context import get_current_connection

class SomeRepository:
    # NO recibe nada en __init__ → sigue siendo singleton sin estado

    @handle_db_errors
    async def get_by_id(self, entity_id):
        conn = get_current_connection()    # conexión de ESTE request
        query = "SELECT * FROM some_table WHERE id = $1"
        return await conn.fetchrow(query, entity_id)

    @handle_db_errors
    async def create(self, data):
        conn = get_current_connection()
        query = """
            INSERT INTO some_table (field_a, field_b, status)
            VALUES ($1, $2, $3)
            RETURNING *
        """
        return await conn.fetchrow(query, data["field_a"], data["field_b"], data["status"])
```

**Nota sobre `asyncpg`:** Usa `$1, $2, $3` para parámetros (no `:name` como SQLAlchemy). Los valores se pasan como argumentos posicionales.

---

### Cómo se cablea en app.py

```python
from fastapi import FastAPI, Depends
from database.connection import Database
from database import dependencies as db_deps

# Pool — singleton
database = Database()
db_deps.database = database

# FastAPI — Depends global aplica a todos los endpoints
app = FastAPI(dependencies=[Depends(db_deps.get_db_connection)])

@app.on_event("startup")
async def startup():
    await database.connect(
        database_url="postgresql://user:pass@localhost:5432/mydb",
        min_size=5,
        max_size=20,
    )

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# Repositories — singletons, sin conexión en __init__
some_repository = SomeRepository()
other_repository = OtherRepository()

# Use Cases — singletons
some_use_case = SomeUseCase(some_repository)

# Controllers — singletons
some_controller = SomeController(some_use_case)
```

---

### Uso fuera de HTTP

El mismo `connection_context` sirve para cualquier contexto non-HTTP:

```python
# Background task
async def notify_in_background(data):
    async with connection_context(database):
        await notification_repo.create(data)

# Script / CLI
async def main():
    await database.connect(DATABASE_URL)
    async with connection_context(database):
        await some_repo.get_all()
    await database.disconnect()

# Worker / Consumer SQS
async def process_message(message):
    async with connection_context(database):
        await some_repo.create(json.loads(message.body))
```

```
connection_context()
    ├── HTTP       → via Depends (automático para todos los endpoints)
    ├── Background → via async with (explícito)
    ├── Script     → via async with (explícito)
    └── Worker     → via async with (explícito)
```

---

### Configuración del pool

| Parámetro | Qué hace | Recomendación |
|---|---|---|
| `min_size` | Conexiones mínimas **siempre abiertas** desde startup hasta shutdown | 5 (ajustar según carga base) |
| `max_size` | Conexiones máximas, las extras se crean bajo demanda | 20 (ajustar según BD y réplicas) |

**min_size siempre abiertas:**
```
3am (0 requests)   → 5 conexiones abiertas, 0 en uso
9am (3 requests)   → 5 conexiones abiertas, 3 en uso
Pico (8 requests)  → 8 conexiones abiertas (creó 3 bajo demanda)
Baja (2 requests)  → extras se cierran gradualmente, vuelve a 5
```

**Pool lleno — requests esperan en cola:**
```
max_size=20, todas ocupadas:

Request 21 llega → espera en cola...
Request 7 termina → libera conexión
Request 21 toma esa conexión → continúa
```

No falla, solo espera. Para evitar espera infinita, se puede poner timeout.

**Cómo calcular max_size:**
```
PostgreSQL max_connections = 100 (default)
- 10 reserva (admin, migraciones, monitoreo)
= 90 disponibles

Si tienes 3 instancias: 90 / 3 = 30 max_size por instancia
Si tienes 5 instancias: 90 / 5 = 18 max_size por instancia
```

Coordinar con el equipo de BD. Nunca exceder `max_connections` o PostgreSQL rechaza la conexión.

---

### Relación con singletons

| Componente | Singleton? | Por qué |
|---|---|---|
| `Database` (pool) | Si | 1 pool compartido por toda la app |
| `Connection` (por request) | No | Cada request toma una del pool via `contextvars` |
| `Repository` | Si | Stateless: no guarda conexión en `self`, la obtiene de `contextvars` |
| `UseCase` | Si | No conoce conexiones |
| `Controller` | Si | No conoce conexiones |

---

### #3 — Transacciones

**Problema:** Un use case llama a múltiples repositorios. Si uno falla, los anteriores ya insertaron datos. Necesitas atomicidad.

**Decisión:** Dos mecanismos según el tipo de use case:
- `@transactional` (decorator) para use cases que solo tocan BD
- `transaction_context` (explícito) para use cases que llaman a terceros y necesitan la respuesta

---

### Implementación

**database/transaction.py** — Decorator + context manager
```python
from database.context import get_current_connection
from contextlib import asynccontextmanager
from functools import wraps

@asynccontextmanager
async def transaction_context():
    """Context manager para transacciones explícitas."""
    conn = get_current_connection()
    async with conn.transaction():
        yield

def transactional(func):
    """Decorator que wrappea todo el método en una transacción."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        conn = get_current_connection()
        async with conn.transaction():
            return await func(*args, **kwargs)
    return wrapper
```

---

### 3 tipos de use case

#### Tipo 1 — Solo BD (sin llamadas externas)

CRUD, actualizaciones, queries que involucran varios repos.

```python
class CreateLoan:
    @transactional
    async def execute(self, client_id, amount):
        client = await self.client_repo.get_by_id(client_id)
        self.ensure_exists(client, "Client not found")
        return await self.loan_repo.create(client_id, amount)
```

`@transactional` wrappea todo. Simple, limpio, lee como libro.

#### Tipo 2 — BD + fire and forget (SQS, SMS, email, webhooks)

Operaciones que necesitan notificar pero no necesitan la respuesta.

```python
class ApproveLoan:
    @transactional
    async def execute(self, loan_id):
        updated = await self.repo.update_status_if(loan_id, "pending", "approved")
        self.ensure_was_updated(updated)
        await self.outbox_repo.save("notification", {"loan_id": loan_id})
```

Externo va al outbox (que es BD) → `@transactional` wrappea todo. El worker del outbox envía después.

#### Tipo 3 — BD + llamada a tercero que necesita respuesta

Operaciones donde necesitas la respuesta del tercero para decidir qué guardar.

```python
class DisburseLoan:
    async def execute(self, loan_id, provider_name):
        # Lectura
        loan = await self.repo.get_by_id(loan_id)
        self.ensure_exists(loan, "Loan not found")

        # Transacción 1: marcar in_progress (idempotente)
        async with transaction_context():
            updated = await self.repo.update_status_if(loan_id, "pending", "in_progress")
            self.ensure_was_updated(updated)

        # Llamada al tercero (fuera de transacción)
        provider = self.factory.get(provider_name)
        result = await provider.execute(loan)

        # Transacción 2: guardar resultado + notificación
        async with transaction_context():
            await self.repo.update_status(loan_id, result.status)
            await self.repo.create_record(loan, result.reference)
            await self.outbox_repo.save("notification", {"user": loan.user})

        return result
```

Status intermedio (`in_progress`) + reconciliación como red de seguridad.

---

### Guía de decisión para el developer

```
¿Tu use case llama a un tercero y necesita la respuesta?

    NO  → @transactional en el método execute
          (incluye outbox para fire-and-forget)

    SI  → transaction_context explícito
          status intermedio (in_progress)
          llamada al tercero entre transacciones
          resultado en segunda transacción
```

---

### Outbox pattern (para fire and forget)

En vez de llamar SQS/SMS directamente, se guarda el mensaje en una tabla de BD dentro de la misma transacción. Un worker aparte envía los mensajes.

**Tabla outbox:**
```sql
CREATE TABLE outbox (
    id SERIAL PRIMARY KEY,
    destination VARCHAR(100) NOT NULL,     -- "sqs", "sms", "email"
    payload JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, sent, dead_letter
    retry_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    sent_at TIMESTAMP
);
```

**Repository:**
```python
class OutboxRepository:

    @handle_db_errors
    async def save(self, destination, payload):
        conn = get_current_connection()
        return await conn.fetchrow(
            """INSERT INTO outbox (destination, payload)
               VALUES ($1, $2::jsonb)
               RETURNING *""",
            destination, json.dumps(payload)
        )

    @handle_db_errors
    async def get_pending(self, limit=10):
        conn = get_current_connection()
        return await conn.fetch(
            """SELECT * FROM outbox
               WHERE status = 'pending'
               ORDER BY created_at
               LIMIT $1""",
            limit
        )

    @handle_db_errors
    async def mark_sent(self, outbox_id):
        conn = get_current_connection()
        await conn.execute(
            """UPDATE outbox SET status = 'sent', sent_at = NOW()
               WHERE id = $1""",
            outbox_id
        )

    @handle_db_errors
    async def increment_retry(self, outbox_id):
        conn = get_current_connection()
        await conn.execute(
            "UPDATE outbox SET retry_count = retry_count + 1 WHERE id = $1",
            outbox_id
        )

    @handle_db_errors
    async def mark_dead_letter(self, outbox_id):
        conn = get_current_connection()
        await conn.execute(
            "UPDATE outbox SET status = 'dead_letter' WHERE id = $1",
            outbox_id
        )
```

**Worker:**
```python
MAX_RETRIES = 5

async def outbox_worker():
    while True:
        async with connection_context(database):
            messages = await outbox_repo.get_pending(limit=10)
            for msg in messages:
                try:
                    await send_to_destination(msg)
                    await outbox_repo.mark_sent(msg["id"])
                except Exception as e:
                    logger.error(f"Outbox {msg['id']} failed: {e}")
                    await outbox_repo.increment_retry(msg["id"])
                    if msg["retry_count"] >= MAX_RETRIES:
                        logger.critical(f"Outbox {msg['id']} moved to dead letter")
                        await outbox_repo.mark_dead_letter(msg["id"])
        await asyncio.sleep(1)
```

**Por qué funciona:**
- Transacción falla → mensaje nunca se guardó en outbox → nunca se envía
- Transacción OK → mensaje en outbox → worker lo envía
- Worker falla → mensaje queda pending → reintenta en el próximo ciclo

---

### Idempotencia en repositorios

Las transacciones requieren queries idempotentes para prevenir race conditions.

**UPDATE condicional (optimistic locking):**
```python
# Solo actualiza si el status actual es el esperado
async def update_status_if(self, entity_id, from_status, to_status):
    conn = get_current_connection()
    return await conn.fetchrow(
        """UPDATE some_table SET status = $1
           WHERE id = $2 AND status = $3
           RETURNING *""",
        to_status, entity_id, from_status
    )
    # Retorna el row actualizado, o None si alguien ya lo cambió
```

**Guard en el use case:**
```python
def ensure_was_updated(self, result):
    if not result:
        raise AlreadyProcessedError("Already processed")
```

**3 capas de protección idempotente:**
```
┌─────────────────────────────────────────┐
│ Capa 1: Idempotency Key (controller)   │ → mismo request no se re-ejecuta
├─────────────────────────────────────────┤
│ Capa 2: Status Guard (use case)        │ → operación duplicada se rechaza
├─────────────────────────────────────────┤
│ Capa 3: UPDATE condicional (repo/BD)   │ → race condition: solo 1 gana
└─────────────────────────────────────────┘
```

---

### Reconciliación (red de seguridad para tipo 3)

Para use cases que llaman a terceros, un cron verifica operaciones que quedaron atascadas en status intermedio:

```python
# cron cada 5 minutos
async def reconcile():
    async with connection_context(database):
        stuck = await repo.get_by_status("in_progress", older_than="5 minutes")
        for item in stuck:
            status = await provider.check_status(item.external_ref)
            await repo.update_status(item.id, status)
```

```
pending → in_progress → disbursed
              │
              └── stuck > 5 min? → cron consulta al tercero → actualiza
```

---

### #4 — Exception Handling

**Problema:** Sin estrategia de errores, terminas con try/catch en cada capa, errores de BD expuestos al cliente, y respuestas inconsistentes.

**Decisión:** Jerarquía de excepciones + decorators en repos/services + handler global en FastAPI. Use case y controller nunca hacen try/catch.

---

### Jerarquía de excepciones

```
Exception (Python base)
│
├── AppException (base de la app)
│   │
│   ├── DomainException (errores de negocio — 4xx)
│   │   ├── EntityNotFoundError          404
│   │   ├── AlreadyExistsError           409
│   │   ├── AlreadyProcessedError        409
│   │   ├── InvalidOperationError        422
│   │   └── InvalidTransitionError       422
│   │
│   ├── DatabaseException (errores de BD — 503)
│   │
│   └── ExternalServiceException (errores de terceros — 502/504)
│       ├── ProviderError                502
│       └── ProviderTimeoutError         504
│
└── Exception (no previsto → 500)
```

**Implementación:**
```python
# exception/base.py
class AppException(Exception):
    def __init__(self, message, status_code=500):
        self.message = message
        self.status_code = status_code

# exception/domain.py
class DomainException(AppException):
    def __init__(self, message, status_code=400):
        super().__init__(message, status_code)

class EntityNotFoundError(DomainException):
    def __init__(self, message="Not found"):
        super().__init__(message, 404)

class AlreadyExistsError(DomainException):
    def __init__(self, message="Already exists"):
        super().__init__(message, 409)

class AlreadyProcessedError(DomainException):
    def __init__(self, message="Already processed"):
        super().__init__(message, 409)

class InvalidOperationError(DomainException):
    def __init__(self, message="Invalid operation"):
        super().__init__(message, 422)

class InvalidTransitionError(DomainException):
    def __init__(self, message="Invalid transition"):
        super().__init__(message, 422)

# exception/infrastructure.py
class DatabaseException(AppException):
    def __init__(self, message="Service temporarily unavailable"):
        super().__init__(message, 503)

class ExternalServiceException(AppException):
    def __init__(self, message="External service unavailable", status_code=502):
        super().__init__(message, status_code)

class ProviderError(ExternalServiceException):
    def __init__(self, message="Provider unavailable"):
        super().__init__(message, 502)

class ProviderTimeoutError(ExternalServiceException):
    def __init__(self, message="Provider timeout"):
        super().__init__(message, 504)
```

---

### Decorators — traducen errores de librerías a la jerarquía

**`@handle_db_errors`** — red de seguridad para repos. Traduce cualquier error de asyncpg a `DatabaseException` (503). Si el repo quiere traducir algo específico a un error de negocio (ej: `UniqueViolation` → `AlreadyExistsError`), lo hace con try/catch puntual ANTES de que el decorator lo atrape.

```python
# exception/decorators.py
from functools import wraps
import asyncpg

def handle_db_errors(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except AppException:
            raise                                    # ya fue traducido → dejarlo pasar
        except asyncpg.PostgresError as e:
            raise DatabaseException(str(e))          # genérico → 503
    return wrapper

def handle_external_errors(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except AppException:
            raise                                    # ya fue traducido → dejarlo pasar
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(str(e))       # timeout → 504
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"Status {e.response.status_code}")  # HTTP error → 502
        except httpx.HTTPError as e:
            raise ExternalServiceException(str(e))   # genérico → 502
    return wrapper
```

**Nota:** `except AppException: raise` es clave. Si el método del repo ya tradujo el error a una excepción de negocio (ej: `AlreadyExistsError`), el decorator la deja pasar sin re-traducirla.

---

### Repository — decorator genérico + override puntual cuando tiene sentido de negocio

```python
class LoanRepository:

    @handle_db_errors
    async def get_by_id(self, loan_id):
        conn = get_current_connection()
        return await conn.fetchrow("SELECT * FROM loans WHERE id = $1", loan_id)
        # BD falla → decorator → DatabaseException (503)

    @handle_db_errors
    async def create(self, client_id, amount):
        try:
            conn = get_current_connection()
            return await conn.fetchrow(
                """INSERT INTO loans (client_id, amount, status)
                   VALUES ($1, $2, 'pending') RETURNING *""",
                client_id, amount
            )
        except asyncpg.UniqueViolationError:
            raise AlreadyExistsError("Loan already exists")     # override: 409
        except asyncpg.ForeignKeyViolationError:
            raise EntityNotFoundError("Client not found")       # override: 404
        # cualquier OTRO error postgres → decorator → DatabaseException (503)

    @handle_db_errors
    async def update_status_if(self, loan_id, from_status, to_status):
        conn = get_current_connection()
        return await conn.fetchrow(
            """UPDATE loans SET status = $1
               WHERE id = $2 AND status = $3 RETURNING *""",
            to_status, loan_id, from_status
        )
        # no hay UniqueViolation esperada → decorator basta
```

**Regla:** El decorator siempre está (red de seguridad). El try/catch puntual solo cuando el error tiene significado de negocio y el developer lo sabe.

---

### Service — misma lógica

```python
class StpService:

    @handle_external_errors
    async def execute(self, loan):
        response = await self.http_client.post(STP_URL, json=loan)
        response.raise_for_status()
        return Result(status="disbursed", reference=response.json()["id"])
        # timeout → decorator → ProviderTimeoutError (504)
        # HTTP error → decorator → ProviderError (502)
```

---

### Use case — cero try/catch

```python
class DisburseLoan:
    async def execute(self, loan_id, provider_name):
        loan = await self.repo.get_by_id(loan_id)
        self.ensure_exists(loan, "Loan not found")

        async with transaction_context():
            updated = await self.repo.update_status_if(loan_id, "pending", "in_progress")
            self.ensure_was_updated(updated)

        provider = self.factory.get(provider_name)
        result = await provider.execute(loan)

        async with transaction_context():
            await self.repo.update_status(loan_id, result.status)

        return result

    def ensure_exists(self, entity, message):
        if not entity:
            raise EntityNotFoundError(message)

    def ensure_was_updated(self, result):
        if not result:
            raise AlreadyProcessedError("Already processed")
```

---

### Controller — cero try/catch

```python
class LoanController:
    async def disburse(self, request):
        result = await self.use_case.execute(request.loan_id, request.provider)
        return DisburseLoanResponse(status=result.status)
```

---

### Handler global — catchea por categoría, cero isinstance

```python
# exception/handler.py
async def domain_handler(request, exc: DomainException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message}
    )

async def database_handler(request, exc: DatabaseException):
    logger.error(f"Database error: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "Service temporarily unavailable"}
    )

async def external_handler(request, exc: ExternalServiceException):
    logger.error(f"External service error: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message}
    )

async def catch_all_handler(request, exc: Exception):
    logger.critical(f"Unhandled: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )

# app.py
app.add_exception_handler(DomainException, domain_handler)
app.add_exception_handler(DatabaseException, database_handler)
app.add_exception_handler(ExternalServiceException, external_handler)
app.add_exception_handler(Exception, catch_all_handler)
```

---

### Quién hace qué con errores

| Capa | Try/catch? | Qué hace |
|---|---|---|
| Repository | `@handle_db_errors` siempre + try/catch puntual opcional | Decorator: genérico 503. Override: negocio 4xx |
| Service | `@handle_external_errors` siempre | Decorator: genérico 502/504 |
| Use Case | No | Lanza guards (`ensure_exists`, `ensure_was_updated`) |
| Controller | No | Delega |
| Handler global | Catchea todo por categoría | Traduce a HTTP response + loguea |

### Flujo de un error

```
Error nace en repo/service
    │
    ├── ¿Tiene significado de negocio? (try/catch puntual en el método)
    │       SI  → DomainException (4xx) → sube → domain_handler
    │       NO  → sigue al decorator
    │
    ├── Decorator lo traduce a categoría genérica
    │       @handle_db_errors       → DatabaseException (503)
    │       @handle_external_errors → ExternalServiceException (502/504)
    │
    └── Sube por use case y controller (nadie lo catchea)
            │
            └── Handler global → JSONResponse al cliente
```

---

### #5 — Tipo de dato entre capas

**Problema:** Sin un contrato entre capas, todo es dict/Record implícito. Typos y cambios de schema explotan en runtime sin autocomplete ni tipos.

**Decisión:** Approach mixto — Pydantic en las fronteras HTTP, dataclass cuando el use case trabaja con los campos, dict para datos que solo se pasan (JOINs, listas).

---

### Qué tipo se usa en cada capa

| Dato | Tipo | Dónde vive | Por qué |
|---|---|---|---|
| Request HTTP | Pydantic `BaseModel` | `schema/` | Validación de entrada |
| Entidad de dominio | `dataclass` con `from_record` | `entity/` | Autocomplete, tipos, lógica |
| Dato de paso (JOINs, listas) | `dict` | — | Sin conversión innecesaria |
| Response HTTP | Pydantic `BaseModel` | `schema/` | Serialización, ignora campos extras |

### Guía de decisión

```
¿El use case accede a campos del dato para hacer lógica?
    SI  → dataclass
    NO  → dict directo
```

---

### Dataclass con factory method

```python
# entity/loan.py — vive en entity/, NO en schema/
from dataclasses import dataclass

@dataclass
class Loan:
    id: str
    client_id: str
    amount: float
    status: str

    @classmethod
    def from_record(cls, record):
        return cls(
            id=record["id"],
            client_id=record["client_id"],
            amount=float(record["amount"]),
            status=record["status"],
        )
        # columnas extras en la BD → se ignoran
        # columnas faltantes → KeyError claro con nombre del campo
        # tipos → se convierten explícitamente (Decimal → float)
```

---

### Repository — retorna dataclass o dict según el caso

```python
# Write repo — dataclass (use case trabaja con campos)
class LoanRepository:

    @handle_db_errors
    async def get_by_id(self, loan_id) -> Loan | None:
        conn = get_current_connection()
        record = await conn.fetchrow(
            "SELECT id, client_id, amount, status FROM loans WHERE id = $1",
            loan_id
        )
        return Loan.from_record(record) if record else None

# Query repo — dict (JOIN directo, solo pasa datos al response)
class LoanQueryRepository:

    @handle_db_errors
    async def get_with_client(self, loan_id) -> dict | None:
        conn = get_current_connection()
        record = await conn.fetchrow(
            """SELECT l.id, l.amount, l.status, c.name as client_name
               FROM loans l JOIN clients c ON l.client_id = c.id
               WHERE l.id = $1""",
            loan_id
        )
        return dict(record) if record else None
```

---

### Use case — trabaja con dataclass (autocomplete, tipos)

```python
class DisburseLoan:
    async def execute(self, loan_id, provider_name):
        loan = await self.repo.get_by_id(loan_id)
        self.ensure_exists(loan, "Loan not found")

        loan.status      # ✅ autocomplete
        loan.amount      # ✅ tipo float
        loan.statos      # ❌ IDE marca error antes de correr
        return loan
```

---

### Controller — convierte a Pydantic Response

```python
from dataclasses import asdict

class LoanController:

    # Desde dataclass (write use case retorna dataclass)
    async def disburse(self, request: DisburseLoanRequest):
        result = await self.disburse_use_case.execute(request.loan_id, request.provider)
        return DisburseLoanResponse(**asdict(result))

    # Desde dict (read use case retorna dict de JOIN via query repo)
    async def get_detail(self, request):
        detail = await self.get_detail_use_case.execute(request.loan_id)
        return LoanDetailResponse.model_validate(detail)
```

Pydantic `model_validate` ignora campos extras del dict — toma solo lo que el model define.

---

### Pydantic Schemas (request/response) — solo en `schema/`

```python
# schema/loan_schema.py — DTOs HTTP, NO entidades de dominio
from pydantic import BaseModel

class CreateLoanRequest(BaseModel):
    client_id: str
    amount: float

class DisburseLoanRequest(BaseModel):
    loan_id: str
    provider: str

class LoanResponse(BaseModel):
    id: str
    status: str
    amount: float

class LoanDetailResponse(BaseModel):
    id: str
    amount: float
    status: str
    client_name: str
```

---

### Flujo completo de tipos

```
POST /loans { client_id, amount }
       │
       ▼
  schema/  → Pydantic CreateLoanRequest (valida input HTTP)
       │
       ▼
  Controller pasa campos al use case
       │
       ▼
  entity/ → Use case trabaja con Loan dataclass
       │
       ▼
  Repository: asyncpg Record → Loan.from_record() (entity/)
       │
       ▼
  Controller: asdict(loan) → LoanResponse (schema/)
       │
       ▼
  Response JSON { id, status, amount }
```

---

### #6 — Migraciones sin ORM

**Problema:** Sin ORM no hay migraciones automáticas. Necesitas una estrategia para versionar cambios de schema.

**Decisión:** Alembic con SQL puro. Sin modelos de SQLAlchemy. Escribes el SQL directo en las migraciones.

---

### Estructura

```
template/
├── migrations/
│   ├── env.py                         # Config de Alembic
│   ├── script.py.mako                 # Template de migraciones
│   └── versions/
│       ├── 001_create_clients.py
│       ├── 002_create_loans.py
│       └── 003_add_disbursed_at.py
└── alembic.ini                        # Connection string y config
```

---

### Ejemplo de migración

```bash
# Generar migración vacía
alembic revision -m "create loans table"
```

```python
# migrations/versions/002_create_loans.py
from alembic import op

def upgrade():
    op.execute("""
        CREATE TABLE loans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            client_id UUID NOT NULL REFERENCES clients(id),
            amount NUMERIC(12,2) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_loans_client_id ON loans(client_id)")
    op.execute("CREATE INDEX idx_loans_status ON loans(status)")

def downgrade():
    op.execute("DROP TABLE loans")
```

```python
# migrations/versions/003_add_disbursed_at.py
from alembic import op

def upgrade():
    op.execute("ALTER TABLE loans ADD COLUMN disbursed_at TIMESTAMP")

def downgrade():
    op.execute("ALTER TABLE loans DROP COLUMN disbursed_at")
```

---

### Comandos

```bash
alembic upgrade head      # aplica todas las migraciones pendientes
alembic downgrade -1      # revierte la última migración
alembic history           # muestra historial de migraciones
alembic current           # muestra migración actual de la BD
```

---

### Flujo de un cambio de schema

```
1. Developer escribe migración:  alembic revision -m "add column"
2. Escribe SQL en upgrade() y downgrade()
3. Actualiza dataclass en entity/ (si aplica)
4. Actualiza port/ si la firma del repo cambió (si aplica)
5. Actualiza raw query en repository (si aplica)
6. Aplica migración:  alembic upgrade head
7. Commit todo junto (migración + entity + port + query)
```

---

### Lo que te da Alembic sin models

| Funcionalidad | Disponible? |
|---|---|
| Versionamiento de migraciones | Si |
| Upgrade / downgrade | Si |
| Historial en git | Si |
| Orden de ejecución garantizado | Si |
| Auto-generación de migraciones | No (sin models) |
| Detección de cambios olvidados | No (sin models) |

---

### #7 — CQRS Lite (Separación de lectura y escritura)

**Problema:** Dijimos que 1 repo = 1 tabla. Pero cuando un use case necesita datos de varias tablas, caes en N+1 queries:

```python
# MAL — N+1 queries
loans = await self.loan_repo.get_all()           # 1 query
for loan in loans:
    client = await self.client_repo.get_by_id(loan.client_id)  # N queries
```

100 loans = 101 queries. Debería ser 1 JOIN.

**Decisión:** CQRS lite — separar repos de escritura y repos de lectura a nivel de código. Hoy usan el mismo pool. El día que haya una réplica de BD, los query repos apuntan al pool de lectura sin tocar use cases ni controllers.

---

### Separación de repos

```python
# repository/loan_repository.py (write)
# CRUD + SELECTs simples de su tabla. Siempre del primary.
from entity.loan import Loan

class LoanRepository:

    @handle_db_errors
    async def get_by_id(self, loan_id):
        conn = get_current_connection()
        record = await conn.fetchrow(
            "SELECT * FROM loans WHERE id = $1", loan_id
        )
        return Loan.from_record(record) if record else None

    @handle_db_errors
    async def create(self, client_id, amount):
        conn = get_current_connection()
        record = await conn.fetchrow(
            """INSERT INTO loans (client_id, amount, status)
               VALUES ($1, $2, 'pending') RETURNING *""",
            client_id, amount
        )
        return Loan.from_record(record)

    @handle_db_errors
    async def update_status_if(self, loan_id, from_status, to_status):
        conn = get_current_connection()
        record = await conn.fetchrow(
            """UPDATE loans SET status = $1
               WHERE id = $2 AND status = $3 RETURNING *""",
            to_status, loan_id, from_status
        )
        return Loan.from_record(record) if record else None

# repository/loan_query_repository.py (read)
# JOINs, agregaciones, dashboards. Lee de replica cuando exista.
class LoanQueryRepository:

    @handle_db_errors
    async def get_with_client(self, loan_id):
        conn = get_current_connection()
        return await conn.fetchrow(
            """SELECT l.id, l.amount, l.status, c.name as client_name
               FROM loans l JOIN clients c ON l.client_id = c.id
               WHERE l.id = $1""",
            loan_id
        )

    @handle_db_errors
    async def get_dashboard_summary(self):
        conn = get_current_connection()
        return await conn.fetch(
            """SELECT l.status, COUNT(*) as total, SUM(l.amount) as amount
               FROM loans l
               GROUP BY l.status"""
        )
```

---

### Qué use case usa qué repo

```python
from port.loan_repository_port import LoanRepositoryPort
from port.loan_query_repository_port import LoanQueryRepositoryPort

# Write use case — depende del Protocol de escritura
class DisburseLoan:
    def __init__(self, loan_repo: LoanRepositoryPort, factory):
        ...

# Read use case — depende del Protocol de lectura
class GetLoanDetail:
    def __init__(self, loan_query_repo: LoanQueryRepositoryPort):
        ...
```

---

### Hoy vs futuro

```
Hoy (1 pool):
  LoanRepository        ──► get_current_connection() ──► pool único
  LoanQueryRepository   ──► get_current_connection() ──► pool único

Futuro (2 pools, réplica):
  LoanRepository        ──► get_write_connection() ──► pool primary
  LoanQueryRepository   ──► get_read_connection()  ──► pool replica
```

Hoy la separación es **solo de código**. Ambos repos usan `get_current_connection()` y el mismo pool. El día que pongan una réplica:
1. Se crea un segundo pool apuntando a la replica
2. Los query repos cambian a `get_read_connection()`
3. No se tocan use cases ni controllers

---

### Consistencia: cuándo leer del primary

La replica puede tener replication lag (milisegundos a segundos). Para la mayoría de lecturas (dashboards, listas, reportes) no importa.

**Write use case que lee antes de escribir:** usa `LoanRepository.get_by_id()` → siempre del primary → consistente.

**Query repo que necesita consistencia fuerte (raro):** el developer elige usar `get_write_connection()` en ese método específico:

```python
class LoanQueryRepository:
    # Normal — replica (tolera staleness)
    async def get_with_client(self, loan_id):
        conn = get_read_connection()
        ...

    # Necesita consistencia — primary
    async def get_balance_with_transactions(self, client_id):
        conn = get_write_connection()
        ...
```

No hay flag ni parámetro. El developer decide al escribir el método qué conexión usa.

---

### Resumen

| Repo | Conexión | Qué hace |
|---|---|---|
| `LoanRepository` | primary (siempre) | CRUD + SELECTs simples de su tabla |
| `LoanQueryRepository` | replica (default) | JOINs, agregaciones, dashboards |
| `LoanQueryRepository` | primary (cuando se necesite) | JOINs que necesitan consistencia fuerte |

---

### #8 — Testing con singletons

**Problema:** Todo es singleton. ¿Cómo testeas sin que un test afecte a otro? ¿Cómo testeas repos que usan `get_current_connection()` de contextvars?

**Decisión:** Unit tests para controller y use case (mock via constructor). Integration tests para repo, service y decorators (necesitan BD real). Coverage se combina de ambos.

---

### Por qué los singletons no son problema

En tests no usas los singletons de `app.py`. Creas instancias nuevas con mocks:

```python
# En app.py — singleton
some_use_case = SomeUseCase(some_repository)

# En test — instancia nueva con mock
mock_repo = AsyncMock()
use_case = SomeUseCase(mock_repo)    # no es el singleton de app.py
```

La DI por constructor hace que cada test cree su propia instancia aislada.

---

### Unit tests — Controller y Use Case

No necesitan BD, pool ni context manager. Solo mocks.

**Use case:**
```python
async def test_use_case_executes_correctly():
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = SomeEntity(id="1", status="pending")
    mock_repo.update_status_if.return_value = SomeEntity(id="1", status="processed")

    mock_factory = Mock()
    mock_provider = AsyncMock()
    mock_provider.execute.return_value = Result(status="completed")
    mock_factory.get.return_value = mock_provider

    use_case = SomeUseCase(mock_repo, mock_factory)
    result = await use_case.execute("1", "provider_a")

    assert result.status == "completed"
    mock_repo.update_status_if.assert_called_once()
```

**Controller:**
```python
async def test_controller_returns_response():
    mock_use_case = AsyncMock()
    mock_use_case.execute.return_value = Result(status="completed")

    controller = SomeController(mock_use_case)
    response = await controller.execute(SomeRequest(entity_id="1", action="do"))

    assert response.status == "completed"
```

---

### Integration tests — Repository y Service

Los repos ejecutan SQL real y los decorators (`@handle_db_errors`, `@transactional`) atrapan excepciones reales. Sin BD no hay nada que testear.

**Fixture con `connection_context` + rollback:**
```python
@pytest.fixture
async def db():
    test_db = Database()
    await test_db.connect("postgresql://localhost:5432/test_db")

    async with connection_context(test_db) as conn:
        transaction = conn.transaction()
        await transaction.start()
        yield                          # test corre aquí
        await transaction.rollback()   # limpia todo

    await test_db.disconnect()
```

**Nota sobre transacciones anidadas:** Si el código bajo test usa `@transactional` o `transaction_context()`, asyncpg crea un **savepoint** dentro de la transacción del fixture. Esto funciona correctamente — el savepoint hace commit pero la transacción externa (del fixture) hace rollback al final, deshaciendo todo. No requiere configuración extra.

**Test de repo:**
```python
async def test_repo_creates_entity(db):
    repo = SomeRepository()
    result = await repo.create("field_a_value", 100.00)

    assert result["status"] == "pending"
    assert result["field_a"] == "field_a_value"
```

**Test de service (mock HTTP, no mock BD):**
```python
async def test_service_calls_provider(httpx_mock):
    httpx_mock.add_response(json={"id": "ext-1", "status": "ok"})

    service = ProviderAService(http_client)
    result = await service.execute(some_entity)

    assert result.status == "completed"
    assert result.reference == "ext-1"
```

---

### Qué tipo de test para cada capa

| Capa | Unit test | Integration test | Qué necesita |
|---|---|---|---|
| Controller | Si | — | Mock del use case |
| Use Case | Si | — | Mock del repo/factory |
| Repository | — | Si | BD real + `connection_context` |
| Service | — | Si | Mock HTTP (`httpx_mock`) |
| Decorators | — | Si | BD real (para errores reales) |

---

### Coverage en CI

```bash
# 1. Unit tests (sin BD, rápido)
pytest tests/unit --cov

# 2. Levantar BD de test
docker compose up -d test-db

# 3. Integration tests (con BD)
pytest tests/integration --cov --cov-append

# 4. Reporte combinado
coverage report
```

`--cov-append` combina el coverage de ambas etapas. Unit tests cubren controller + use case. Integration tests cubren repo + service + decorators. El reporte final refleja todo.

---

### Estructura de tests

```
tests/
├── unit/
│   ├── test_some_controller.py
│   └── test_some_use_case.py
│
├── integration/
│   ├── test_some_repository.py
│   ├── test_some_query_repository.py
│   └── test_some_service.py
│
├── conftest.py                    # fixture de BD compartido
└── docker-compose.test.yml        # BD de test
```

---

## Guía rápida — Qué patrón usar según el problema

| Problema | Patrón | Ejemplo |
|---|---|---|
| "Necesito elegir entre múltiples implementaciones según un valor" | **Factory** | Seleccionar proveedor por nombre |
| "Tengo varias formas de hacer lo mismo, intercambiables" | **Strategy** | Múltiples APIs externas con misma función |
| "No quiero crear objetos nuevos en cada request" | **Singleton** | Controllers, Use Cases, Repos stateless |
| "Necesito pasar por una cadena de validaciones/pasos" | **Chain of Responsibility** | Pipeline de validaciones |
| "Necesito encolar, loguear o deshacer una acción" | **Command** | Acciones asíncronas, audit log |
| "El comportamiento cambia según el estado de la entidad" | **State** | Ciclo de vida con transiciones (pending → approved → ...) |
