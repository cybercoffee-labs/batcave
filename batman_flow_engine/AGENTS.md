# Batcave Agent Guidance

## Architecture Overview

Batcave is the verified Batman runtime for governance-aware market intelligence and operator scaffolding.

- `engine.run_engine()` is the canonical runtime entry point.
- `engine.py` should be treated as protected runtime code and must not be modified casually.
- HARVEY is the local analytics and persistence layer for opportunity records.
- GORDON is the local governance and runtime control layer for kill switch, audit, and runtime guard checks.
- Nightwing is a separate repository and is not part of this codebase's direct runtime modifications.

## Governance Before Dashboard Work

Governance modules must be added before dashboard-first work. Safety, auditability, runtime control, and analytics scaffolding take priority over presentation layers and dashboard-driven integration.

## Safe Unattended Codex Tasks

Codex can safely perform these unattended tasks:

- Add new governance modules that are not wired into runtime yet.
- Add analytics helpers that read from existing HARVEY data stores.
- Add operator scaffolding with placeholders and docstrings only.
- Add documentation, diagrams, and CLI utilities that do not mutate runtime behavior.
- Run lightweight validation such as `py_compile` and import checks.

## Do Not Modify Without Review

The following areas require explicit human review before modification:

- `engine.py`
- `runner.py`
- `tools/run_loop.py`
- Scanner logic and signal calculations
- Runtime integration points that change execution flow
- Any code that could place or simulate trades beyond placeholder structure

## Current Boundaries

- Prefer additive modules over edits to critical runtime files.
- If future integration is needed, document the insertion points first.
- Keep analytics helpers read-only unless a reviewed migration explicitly requires schema changes.
