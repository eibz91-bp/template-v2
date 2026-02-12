# Architecture Decision Records (ADR)

Registro de todas las decisiones arquitectónicas discutidas, con contexto, opciones evaluadas, justificación y consecuencias.

**Formato:** Cada ADR sigue la estructura: Contexto → Opciones → Decisión → Justificación → Consecuencias.

---

## ADR-001: Full Async en toda la cadena

**Status:** Aceptado

**Contexto:**
FastAPI corre sobre un event loop async. Si cualquier método en la cadena (controller → use case → repository → service) es sync y hace I/O, bloquea el event loop completo. Ningún otro request se procesa hasta que termine.

**Opciones consideradas:**

| Opción | Descripción |
|---|---|
| A) Full async | Toda la cadena es `async/await`. Librerías async en cada capa |
| B) Sync con threads | Usar `run_in_executor` para wrappear llamadas sync |
| C) Mixto | Async en controller, sync en repos/services |

**Por qué NO las otras:**
- **B) Sync con threads:** Introduce overhead de context switching. Pierde las ventajas del event loop. Cada thread consume ~8MB de stack. No escala con miles de conexiones concurrentes.
- **C) Mixto:** Crea confusión sobre qué es async y qué no. Un solo `requests.post()` en un service bloquea todo. El developer tiene que recordar dónde es seguro llamar sync — propenso a errores silenciosos.

**Decisión:** Opción A — Full async.

**Justificación:**
- Un solo event loop maneja miles de conexiones concurrentes con ~KB por coroutine (vs ~MB por thread)
- Si olvidas `await`, Python lanza un `RuntimeWarning` que con `PYTHONWARNINGS=error::RuntimeWarning` se convierte en excepción — detectable antes de producción
- asyncpg es ~3x más rápido que psycopg2 en benchmarks
- El equipo necesita aprender un solo modelo mental: si cruza la frontera del proceso → `await`

**Consecuencias:**
- (+) Performance superior bajo carga concurrente
- (+) Modelo mental consistente en toda la app
- (-) Toda dependencia nueva debe tener soporte async. Si no existe, `asyncio.to_thread()` como último recurso
- (-) Debugging de async puede ser más complejo (stack traces más largos)
- (-) El equipo debe aprender async/await si no lo conoce

**Stack elegido:**

| Capa | Async | Sync (rechazado) |
|---|---|---|
| HTTP Framework | FastAPI | Flask |
| Base de datos | asyncpg | psycopg2 |
| HTTP Client | httpx.AsyncClient | requests |
| Redis | redis.asyncio | redis |
| AWS | aioboto3 | boto3 |

---

## ADR-002: Connection Pool + Session por Request via Context Manager

**Status:** Aceptado

**Contexto:**
Los repositories son singletons stateless. Cada request HTTP necesita su propia conexión a BD para evitar que requests concurrentes interfieran entre sí. Necesitamos un mecanismo que funcione tanto para HTTP (FastAPI) como para non-HTTP (workers, scripts, crons).

**Opciones consideradas:**

| Opción | Descripción |
|---|---|
| A) Middleware | Middleware de FastAPI que adquiere conexión antes de cada request |
| B) Depends + Context Manager | `connection_context` reutilizable + FastAPI `Depends` como adapter |
| C) Conexión por query | Cada método del repo adquiere y libera su propia conexión |

**Por qué NO las otras:**
- **A) Middleware:** Solo funciona para HTTP. Workers, scripts y crons necesitan otro mecanismo. Además, adquiere conexión para TODOS los endpoints — incluso `/health` que no toca BD, desperdiciando conexiones del pool.
- **C) Conexión por query:** Imposible hacer transacciones que cruzan múltiples repos (el UPDATE de un repo y el INSERT de otro no comparten conexión). También más overhead por acquire/release en cada query.

**Decisión:** Opción B — `connection_context` (context manager) + `contextvars` + FastAPI `Depends` como adapter.

**Justificación:**
- **Un solo mecanismo** para todo: HTTP usa `Depends(get_db_connection)` que internamente llama `connection_context`. Workers/scripts llaman `async with connection_context(database)` directamente
- **No desperdicia conexiones:** Solo los endpoints que tienen `Depends` adquieren conexión
- **Testeable:** `app.dependency_overrides` para tests de FastAPI, `connection_context` directo para integration tests
- **Transacciones posibles:** Todos los repos de un request ven la misma conexión via `contextvars`, permitiendo transacciones atómicas

