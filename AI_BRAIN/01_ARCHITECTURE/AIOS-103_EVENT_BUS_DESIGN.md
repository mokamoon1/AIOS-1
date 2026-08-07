# AIOS-103: Event Bus Design

## Overview
The Event Bus is the central nervous system of AIOS, enabling decoupled communication between components.

## Design Goals
- **Loose Coupling**: Publishers and subscribers are independent.
- **High Throughput**: Support for high-frequency event streaming.
- **Reliability**: Guaranteed delivery with at-least-once semantics.
- **Observability**: Full traceability of event flows.

## Event Structure
```json
{
  "eventId": "uuid",
  "eventType": "domain.event.name",
  "timestamp": "ISO8601",
  "source": "component-name",
  "payload": {},
  "metadata": {
    "correlationId": "uuid",
    "causationId": "uuid"
  }
}
```

## Topology
- **Topics**: Hierarchical topic naming (e.g., `aios.agents.task.completed`)
- **Partitions**: Sharded by event type or agent ID for parallelism.
- **Consumer Groups**: Load-balanced consumption within services.

## Delivery Guarantees
- At-least-once delivery (default)
- Exactly-once processing (optional, idempotent consumers)

## Backpressure
- Dynamic buffer sizing
- Circuit breaker patterns
- Dead letter queues for failed events

## References
- AIOS-101: System Architecture
- AIOS-104: Core Engine Design
