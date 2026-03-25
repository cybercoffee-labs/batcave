# AGENTS.md — Batman Lab Multi-Agent Orchestration
# Compatible with: Codex, Claude Code, Cursor, Copilot, Jules, Aider
# This file defines persistent rules, roles, and execution standards.

---

## PROJECT IDENTITY

- **Name:** Batman Lab
- **Type:** Multi-Stream Income Command Center (Fintech)
- **Owner:** Erick Posselt (Cancún, Mexico)
- **Status:** Phase 1 complete, operational with real Binance data
- **Full context:** Read MASTER_HANDOFF.md for complete state

---

## AGENT ROLES

### 🏗️ PLANNER (Claude.ai / ChatGPT Atlas)
- Defines architecture, specs, priorities
- Creates task issues and acceptance criteria
- Reviews high-level decisions
- Output: specs (.md), task lists, architecture docs

### ⚡ IMPLEMENTER (Claude Code / Codex / Cursor)
- Writes code, creates files, runs tests
- Follows existing patterns in codebase
- Must run tests after every change
- Output: .py files, tests, working features

### 🧪 TEST-WRITER (Claude Code / Codex)
- Creates tests for every new module
- Maintains 430+ test count (never decrease)
- Tests must pass before any commit
- Pattern: see tests/ directory for examples

### 🔍 REVIEWER (Copilot / Cursor Bugbot / Manual)
- Reviews PRs before merge to develop
- Checks: lint (ruff), types (mypy), tests (pytest)
- Validates security (no secrets, no unsafe operations)

### 🛡️ SECURITY (GORDON)
- All trading operations require explicit confirmation
- API keys only in .env (never in code)
- No withdrawal permissions ever
- Kill switch available at all times

---

## PERSISTENT RULES (NEVER BREAK)

### Code Standards
- Language: Python 3.13 (Mac Mini M4 Apple Silicon)
- Linter: ruff (select E,F,W --ignore E501)
- Types: mypy --ignore-missing-imports
- Tests: pytest with timeout=30
- Style: Follow existing patterns in codebase
- Commits: Conventional format (feat/fix/docs/test/chore)

### Architecture Rules
1. OBSERVE-ONLY by default. No real trades without human approval.
2. Append-only logs. Never delete .jsonl files.
3. No secrets in code. API keys → .env only.
4. Batman runs BEFORE Nightwing. Always.
5. PostgreSQL is primary data store. JSONL is legacy backup.
6. All new modules get tests. No untested code.
7. Team names are non-negotiable (Batman-themed).
8. LIVE mode requires HARVEY + LUCIUS + GORDON + two explicit flags.

### Database
- PostgreSQL 16 at localhost:5432, database: batman_lab
- Schema: database/schema.sql (8 tables, 5 views)
- Connection: database/postgres.py (pool, 20 CRUD functions)
- Legacy: core/database.py (SQLite — keep but don't extend)
- IMPORTANT: core/database.py shadows database/ package — use sys.path.insert(0, BASE_DIR) in any module that imports from database/

### Testing
- Run: cd batman_flow_engine && python -m pytest tests/ -q
- Current count: 430+ (24 test files)
- Never decrease test count
- New features require tests before merge

### Git
- Branch: develop (active), main (stable)
- Strategy: feature/ branches from develop
- Commits: --no-verify (pre-commit hooks may block)
- Remote: not pushed yet (needs GitHub repo)

---

## EXECUTION SURFACES

### Local (Mac Mini M4)
- Fast iteration, debugging, testing
- Use for: new features, bug fixes, exploration
- Tools: Claude Code, Cursor, terminal

### Worktree (parallel branches)
- Use for: large refactors, parallel feature development
- Setup: git worktree add ../batman-feature-X feature/X

### Cloud (future — AWS)
- Use for: 24/7 operation, deployment
- Not configured yet — see FULLSTACK_UPGRADE_SPEC.md Phase 4

---

## DEFINITION OF DONE

A task is DONE when:
1. ✅ Code written and working
2. ✅ Tests passing (all 430+, no regressions)
3. ✅ Lint clean (ruff check passes)
4. ✅ Committed to develop branch
5. ✅ Erick has verified it works (shown output)

---

## CURRENT TASK QUEUE (Priority Order)

### P0 — IMMEDIATE
- [ ] Set baseline avg_buy_price for HODL positions (use current price)
- [ ] Connect dual_writer to engine.py (new data → PostgreSQL)
- [ ] Fix 35 lint errors (see LINT_FIX_SPEC.md)
- [ ] Restart Batman engine (been off 3+ days)

### P1 — THIS WEEK
- [ ] GORDON v2 security (daily limits, confirmation, kill switch, whitelist)
- [ ] Dashboard pages 7-11 (portfolio, income streams, HODL, risk, content)
- [ ] Create GitHub repo + push
- [ ] Set take-profit/stop-loss targets on all HODL positions

### P2 — NEXT 2 WEEKS
- [ ] RED HOOD agent scaffold (spot cross-exchange)
- [ ] RED ROBIN agent scaffold (derivatives/funding)
- [ ] VICKI module (Binance Square content generation)
- [ ] Node.js API (Phase 2 of fullstack upgrade)

### P3 — MONTH 2
- [ ] Vue.js dashboard (Phase 3)
- [ ] AWS deployment (Phase 4)
- [ ] C++ speed core (Phase 5)
- [ ] Tax integration (Super Agente Contable)

---

## FILE MAP (key files for any agent)

```
MASTER_HANDOFF.md          — Complete project state (READ FIRST)
AGENTS.md                  — THIS FILE (persistent rules)
batman_flow_engine/
  CLAUDE.md                — Context for Claude Code
  ECOSYSTEM_v3_SPEC.md     — 10-stream income vision
  FULLSTACK_UPGRADE_SPEC.md — 10-week upgrade plan
  CPP_CORE_SPEC.md         — C++ speed layer spec
  LINT_FIX_SPEC.md         — 35 lint errors to fix
  config.yaml              — Scanner thresholds
  .env                     — API keys (NEVER commit)
  engine.py                — Main orchestrator (11 scanners)
  core/binance_live.py     — Live Binance API connector
  core/oracle.py           — HODL tracker + anti-FOMO
  core/dual_writer.py      — JSONL + PostgreSQL writer
  database/postgres.py     — PostgreSQL connection module
  database/schema.sql      — Database schema
  tools/command_center.py  — Master CLI dashboard
```

---

## CONTEXT SHARING (MCP)

When using multiple AI agents:
1. All agents read AGENTS.md for rules
2. All agents read MASTER_HANDOFF.md for state
3. Claude Code reads CLAUDE.md for implementation details
4. Codex reads AGENTS.md for task queue
5. After each change: git commit + update AGENTS.md task status

---

## VALIDATION GATES

Before ANY merge to develop:
```bash
make test          # All 430+ tests pass
make lint          # ruff clean (or document exceptions)
git diff --stat    # Review what changed
```

Before merge to main:
```bash
make test
make lint
python core/binance_live.py --test    # API still works
python tools/command_center.py        # System operational
```