**Consecuencias:**
- (+) Repos son singletons puros (sin `__init__` con DB)
- (+) Workers, scripts y crons usan el mismo mecanismo que HTTP
- (+) Pool configurable (min_size, max_size) según carga
- (-) `contextvars` es implícito — si un developer llama un repo fuera de un `connection_context`, obtiene un `RuntimeError` claro pero en runtime, no en compile time
- (-) El developer debe entender que `get_current_connection()` retorna la conexión del request actual, no una conexión global

---

## ADR-003: Transacciones — Decorator + Context Manager Explícito

**Status:** Aceptado

**Contexto:**
Un use case puede llamar a múltiples repositorios. Si uno falla después de que otro ya insertó datos, la BD queda en estado inconsistente. Necesitamos atomicidad. Pero no todos los use cases son iguales — algunos solo tocan BD, otros llaman a terceros y necesitan la respuesta antes de decidir qué guardar.

**Opciones consideradas:**

| Opción | Descripción |
|---|---|
| A) Transaction manual | Cada use case maneja su propio `async with conn.transaction()` |
| B) Decorator único | `@transactional` wrappea todo el `execute()` |
| C) Decorator + Context Manager | `@transactional` para use cases simples, `transaction_context` explícito para complejos |

**Por qué NO las otras:**
- **A) Transaction manual:** Boilerplate repetido en cada use case. Fácil olvidar el rollback. El use case se llena de código de infraestructura.
- **B) Decorator único:** No funciona para Type 3 (BD + tercero). Si wrappeas todo en una transacción y la llamada HTTP al tercero tarda 5 segundos, la conexión queda bloqueada 5 segundos con un lock en la tabla. Bajo carga, el pool se agota.

**Decisión:** Opción C — `@transactional` + `transaction_context`.

**Justificación:**

Se identificaron 3 tipos de use case:

| Tipo | Ejemplo | Mecanismo |
|---|---|---|
| Tipo 1: Solo BD | CreateLoan, RegisterUser | `@transactional` — simple, limpio |
| Tipo 2: BD + fire-and-forget | ApproveLoan (+ notificación) | `@transactional` — el outbox es BD |
| Tipo 3: BD + tercero que necesita respuesta | DisburseLoan, EvaluateLoan | `transaction_context` explícito — 2 transacciones con llamada HTTP en medio |

Para Type 3, el patrón es:
1. Transaction 1: marcar status intermedio (idempotente)
2. Llamada al tercero (fuera de transacción)
3. Transaction 2: guardar resultado

**Consecuencias:**
- (+) El developer tiene una regla clara: ¿llamas a tercero y necesitas la respuesta? → `transaction_context`. ¿Todo lo demás? → `@transactional`
- (+) Status intermedios (`scoring`, `disbursing`) + reconciliación = red de seguridad para Type 3
- (+) Outbox pattern para fire-and-forget evita llamadas externas dentro de transacciones
- (-) Type 3 requiere más código y más cuidado
- (-) El developer debe elegir correctamente entre los dos mecanismos

---

## ADR-004: Exception Handling — Jerarquía + Decorators + Handler Global

**Status:** Aceptado

**Contexto:**
Sin estrategia de errores, cada developer pone try/catch donde le parece. Errores de BD se exponen al cliente (`asyncpg.UniqueViolationError`). Responses inconsistentes (`{"error": "..."}` vs `{"message": "..."}` vs stack traces). Use cases y controllers llenos de try/catch que oscurecen la lógica de negocio.

**Opciones consideradas:**

| Opción | Descripción |
|---|---|
| A) Try/catch en cada capa | Cada capa catchea y re-lanza sus errores |
| B) Handler global único | Un solo catch-all en FastAPI traduce todo |
| C) Jerarquía + Decorators + Handler | Excepciones tipadas + decorators en repos/services + handler global |

**Por qué NO las otras:**
- **A) Try/catch en cada capa:** Controller tiene try/catch, use case tiene try/catch, repo tiene try/catch. 3 niveles de catch para un solo error. El código se vuelve ilegible. Si alguien olvida un catch, el error sube sin traducir.
- **B) Handler global único:** Funciona, pero el handler necesita `isinstance` checks para saber qué tipo de error es. Si el repo lanza `asyncpg.UniqueViolationError`, el handler global necesita conocer asyncpg — acoplamiento directo entre el handler HTTP y la librería de BD.

