# ADR-0005: Event Bus Architecture

## Document Information

**ADR ID:** ADR-0005
**Title:** Event Bus Architecture
**Status:** ACCEPTED
**Date:** 2026-08-07
**Decision Type:** Architecture Decision
**Category:** Architecture Decision
**Decision Owner:** AIOS Project Owner
**Approval Authority:** AIOS Governance Authority
**Implementation Status:** Pending Implementation
**Version:** 1.0.0

---

# 1. Context

AIOS-103 defines the Event Bus as the communication backbone of AIOS.

The Event Bus allows components, AI agents, and services to exchange events without creating direct dependencies between them.

The Core Engine startup sequence defined in AIOS-104 requires the Event Bus to be initialized before AI agents are loaded:

```text
Load Configuration

        ↓

Initialize Database

        ↓

Initialize Event Bus

        ↓

Load AI Agents
```

The Agent Framework defined in AIOS-604 requires agents to communicate through structured messages containing Sender, Receiver, Timestamp, Request Identifier, Payload, Confidence, and Status.

The Database Layer defined in AIOS-606 and ADR-0001 establishes the Repository Pattern with a System Database Domain that stores logs, events, and configuration history.

AIOS-103 explicitly lists future expansion capabilities including distributed event systems, cloud messaging, real-time market streaming, and multiple AIOS instances.

---

# 2. Problem Statement

The AIOS documentation defines what the Event Bus must do, but does not define how it shall be implemented in Phase 1.

The following questions remain unresolved:

* Should the Event Bus run inside the application process or require an external message broker?
* Should event dispatch be synchronous or asynchronous?
* Is event ordering guaranteed?
* What delivery guarantees are provided to subscribers?
* What happens when a subscriber fails?
* How are failed events retried?
* Are events persisted, and if so, where?
* Where are the integration boundaries of the Event Bus?

This ambiguity blocks Phase 1 implementation because the Core Engine, Agent Framework, and Database Layer cannot be built consistently while the communication backbone is undefined.

---

# 3. Decision Drivers

The decision shall satisfy the following drivers:

* **Modularity:** Components must communicate through controlled interfaces without direct dependencies (AIOS-002, AIOS-103).
* **Testability:** Phase 1 communication must be deterministic and reproducible in tests.
* **Traceability:** Every event must be logged and traceable (AIOS-103).
* **Failure Safety:** A failing component must never corrupt decisions (AIOS-104, AIOS-604).
* **Operational Simplicity:** Phase 1 is a single-user, paper-trading system and must avoid unnecessary operational complexity (AIOS-101).
* **Future Scalability:** The architecture must allow migration to a distributed event system without redesign (AIOS-103).
* **Governance Compliance:** Events carrying investment decisions must respect the gates defined in ADR-0002 and ADR-0004.

---

# 4. Alternatives Considered

## Alternative 1: In-Process Event Bus

The Event Bus runs inside the AIOS application process.

### Advantages

* Minimal operational complexity.
* Low latency with no network overhead.
* Deterministic behavior suitable for testing.
* Simple deployment for a single-user system.
* Direct integration with the Core Engine lifecycle.

### Disadvantages

* Limited to a single process.
* No built-in durability across restarts.
* Requires explicit design for ordering and failure isolation.
* Migration to distributed systems requires a new implementation.

---

## Alternative 2: External Message Broker

The Event Bus is provided by an external broker such as RabbitMQ, Kafka, or Redis Streams.

### Advantages

* Durable and persistent messaging.
* Strong delivery and ordering capabilities.
* Supports future distribution and multiple instances.
* Operational features such as reconnection and dead-letter handling.

### Disadvantages

* Additional infrastructure to install, configure, and operate.
* Higher complexity for a single-user paper-trading system.
* Network failure modes must be handled.
* More difficult local development and testing.
* Overkill for Phase 1 scope.

---

## Alternative 3: Hybrid Approach

Use an in-process Event Bus for Phase 1 with an abstraction layer that permits a future external broker.

### Advantages

* Provides the simplicity of the in-process option for Phase 1.
* Preserves migration capability to a broker later.
* Keeps integration boundaries explicit from the start.
* Aligns with AIOS-103 future expansion plans.

### Disadvantages

* Requires a stable bus interface designed today.
* The abstraction must not add unnecessary complexity in Phase 1.
* Risk of over-engineering if the migration is never needed.

---

# 5. Decision

AIOS adopts the **In-Process Event Bus** for Phase 1, implemented behind a stable bus interface that preserves the ability to replace it with an external broker in a future version without redesigning components.

This decision balances Phase 1 simplicity with the AIOS-103 expansion requirement.

---

## 5.1 Sync/Async Model

