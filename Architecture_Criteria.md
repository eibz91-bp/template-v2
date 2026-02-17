# Architecture Criteria

A set of software practices and ideas we share as a team. They are not laws — they are the starting point that guides our decisions.

Each criterion has a core **idea** that defines it: what it means and why it matters.

The **implementation** describes ways to put the criterion into practice. Each project and each team decides which ones to adopt and how to adapt them to their context.

---

## The 9 criteria

1. Business doesn't depend on technology
2. Code reads without effort
3. Dependencies are injected, not created
4. Errors express business problems
5. Entities own their data
6. Decisions are documented and can be challenged
7. Discipline holds everything together
8. Complexity is added when it hurts
9. AI accelerates, humans decide

---

## 01 — Business doesn't depend on technology

> *Have you ever updated a dependency and broken logic that had nothing to do with it?*

**Idea**

Business logic doesn't break when you change a library, a framework, or a database. A loan knows it can be approved — it doesn't know it lives in PostgreSQL.

**Implementation**

- Layer separation with strict dependency direction
- Import rules verified automatically in CI

---

## 02 — Code reads without effort

> *Have you ever opened a 300-line controller with nested try/catch blocks and couldn't find the actual logic?*

**Idea**

You open a file and understand what it does without opening 4 others. Top to bottom, like reading a book.

**Implementation**

- 1 class = 1 operation
- Simple guards. Factory/Strategy instead of if/else
- Zero try/catch in business logic

---

## 03 — Dependencies are injected, not created

> *Have you ever needed to spin up the entire infrastructure just to test a use case, and it took minutes?*

**Idea**

A class receives what it needs from the outside. It doesn't build it. This allows testing any piece in isolation and replacing any component without touching the one that uses it.

**Implementation**

- Constructor injection + centralized wiring
- Formal contracts with interfaces or Protocols

---

## 04 — Errors express business problems

> *Have you ever seen one endpoint return {"error": "..."}, another {"message": "..."}, and a third one a raw stack trace?*

**Idea**

"Entity not found" is business. 404 is HTTP. They are different things. Exceptions say what happened. Each protocol decides how to communicate it.

**Implementation**

- Typed exceptions without HTTP status codes
- Handler per protocol with centralized mapping
- Decorators that translate infrastructure errors to domain

---

## 05 — Entities own their data

> *Have you ever found the same validation copied in 3 files, and only 2 were updated?*

**Idea**

"Can this loan be disbursed?" — the loan knows the answer, not the use case. The entity's rules live in the entity.

**Implementation**

- Entities as classes with pure data
- Validation methods when logic repeats in 2+ use cases

---

## 06 — Decisions are documented and can be challenged

> *Have you ever asked "why was it done this way?" and the answer was "it's always been like that"?*

**Idea**

Every decision has a reason. Without a record, the same decisions get re-discussed every 6 months. Documenting is not just recording what was chosen — it's making explicit what was sacrificed and when it's worth reopening the decision.

**Implementation**

- Informal record: decisions and reasons in a README
- Formal ADRs: context, options, accepted consequences

---

## 07 — Discipline holds everything together

> *Have you ever seen a project start clean and a year later nobody wants to touch it?*

**Idea**

The best architecture degrades if someone puts logic in a controller "because it's faster". Rules exist so you don't have to decide every time.

**Implementation**

- Clear conventions: what belongs in each layer
- Code review with architecture checklist
- Automated verification in CI

---

## 08 — Complexity is added when it hurts

> *Have you ever spent weeks building infrastructure that was never used?*

**Idea**

Every piece has a cost. That cost is only justified when it solves a real pain. If it doesn't hurt, don't implement it.

**Implementation**

- Ports → when there are 2+ implementations
- Cache → when the DB is the bottleneck
- Each piece with its own concrete adoption trigger

---

## 09 — AI accelerates, humans decide

> *Have you ever spent 80% of your time creating files and boilerplate instead of thinking about business?*

**Idea**

Clear rules = AI can follow them. The developer stops writing boilerplate and reviews business decisions. AI generates, humans have the final word.

**Implementation**

- Conventions document that AI follows
- Complete canonical example as a reference pattern

---

## It's not about the architecture. It's about the ideas behind it.

Tools change. Frameworks get replaced.
Ideas remain.