**Decisión:** Opción C — Jerarquía tipada + Decorators en infraestructura + Handler global.

**Justificación:**
- **Decorators (`@handle_db_errors`, `@handle_external_errors`)** en repos/services traducen errores de librerías a la jerarquía de la app. El repo puede hacer un try/catch puntual para errores con significado de negocio (ej: `UniqueViolation → AlreadyExistsError`). Todo lo demás → decorator → `DatabaseException(503)`
- **Use cases y controllers:** CERO try/catch. Solo lanzan guardas (`if not entity: raise EntityNotFoundError`). Se leen como libro.
- **Handler global:** Catchea por categoría (`DomainException`, `DatabaseException`, `ExternalServiceException`, `Exception`). Un handler por categoría, cero `isinstance`

**Consecuencias:**
- (+) Use cases y controllers limpios — solo lógica de negocio
- (+) Responses HTTP consistentes siempre
- (+) Agregar un nuevo tipo de error = agregar una clase, no modificar handlers
- (+) Errores de infra nunca se exponen al cliente (503 genérico para BD, 502/504 para externos)
- (-) La jerarquía debe mantenerse coherente — si alguien lanza `Exception` directamente, cae al catch-all (500)
- (-) Los decorators atrapan `AppException` y la dejan pasar — si alguien no entiende esto, puede confundirse

---

## ADR-005: Tipos de dato entre capas — Approach Mixto

**Status:** Aceptado

**Contexto:**
asyncpg retorna `Record` objects. Sin conversión, todo es `record["field"]` — sin autocomplete, sin tipos, typos explotan en runtime. Pero convertir TODO a Pydantic o dataclass tiene costo innecesario para datos que solo se pasan sin procesarlos.

**Opciones consideradas:**

| Opción | Descripción |
|---|---|
| A) Pydantic everywhere | Todo dato se convierte a Pydantic model |
| B) Dict everywhere | Todo queda como Record/dict |
| C) Mixto | Pydantic en fronteras HTTP, dataclass para dominio, dict para pass-through |

**Por qué NO las otras:**
- **A) Pydantic everywhere:** Overhead de validación en cada conversión. Un JOIN que retorna 20 columnas necesita un model con 20 campos solo para pasar datos al response. Pydantic v2 es rápido, pero no gratis — y la mayoría de esos campos nunca se acceden en el use case.
- **B) Dict everywhere:** El use case accede a `loan["status"]` — sin autocomplete, sin tipos, `loan["statos"]` falla en runtime. Para datos que el use case necesita manipular, esto es inaceptable.

**Decisión:** Opción C — Approach mixto.

**Justificación:**

| Dato | Tipo | Dónde vive | Por qué |
|---|---|---|---|
| Request HTTP | Pydantic | `schema/` | Validación de entrada automática |
| Entidad de dominio | dataclass + `from_record` | `entity/` | Autocomplete, tipos, lógica futura |
| Dato de paso (JOINs) | dict | — | Sin conversión innecesaria |
| Response HTTP | Pydantic | `schema/` | Serialización controlada |

**Regla simple:** ¿El use case accede a campos del dato para hacer lógica? → dataclass. ¿Solo lo pasa al response? → dict.

**Consecuencias:**
- (+) Autocomplete y tipos donde importa (use cases)
- (+) Sin overhead para datos que solo se pasan
- (+) `from_record` centraliza la conversión Record→Entity
- (-) Dos tipos de retorno en repos (dataclass para write, dict para query) — el developer debe saber cuál usar
- (-) `schema/` y `entity/` pueden confundirse si no se documenta bien la diferencia

---

## ADR-006: Migraciones con Alembic + Raw SQL (sin ORM)

**Status:** Aceptado

**Contexto:**
No usamos ORM — los repos escriben SQL directo. Pero necesitamos versionar cambios de schema de BD con orden garantizado, upgrade/downgrade, y historial en git.

**Opciones consideradas:**

