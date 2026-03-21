# HARVEY Analytics

## Purpose

HARVEY is the local analytics persistence layer for Batcave opportunity records. It ingests append-only opportunities into SQLite and now exposes a first set of read-only analytics helpers.

## Confirmed Current State

- HARVEY ingests opportunity records from `storage/logs/opportunities.jsonl`.
- HARVEY stores normalized signal rows in `storage/batman.db`.
- HARVEY refreshes `scanner_stats` during ingestion.
- Read-only analytics helpers are now available:
  - `get_top_edges(limit=10)`
  - `get_scanner_performance()`
  - `get_asset_statistics()`
  - `get_venue_statistics()`
  - `get_signal_type_statistics()`

## Planned Future State

- Additional aggregates for quality, recency, and cross-scanner attribution.
- Time-windowed analysis for operator and dashboard consumption.
- Reviewed schema extensions for richer venue and asset normalization if the current signal payload evolves.

## Confirmed vs Planned

Confirmed:

- Ingestion behavior is unchanged.
- Analytics helpers only read from the existing HARVEY schema.
- Scanner performance can be surfaced from CLI or future dashboards without modifying the runtime path.

Planned:

- Historical trend metrics and edge decay analytics.
- Governance overlays that combine HARVEY telemetry with GORDON status.

## Notes on Edge Ordering

`get_top_edges()` sorts by absolute edge magnitude. This allows analysts to see the strongest positive or negative dislocations first without introducing trading behavior or policy decisions.
