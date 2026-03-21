# Operators Architecture

## Purpose

The operator framework defines future human and autonomous control personas without introducing trading logic into the current runtime.

## Confirmed Current State

- `operators/base_operator.py` defines the common interface:
  - `observe()`
  - `simulate()`
  - `execute()`
- Placeholder operators now exist for:
  - Nightwing
  - Red Hood
  - Red Robin
  - Robin
- These classes contain docstrings and placeholders only.

## Planned Future State

- Operators will consume Batcave analytics, governance checks, and reviewed execution adapters.
- Mode transitions will distinguish observation, simulation, and execution authority.
- Nightwing will remain externally managed because it lives in a separate repository.

## Confirmed vs Planned

Confirmed:

- No operator performs trading or runtime mutation.
- The framework establishes a shared interface for later expansion.

Planned:

- Policy-aware operator orchestration.
- Human approval boundaries for execution-capable operators.
- Cross-repo contracts for Nightwing interoperability.

## Design Principle

Operators should remain downstream of governance and analytics. GORDON and HARVEY must mature before operator execution surfaces are reviewed for runtime insertion.