| Opción | Descripción |
|---|---|
| A) SQLAlchemy ORM + autogenerate | Alembic con modelos SQLAlchemy, migraciones auto-generadas |
| B) Alembic + raw SQL | Alembic como runner, SQL escrito a mano |
| C) Custom scripts | Scripts SQL numerados, ejecutados manualmente |

**Por qué NO las otras:**
- **A) SQLAlchemy ORM + autogenerate:** Introduciría un ORM que contradice la decisión de usar raw queries. Tendríamos models de SQLAlchemy que no se usan para queries pero sí para migraciones — confusión. El equipo tendría que mantener dos fuentes de verdad (models ORM + raw queries).
- **C) Custom scripts:** Sin orden garantizado, sin tracking de qué migración ya corrió, sin downgrade. Re-inventar lo que Alembic ya resuelve.

**Decisión:** Opción B — Alembic como runner de migraciones con SQL puro.

**Justificación:**
- Alembic provee: versionamiento, orden de ejecución, upgrade/downgrade, historial en git, tabla `alembic_version` para tracking
- El developer escribe `op.execute("CREATE TABLE ...")` — SQL puro, sin abstracciones
- Consistente con la filosofía de raw queries: el equipo controla el SQL exacto
- No requiere SQLAlchemy models — solo el runner de Alembic

**Consecuencias:**
- (+) Control total sobre el SQL de las migraciones
- (+) Sin duplicación de schema (no hay models ORM paralelos)
- (+) El equipo solo necesita saber SQL, no SQLAlchemy
- (-) Sin auto-generación: el developer debe escribir upgrade() Y downgrade() manualmente
- (-) Sin detección automática de cambios olvidados — si cambias una query pero no creas migración, falla en runtime
- (-) El flujo requiere disciplina: migración + entity + port + query deben commitearse juntos

---

## ADR-007: CQRS Lite — Separación de repos de lectura y escritura

**Status:** Aceptado

**Contexto:**
Dijimos "1 repo = 1 tabla". Pero cuando un use case necesita datos de varias tablas (ej: préstamo + datos del usuario), caes en N+1 queries: 1 query para loans + N queries para cada user. 100 loans = 101 queries. La solución es un JOIN, pero un JOIN cruza tablas — viola "1 repo = 1 tabla".

**Opciones consideradas:**

| Opción | Descripción |
|---|---|
| A) JOINs en write repos | Permitir JOINs en los repos existentes |
| B) Repos de lectura separados | `LoanRepository` (write, 1 tabla) + `LoanQueryRepository` (read, JOINs) |
| C) CQRS completo | 2 pools de BD (primary + replica), event sourcing |

**Por qué NO las otras:**
- **A) JOINs en write repos:** Mezcla responsabilidades. Un `LoanRepository` con CRUD + JOINs complejos crece descontroladamente. No prepara para escalamiento futuro.
- **C) CQRS completo:** Requiere 2 nodos de BD (primary + replica), event sourcing o change data capture, eventual consistency handling. Complejidad excesiva para el estado actual. No tenemos réplica de BD hoy.

**Decisión:** Opción B — CQRS lite (separación a nivel de código).

**Justificación:**
- **Hoy:** Ambos repos (`LoanRepository` y `LoanQueryRepository`) usan `get_current_connection()` y el mismo pool. La separación es SOLO de código
- **Futuro:** El día que pongan una réplica de BD:
  1. Se crea un segundo pool apuntando a la replica
  2. `LoanQueryRepository` cambia a `get_read_connection()`
  3. No se tocan use cases ni controllers
- **Claridad:** Write repos son CRUD puros (1 tabla, fácil de entender). Query repos son consultas complejas (JOINs, agregaciones, dashboards)

**Consecuencias:**
- (+) Elimina N+1 queries con JOINs en query repos
- (+) Write repos se mantienen simples (1 clase = 1 tabla)
- (+) Preparado para réplica de BD sin refactor
- (+) Use cases declaran qué tipo de datos necesitan (write port vs query port)
- (-) Más clases (2 repos por entidad en vez de 1)
- (-) El developer debe decidir si un nuevo query va en write repo o query repo
- (-) Sin réplica real, la separación es "solo cosmética" hoy — el beneficio futuro es especulativo

---

## ADR-008: Testing — Unit para lógica + Integration para datos

**Status:** Aceptado

