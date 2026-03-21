# GORDON Integration

## Purpose

GORDON is the Batcave governance and runtime control module. Its current role is to provide a minimal but explicit control plane for kill switch inspection, lock-file awareness, audit logging, and health reporting.

## Confirmed Current State

- `core/gordon.py` exists and is self-contained.
- Kill switch detection is based on `storage/kill_switch.flag`.
- Runtime guard inspection reads `storage/engine.lock` and reports status information.
- GORDON writes append-only audit records to `storage/logs/gordon_audit.jsonl`.
- `core/gordon_integration.py` now provides non-invasive scaffolding for future runtime insertion.

## Planned Future State

- `engine.run_engine()` should perform a pre-run security check before work begins.
- Accepted runs should emit `engine_start` audit events.
- Runtime exceptions should emit `engine_error` audit events.
- Clean shutdown paths should emit `engine_stop` audit events.
- Governance decisions should become visible to operator and dashboard layers only after runtime insertion is reviewed by a human.

## Confirmed vs Planned

Confirmed:

- GORDON can inspect current runtime state without changing behavior.
- Integration points are documented in code via `recommended_integration_points()`.

Planned:

- Direct invocation inside `engine.run_engine()`.
- Enforcement of `ready == false` states.
- Cross-module governance reporting for dashboards or external operators.

## Recommended Integration Surface

The canonical runtime path is `engine.run_engine()`. The recommended insertion points are:

1. Before lock-file creation: `pre_run_security_check()`
2. After run acceptance: `record_engine_start()`
3. In exception handling: `record_engine_error(...)`
4. In final shutdown handling: `record_engine_stop()`

## Implementation Boundary

This repository currently contains scaffolding only. No GORDON integration has been activated in the runtime path.