* Event publishing and delivery are **asynchronous**.
* Publishers do not block on subscriber processing.
* Subscribers are notified by the bus and process events independently.

A synchronous **request/reply** channel is available on the same bus for coordination flows where a result is required before continuing, such as Decision Engine validation requests. Request/reply calls are explicit and bounded by a timeout.

---

## 5.2 Event Ordering

* Events are ordered **per event type and per source** in FIFO order.
* No global ordering across different event types is guaranteed.
* Components that depend on sequence shall rely on the Event ID and Timestamp defined in AIOS-103.
* FIFO is guaranteed within the same source and event type.
* Redelivery caused by the at-least-once guarantee may introduce a delay or reprocessing of an earlier event.
* Consumers shall handle redelivery through the Event ID and idempotent processing.

---

## 5.3 Delivery Guarantees

* The bus provides **at-least-once** delivery to registered subscribers.
* Subscribers must be **idempotent** by Event ID to tolerate redelivery.
* Every event is persisted to the event log before dispatch (see 5.5).

---

## 5.4 Retry Strategy

* Subscriber failures trigger a **bounded retry** with exponential backoff.
* Retry count and backoff parameters are configurable.
* Retried events are logged with their retry attempt number.
* After the maximum retry count, the event is moved to a **dead-letter state** and reported to Core Engine monitoring.

---

## 5.5 Persistence Requirements

* The in-process bus itself is **not a durable queue**.
* Every published event shall be persisted to the System Database Domain via the EventRepository **before dispatch**, per ADR-0001 and AIOS-606.
* Persisted events satisfy the audit, traceability, and explainability requirements of AIOS-103.

---

## 5.6 Error Handling

* A failing subscriber must **not** crash the bus or block other subscribers.
* Errors are logged with the Event ID, subscriber identity, and failure details.
* Failed events are tracked and reported to Monitoring.
* No event that carries an investment decision may proceed when its mandatory gates are not satisfied (ADR-0002, ADR-0004).

---

## 5.7 Integration Boundaries

* The Event Bus is the **only** communication path between components.
* No component may call another component directly (AIOS-002, AIOS-103).
* External boundaries, such as data providers and the paper-trading broker, are wrapped in adapter interfaces that translate external calls into bus events.
* The bus exposes a stable public interface so the in-process implementation can be replaced by an external broker in a future version without changing components.

---

## 5.8 Security Rules

* The Event Bus shall verify the permission of a **Publisher** before allowing it to publish an event.
* The Event Bus shall verify the permission of a **Subscriber** before allowing it to subscribe to an event type.
* An Agent or Component that is not authorized to send or receive a given event type must be prevented from doing so.
* Any unauthorized attempt to publish or subscribe shall be recorded in the **Audit Log**.

---

# 6. Consequences

## Positive Consequences

* Simple and deterministic communication for Phase 1.
* Components remain independent and testable.
* All events are logged and traceable.
* Failure isolation protects decision integrity.
* Future migration to a distributed broker remains possible without redesign.

---

## Negative Consequences

* Single-process limitation in Phase 1.
* No durability across process restarts; the event log mitigates but does not replace a durable queue.
* Ordering guarantees are limited to per-event-type FIFO.

---

## Risks

* Idempotency violations by subscribers causing duplicate processing.
* Subscriber failures starving the bus under load.
* Retry storms on persistent infrastructure failures.
* Incomplete event persistence reducing auditability.
* Over-abstraction of the bus interface delaying Phase 1.

These risks shall be managed through interface enforcement, idempotent handler validation, monitoring, and governance review during development.

---

# 7. Related Documents

* AIOS-002_PROJECT_CONSTITUTION
* AIOS-101_SYSTEM_ARCHITECTURE
* AIOS-103_EVENT_BUS_DESIGN
* AIOS-104_CORE_ENGINE_DESIGN
* AIOS-401_SYSTEM_DESIGN
* AIOS-604_AGENT_FRAMEWORK
* AIOS-606_DATABASE_LAYER
* AIOS-902_DECISION_POLICY
* ADR-0001_DATABASE_SELECTION
* ADR-0002_DECISION_AUTHORITY
* ADR-0003_STRUCTURE_ALIGNMENT
* ADR-0004_AI_AGENT_INTELLIGENCE_ARCHITECTURE

---

# 8. Change Log

**Version:** 1.0.0

**Change:** Initial formal ADR proposal for the AIOS Event Bus architecture.

---

**Version:** 1.0.1

**Change:** Persistence policy unified to before dispatch; added Event Bus security rules; clarified redelivery behavior under at-least-once delivery.

---

**Version:** 1.0.2

**Change:** ADR formally accepted after governance review.

---

**ADR Status:** ACCEPTED