**Contexto:**
Todo es singleton. Los repos usan `get_current_connection()` de contextvars. No puedes hacer unit test de un repo sin BD real porque no hay nada que mockear — el SQL es la lógica. Pero para use cases y controllers, un mock del repo basta.

**Opciones consideradas:**

| Opción | Descripción |
|---|---|
| A) Todo unit test | Mockear conexión, cursor, fetchrow — probar que "llama a fetchrow con estos params" |
| B) Todo integration test | BD real para todo, incluyendo use cases y controllers |
| C) Mixto | Unit tests para controller/use case (mocks), integration para repo/service (BD real) |

**Por qué NO las otras:**
- **A) Todo unit test:** Mockear `conn.fetchrow()` solo prueba que escribiste el mock correctamente. Un typo en el SQL pasa todos los unit tests y falla en producción. Los decorators (`@handle_db_errors`) nunca se ejercitan con errores reales.
- **B) Todo integration test:** Lento. Requiere BD levantada para correr cualquier test. Un test de "si el user no existe, lanza error" no necesita BD — es lógica pura. CI se vuelve más lento y frágil.

**Decisión:** Opción C — Mixto con coverage combinado.

**Justificación:**

| Capa | Tipo de test | Qué necesita |
|---|---|---|
| Controller | Unit | Mock del use case (constructor injection) |
| Use Case | Unit | Mock del repo/factory (constructor injection) |
| Repository | Integration | BD real + `connection_context` + rollback |
| Service | Integration | Mock HTTP (`httpx_mock`), no mock BD |
| Decorators | Integration | BD real (para errores reales de asyncpg) |

- **Unit tests:** Rápidos (~ms), sin BD. Prueban lógica de negocio: guardas, orquestación, delegación
- **Integration tests:** Con BD real. Prueban SQL, conversiones, constraints, decorators. Fixture con `connection_context` + rollback para aislamiento
- **Coverage combinado:** `pytest tests/unit --cov` + `pytest tests/integration --cov --cov-append` + `coverage report`

**Consecuencias:**
- (+) Unit tests son rápidos — se pueden correr en cada save
- (+) Integration tests prueban lo que realmente importa en repos: el SQL
- (+) Coverage combinado refleja cobertura real del código
- (-) Necesitas una BD de test (Docker Compose)
- (-) Para use cases con `@transactional`, unit tests usan `__wrapped__` para bypassear el decorator. Para use cases con `transaction_context`, se patchea el context manager
- (-) Dos suites de test = más configuración de CI

---

## ADR-009: Interfaces con Python Protocols (typing.Protocol)

**Status:** Aceptado

**Contexto:**
En Clean Architecture, las capas internas (use case) no deben depender de las externas (repository concreto). El use case debe depender de una abstracción. Python ofrece varias formas de definir contratos.

**Opciones consideradas:**

| Opción | Descripción |
|---|---|
| A) Sin interfaces | El use case recibe el repo concreto. DI por constructor sin abstracción |
| B) ABC (Abstract Base Class) | `class LoanRepoABC(ABC)` con `@abstractmethod`. El repo hereda |
| C) Protocol (duck typing) | `class LoanRepositoryPort(Protocol)`. El repo cumple por firma, sin herencia |

**Por qué NO las otras:**
- **A) Sin interfaces:** El use case importa directamente `LoanRepository`. Si quieres cambiar la implementación, tocas el use case. Si quieres testear, el mock debe imitar la clase concreta. No hay Dependency Inversion.
- **B) ABC:** Requiere herencia (`class LoanRepository(LoanRepoABC)`). Si agregas un método al ABC, TODOS los repos concretos explotan hasta que lo implementen. Más rígido. Python no es Java — la herencia obligatoria se siente antinatural.

**Decisión:** Opción C — Python Protocols (duck typing estructural).

**Justificación:**
- **Sin herencia:** `LoanRepository` no hereda de nada. Cumple el Protocol simplemente por tener los mismos métodos con las mismas firmas
- **Verificable estáticamente:** `mypy --strict` detecta si un repo no cumple un Protocol antes de correr
- **DI pura:** app.py instancia el concreto y lo pasa al use case. El use case solo ve el Protocol. Si cambias la implementación, solo tocas app.py
- **Pythonic:** Protocols son el equivalente Python de interfaces — duck typing con verificación estática

