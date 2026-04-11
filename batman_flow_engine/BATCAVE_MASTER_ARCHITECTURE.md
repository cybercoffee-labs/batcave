# BATCAVE Economic Flow Intelligence Lab

## 1. Purpose

BATCAVE is not just a trading bot or a P2P scanner.

It is an economic flow intelligence lab designed to:

- detect inefficiencies across assets, markets, and jurisdictions
- map liquidity, friction, and transfer paths
- build durable research datasets
- evaluate opportunities with governance, compliance, and safety controls
- evolve into a platform for specialized operators

The target form is an Economic Flow Observatory: a system that models the economy as a multi-layer graph of assets, markets, currencies, intermediaries, and signals.

## 2. Conceptual Model

The economy is treated as a flow graph.

### Nodes

- fiat currencies: USD, MXN, ARS, COP, VES
- digital assets: BTC, ETH, SOL, USDT
- traditional assets: ETFs, equities, bonds, commodities
- intermediaries: exchanges, P2P merchants, banks, brokers
- markets: spot, futures, funding, P2P, FX, macro

### Edges

- spread
- basis
- premium
- friction
- liquidity
- depth
- correlation
- risk transfer
- opportunity signal

### Core questions

- where is liquidity concentrated
- where is the edge
- which markets are misaligned
- which signals are actionable
- which patterns persist through time

## 3. Persona Architecture

### BATMAN — Intelligence Core

- Responsibilities: run scanners, detect opportunities, emit canonical signals, persist artifacts, prioritize edges.
- Current repo state: implemented in `engine.py` with canonical runtime `engine.run_engine()`.
- Current capabilities: cross-exchange, basis/funding, and P2P LATAM scanning; SQLite persistence; cycle reports; Ollama enrichment.
- Expected evolution: canonical signal versioning, richer payloads, quality-aware ranking, downstream-ready contracts.

### BATCOMPUTER — Detection Fabric

- Responsibilities: encapsulate scanner logic, compare markets, detect dislocations, emit observable events.
- Current repo state: implemented as `core/scanner_cross_exchange.py`, `core/scanner_basis.py`, and `core/p2p_latam.py`.
- Expected evolution: per-market tuning, noise suppression, macro/FX/ETF/commodities scanners, event deduplication.

### ALFRED — Data Quality Layer

- Responsibilities: freshness checks, payload validation, feed degradation detection, data-quality scoring.
- Current repo state: implemented in `core/alfred.py` with `dq_score` reporting and append-only quality logs.
- Expected evolution: source-specific rules, historical quality metrics, schema/version enforcement, degradation alerting.

### BARBARA — Narrative / Context Intelligence

- Responsibilities: translate signals into explanations, summarize patterns, contextualize edge, produce interpretable intelligence.
- Current repo state: partial via `core/ollama_intel.py` and `core/news_intel.py`.
- Expected evolution: per-market explanations, narrative/risk tagging, executive reports, tentative causal context.

### HARVEY — Memory / Ledger / Signal Analytics

- Responsibilities: store signals, maintain history, expose analytics, serve as the research ledger.
- Current repo state: implemented in `core/harvey.py` with SQLite ingestion and read-only scanner analytics.
- Expected evolution: feature joins, posterior labeling, longitudinal analytics, scanner/market/regime outcomes.

### LUCIUS — Compliance / Policy Engine

- Responsibilities: operational windows, jurisdiction limits, exposure rules, AML flags, policy enforcement.
- Current repo state: partial in `core/lucius.py`; not part of the canonical runtime gating path in this repo.
- Expected evolution: stronger policy authority, market-specific policies, dynamic limits, tighter operator integration.

### GORDON — Safety / Security / Incident Control

- Responsibilities: kill switch, runtime health, stale-data policy, incident logging, recovery controls.
- Current repo state: standalone implementation in `core/gordon.py` plus future runtime insertion scaffolding in `core/gordon_integration.py`.
- Expected evolution: real runtime integration, heartbeat state, robust stop conditions, centralized system visibility.

### COMMANDER — Control Plane / Orchestration

