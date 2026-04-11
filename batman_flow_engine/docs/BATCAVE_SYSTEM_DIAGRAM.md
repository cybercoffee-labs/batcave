# Batcave System Diagram

## Confirmed Current State

- `engine.run_engine()` is the canonical runtime.
- Scanners and signal logic feed the engine result and opportunity log.
- HARVEY ingests opportunity records into SQLite and exposes read-only analytics helpers.
- GORDON provides standalone governance helpers and runtime state inspection.
- Nightwing is external to this repository.

## Planned Future State

- GORDON integration hooks will be inserted into `engine.run_engine()` after review.
- Operators will consume governance and analytics outputs.
- Dashboard and external control surfaces will remain downstream of governance-first controls.

## Confirmed vs Planned

Confirmed:

- Runtime remains centered on `engine.run_engine()`.
- Governance and analytics scaffolding can now be developed without changing runtime behavior.

Planned:

- Reviewed runtime insertion of GORDON checks and audit events.
- Richer operator workflows and dashboard surfaces.

## Diagram

```markdown
                +----------------------+
                |   Nightwing Repo     |
                |  External Operator   |
                +----------+-----------+
                           |
                           | planned contract
                           v
+--------------------+   +----------------------+   +----------------------+
|  Governance Layer  |   | Canonical Runtime    |   |  Analytics Layer     |
|      GORDON        |<->| engine.run_engine()  |<->|       HARVEY         |
| kill switch        |   | scanners + signals   |   | SQLite + summaries   |
| runtime guard      |   | opportunity logging  |   | read-only analytics  |
| audit + health     |   +----------+-----------+   +----------+-----------+
+---------+----------+              |                          |
          |                         |                          |
          | planned                 | confirmed                | planned
          v                         v                          v
   +------+-------------------------------+         +----------------------+
   |         Operators (local)            |         | Dashboards / CLI     |
   | Robin / Red Robin / Red Hood         |         | health + reporting   |
   | observe / simulate / execute         |         | downstream surfaces  |
   +--------------------------------------+         +----------------------+
```

## Boundary Statement

This diagram distinguishes confirmed components from planned integrations. It should be used as architecture guidance, not as evidence that runtime integration has already occurred.