**Consecuencias:**
- (+) Use cases desacoplados de implementaciones concretas
- (+) Tests triviales: cualquier mock que tenga los mismos métodos cumple el Protocol
- (+) mypy/pyright detectan incompatibilidades antes de runtime
- (-) Sin mypy, los errores de Protocol son invisibles — funciona igual que sin interfaces
- (-) Una capa más de archivos (`port/`) que mantener
- (-) Los Protocols deben actualizarse cuando cambia la firma de un repo

---

## ADR-010: Modelo de Entidad — Anémico progresivo

**Status:** Aceptado

**Contexto:**
Clean Architecture sugiere entidades ricas con lógica de negocio. Pero hoy las entidades son simples contenedores de datos (dataclass). ¿Agregamos lógica de negocio a las entidades ahora o después?

**Opciones consideradas:**

| Opción | Descripción |
|---|---|
| A) Entidades ricas desde el inicio | `loan.approve()`, `loan.can_be_disbursed()`, validaciones en la entidad |
| B) Anémico permanente | Solo datos, toda la lógica en use cases, las entidades nunca cambian |
| C) Anémico progresivo | Datos hoy. Lógica se agrega cuando se justifica |

**Por qué NO las otras:**
- **A) Entidades ricas desde el inicio:** Hoy no tenemos suficiente lógica de negocio para justificarlo. Un `loan.approve()` que solo hace `self.status = "approved"` no agrega valor sobre `update_status_if` en el repo. Estaríamos creando abstracciones para lógica que no existe todavía.
- **B) Anémico permanente:** Si la lógica de negocio crece (validaciones de transición de estado, reglas de negocio complejas), todo queda en los use cases. Los use cases crecen y se vuelven difíciles de testear.

**Decisión:** Opción C — Anémico progresivo.

**Justificación:**
- **Hoy:** Dataclass con datos + `from_record()`. Si un `ensure_exists` en el use case basta, no mover esa lógica a la entidad
- **Futuro:** Cuando la lógica de negocio justifique (ej: `loan.can_be_disbursed()` involucra 3+ condiciones), se agrega a la entidad
- **YAGNI:** No crear abstracciones para código que no existe
- **Orgánico:** Las entidades crecen naturalmente cuando el dominio lo requiere

**Consecuencias:**
- (+) Simplicidad hoy — las entidades son triviales de entender
- (+) Sin premature abstraction — solo se agrega lógica cuando se necesita
- (+) Compatible con entidades ricas futuras — el path está preparado
- (-) Hoy no estamos 100% Clean Architecture (las entidades son anémicas)
- (-) Requiere disciplina: el equipo debe reconocer cuándo mover lógica del use case a la entidad

---

## ADR-011: Raw Queries vs ORM

**Status:** Aceptado

**Contexto:**
Necesitamos acceder a PostgreSQL. La decisión entre ORM y raw queries afecta toda la capa de datos, las migraciones, y el modelo mental del equipo.

**Opciones consideradas:**

| Opción | Descripción |
|---|---|
| A) SQLAlchemy ORM | Models, relationships, session management, query builder |
| B) Raw queries con asyncpg | SQL directo, parámetros posicionales ($1, $2) |
| C) Query builder (SQLAlchemy Core) | Builder de queries sin ORM, sin models |

**Por qué NO las otras:**
- **A) SQLAlchemy ORM:** Genera SQL que el developer no controla. Lazy loading puede crear N+1 invisibles. Session management agrega complejidad (flush, commit, expire). El equipo necesita aprender SQLAlchemy además de SQL. Debug de queries generadas es más difícil que debug de SQL que tú escribiste.
- **C) Query builder:** Más portable que raw SQL, pero agrega una abstracción sobre SQL que el equipo ya conoce. No vamos a cambiar de PostgreSQL. El beneficio de portabilidad no justifica la abstracción.

**Decisión:** Opción B — Raw queries con asyncpg.

**Justificación:**
- **Control total:** El developer escribe el SQL exacto que se ejecuta. Sin magia, sin queries invisibles
- **Performance:** asyncpg es el driver PostgreSQL más rápido en Python. Sin overhead de ORM
- **El equipo sabe SQL:** No necesitan aprender una abstracción sobre algo que ya conocen
- **Debug directo:** El SQL que ves en el código es el SQL que se ejecuta. Sin traducciones