- Responsibilities: coordinate Batman and operators, manage jobs and priority, supervise scheduler state.
- Current repo state: partial through `runner.py` and `tools/run_loop.py`.
- Expected evolution: explicit control plane, retries/backoff/timeouts, health-aware scheduling, formal subsystem coordination.

### VICKI — Reporting / Distribution / Visualization

- Responsibilities: local dashboards, research reporting, snapshots, flow and graph visualization.
- Current repo state: partial through `app.py`, `graph_engine.py`, `live_graph.py`, `p2p_flow_dashboard.py`, and alerts/report artifacts.
- Expected evolution: unified local command center, heatmaps, flow maps, consolidated reports, graph-native observability.

### NIGHTWING — Primary Operator

- Responsibilities: consume Batman signals, apply compliance, evaluate opportunities, log decisions, generate research features.
- Current repo state: external repository by design; only local scaffolding/contracts are kept here.
- Expected evolution: event-oriented sampling, serious paper mode, stronger fresh/stale transitions, true multi-pair operation.

### RED HOOD — Future Spot Operator

- Responsibilities: specialized spot execution with its own ruleset and risk integration.
- Current repo state: scaffold only in `operators/red_hood.py`.

### RED ROBIN — Future Basis / Futures Operator

- Responsibilities: consume basis signals and study funding, carry, and futures dislocations.
- Current repo state: scaffold only in `operators/red_robin.py`.

### ROBIN — Future Macro Operator

- Responsibilities: consume macro, ETF, bonds, and regime signals.
- Current repo state: scaffold only in `operators/robin.py`.

## 4. Technical Architecture

### Canonical runtime

`engine.run_engine()` remains the canonical protected runtime entrypoint.

Current flow:

```text
config.yaml
  -> load_config()
  -> engine.run_engine()
  -> _build_engine_result()
     -> market data collection
     -> cross-exchange scanner
     -> P2P LATAM scanner
     -> basis scanner
  -> _enrich_runtime_metadata()
     -> BARBARA / Ollama enrichment
     -> ALFRED data-quality checks
  -> _persist_run()
     -> latest snapshot
     -> reports
     -> alerts
  -> HARVEY ingest_opportunities()
     -> SQLite persistence
```

### Canonical artifacts

- `storage/latest.json`
- `storage/prev.json`
- `storage/alerts.json`
- `storage/logs/opportunities.jsonl`
- `storage/logs/data_quality.jsonl`
- `storage/logs/gordon_audit.jsonl`
- `storage/batman.db`

### Read-only observatory helpers

This repo also exposes a read-only architecture view via:

- `core/observatory.py`
- `tools/architecture_status.py`

These helpers summarize persona maturity, HARVEY telemetry, and GORDON status without changing runtime behavior.

## 5. Current Boundaries

- `engine.py` is protected runtime code and should not be modified casually.
- `runner.py`, `tools/run_loop.py`, and scanner execution paths require explicit review before behavioral changes.
- Governance and analytics maturity take priority over dashboard-first work.
- Additive, read-only modules are preferred over runtime edits.
- Operator scaffolds must remain non-executing until reviewed.

## 6. Maturity Model

### L0 — Research Runtime

- `engine.run_engine()` is operational.
- scanners persist opportunities
- ALFRED and HARVEY are active
- artifacts and SQLite history exist

### L1 — Governed Observatory

- GORDON status is visible and review-ready
- LUCIUS policy surfaces are hardened
- architecture and telemetry become explicit and queryable

### L2 — Coordinated Operator Layer

- Nightwing contracts are reverified
- COMMANDER gating becomes explicit
- operator transitions remain observe/paper-first

### L3 — Live Readiness

- governance, compliance, ledgering, runtime control, and operator state are verified together
- repo drift and runtime drift are controlled
- live behavior is considered only after L0-L2 are complete

## 7. Immediate Priorities

1. Reverify Nightwing directly from disk and runtime.
2. Mature GORDON from standalone scaffolding into reviewed runtime controls.
3. Extend HARVEY into longitudinal and outcome-aware analytics.
4. Make COMMANDER gating explicit before deeper operator work.
5. Keep dashboards and presentation downstream of governance maturity.