**Consecuencias:**
- (+) Performance óptima — asyncpg con prepared statements
- (+) Sin sorpresas — el SQL que escribes es el que corre
- (+) El equipo solo necesita saber SQL + asyncpg
- (-) Sin migraciones automáticas (resuelto con ADR-006: Alembic + raw SQL)
- (-) Sin lazy loading — JOINs explícitos (resuelto con ADR-007: CQRS Lite)
- (-) Sin portabilidad entre BDs — atados a PostgreSQL (aceptable: no planeamos cambiar)
- (-) SQL repetido en repos — sin abstracciones como `.filter()` o `.select()`

---

## ADR-012: Separación de Schema (HTTP DTOs) vs Entity (Dominio)

**Status:** Aceptado

**Contexto:**
Inicialmente teníamos `schema/` con Pydantic models que servían tanto para HTTP validation como para representar entidades de dominio. Esto mezclaba concerns: un `Loan` model tenía campos de request (`provider`), campos de response (`id`, `status`), y campos de dominio (`score`).

**Opciones consideradas:**

| Opción | Descripción |
|---|---|
| A) Un modelo para todo | Pydantic model usado en HTTP y en use cases |
| B) Separar schema/ y entity/ | schema/ solo para HTTP DTOs, entity/ para dominio |
| C) Pydantic para todo pero separado | Pydantic para HTTP y Pydantic para dominio (sin dataclass) |

**Por qué NO las otras:**
- **A) Un modelo para todo:** El model necesita campos opcionales para cubrir request, response Y dominio. `amount: float | None` porque el response no siempre lo incluye, pero el dominio siempre lo tiene. Confusión sobre qué campos son requeridos en qué contexto.
- **C) Pydantic para todo:** Validación de Pydantic tiene costo. En el dominio no necesitamos re-validar datos que ya vienen de la BD. Además, Pydantic models son immutables por default — si la entidad necesita mutarse (futuro: entidades ricas), es friction innecesaria.

**Decisión:** Opción B — `schema/` para HTTP DTOs (Pydantic), `entity/` para dominio (dataclass).

**Justificación:**
- **schema/:** Pydantic BaseModel. Solo valida requests y serializa responses. Vive en la frontera HTTP
- **entity/:** Python dataclass. Datos de dominio + `from_record()`. Usado dentro de use cases para autocomplete y tipos
- **Separación clara:** HTTP concerns (validación, serialización) no contaminan el dominio. El dominio no conoce Pydantic

**Consecuencias:**
- (+) Cada capa tiene su tipo de dato apropiado
- (+) Las entidades pueden crecer a entidades ricas sin restricciones de Pydantic
- (+) Los schemas HTTP pueden cambiar sin afectar el dominio
- (-) Más archivos (entity/ + schema/ en vez de solo schema/)
- (-) Conversión necesaria: `asdict(entity)` → `Response(**asdict(entity))`. Costo mínimo

---

## ADR-013: Dependency Injection — Constructor Manual en app.py

**Status:** Aceptado

**Contexto:**
Cada clase necesita sus dependencias (repos, services, factories). Necesitamos un mecanismo de inyección que sea testeable y no acople las clases entre sí.

**Opciones consideradas:**

| Opción | Descripción |
|---|---|
| A) FastAPI Depends para todo | Usar `Depends()` para inyectar repos, use cases, etc. |
| B) Constructor injection + wiring manual en app.py | Cada clase recibe deps en `__init__`, app.py cablea todo |
| C) DI Container library | python-inject, dependency-injector, etc. |

**Por qué NO las otras:**
- **A) FastAPI Depends para todo:** Acopla todo al framework. Los use cases no deberían conocer FastAPI. Además, `Depends()` crea instancias por request — queremos singletons para controllers, use cases y repos.
- **C) DI Container library:** Agrega una dependencia y complejidad que no necesitamos. El wiring manual en app.py es ~30 líneas y es completamente explícito. No hay magia de auto-discovery ni decorators especiales.

**Decisión:** Opción B — Constructor injection con wiring manual en app.py.

**Justificación:**
- **Explícito:** app.py es el único archivo donde se conocen las clases concretas. Puedes leerlo y ver exactamente qué recibe cada clase
- **Testeable:** En tests, creas `UseCase(mock_repo)` — sin configurar containers ni overrides
- **Sin magia:** No hay auto-wiring, no hay decorators de DI, no hay runtime reflection
- **Singletons naturales:** Instancias una vez en app.py, reutilizas para siempre

**Consecuencias:**
- (+) Zero dependencias extra
- (+) Tests triviales: `UseCase(AsyncMock())` y listo
- (+) El developer ve todo el wiring en un solo archivo
- (-) Si la app crece mucho, app.py puede volverse largo. Mitigation: separar en módulos de wiring si llega a 100+ líneas
- (-) Sin auto-wiring: agregar un nuevo use case requiere 3 líneas en app.py (instanciar repo, instanciar use case, instanciar controller)

---

## ADR-014: Outbox Pattern para notificaciones fire-and-forget

**Status:** Aceptado

**Contexto:**
Después de aprobar o dispersar un préstamo, necesitamos enviar una notificación al usuario (SMS, email, push). Si la llamada al servicio de notificación falla, ¿revertimos la dispersión? No — el dinero ya salió. Necesitamos un mecanismo que garantice que la notificación se envíe eventualmente, sin acoplar la transacción de BD al servicio externo.

**Opciones consideradas:**

| Opción | Descripción |
|---|---|
| A) Llamada directa | Llamar SQS/SMS directamente en el use case |
| B) Saga pattern | Orquestador de pasos con compensaciones |
| C) Outbox pattern | Guardar mensaje en tabla de BD dentro de la misma transacción. Worker envía después |

**Por qué NO las otras:**
- **A) Llamada directa:** Si la transacción de BD hace commit pero la llamada a SQS falla → dato guardado pero notificación perdida. Si la llamada a SQS tiene éxito pero la transacción falla → notificación enviada para un dato que no existe. No hay atomicidad.
- **B) Saga pattern:** Complejidad excesiva para notificaciones. Sagas son para operaciones distribuidas que necesitan compensación (ej: reserva de vuelo + hotel). Una notificación SMS no necesita compensación — si falla, se reintenta.

**Decisión:** Opción C — Outbox pattern.

**Justificación:**
- **Atomicidad:** El mensaje se guarda en la tabla `outbox` dentro de la misma transacción que el cambio de BD. Si la transacción falla, el mensaje nunca se guardó → nunca se envía. Si la transacción tiene éxito, el mensaje está garantizado en la tabla
- **Resiliencia:** Un worker lee mensajes pending y los envía. Si falla, reintenta. Después de N reintentos, mueve a `dead_letter` para revisión manual
- **Desacoplado:** El use case no conoce SQS, SMS ni email — solo llama `outbox_repo.save("notification", payload)`

**Consecuencias:**
- (+) Garantía de que cada transacción exitosa genera su notificación
- (+) Reintentos automáticos con dead letter para mensajes poison
- (+) El use case no se acopla al mecanismo de envío
- (-) Eventual consistency: la notificación no se envía en el mismo request — hay un delay (1-2 segundos típicamente)
- (-) Requiere un worker corriendo (cron o proceso background)
- (-) La tabla outbox crece — necesita limpieza periódica de mensajes `sent`

---

## Resumen de decisiones

| ADR | Decisión | Alternativa principal rechazada |
|---|---|---|
| 001 | Full async | Sync con threads |
| 002 | Context manager + contextvars + Depends | Middleware |
| 003 | @transactional + transaction_context | Decorator único para todo |
| 004 | Jerarquía + decorators + handler global | Try/catch en cada capa |
| 005 | Mixto (Pydantic + dataclass + dict) | Pydantic everywhere |
| 006 | Alembic + raw SQL | SQLAlchemy ORM + autogenerate |
| 007 | CQRS Lite (write + query repos) | JOINs en write repos |
| 008 | Unit (controller/UC) + Integration (repo) | Todo unit test con mocks |
| 009 | Python Protocols | ABC / Sin interfaces |
| 010 | Anémico progresivo | Entidades ricas desde inicio |
| 011 | Raw queries con asyncpg | SQLAlchemy ORM |
| 012 | schema/ (HTTP) + entity/ (dominio) | Un modelo para todo |
| 013 | Constructor injection + app.py | DI Container library |
| 014 | Outbox pattern | Llamada directa a SQS/SMS |
