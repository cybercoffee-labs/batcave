# LINT FIX SPEC — For Claude Code
# Run: ruff check batman_flow_engine/ nightwing_agent/ --select E,F,W --ignore E501
# Current: 35 errors remaining
# Goal: 0 errors

## ERRORS BY TYPE

### E402 — Module level import not at top of file (15 errors)
These are all `sys.path.insert()` before imports. This is INTENTIONAL for tools/ scripts.
FIX: Add `# noqa: E402` to each affected import line.

Files:
- batman_flow_engine/tools/architecture_status.py:23
- batman_flow_engine/tools/research_metrics.py:18-19
- batman_flow_engine/tools/run_loop.py:23
- batman_flow_engine/tools/system_health.py:14-15
- nightwing_agent/agent.py:25-32
- nightwing_agent/research/feature_analysis.py:24
- nightwing_agent/scanners/opportunity_scanner.py:35
- nightwing_agent/scanners/system_scanner.py:35

### E701 — Multiple statements on one line (3 errors)
FIX: Split into separate lines.

File: batman_flow_engine/tools/morning_briefing.py
- Line 82: `if not line.strip(): continue` → split to 2 lines
- Line 85: `if r.get("ts", "") > cutoff: opps.append(r)` → split to 2 lines
- Line 86: `except Exception: continue` → split to 2 lines

### E702 — Multiple statements on one line semicolon (7 errors)
FIX: Split semicolons into separate lines.

File: batman_flow_engine/graph_engine.py
- Line 41: `vz=...; r1d=...; px=...` → 3 separate lines
- Line 61: same pattern
- Line 79: same pattern
- Line 83: `nodes_j=...; edges_j=...` → 2 separate lines

### E712 — Avoid equality comparisons to True (1 error)
FIX: Change `== True` to just the expression.

File: batman_flow_engine/dashboard/pages/4_patterns.py:51
- `mask = mask & (df.get("viable", False) == True)` → `mask = mask & (df.get("viable", False))`

### E741 — Ambiguous variable name (already fixed by sed, verify)

### F841 — Local variable assigned but never used (3 errors)
FIX: Either use the variable or prefix with underscore.

Files:
- batman_flow_engine/tests/test_scanner_funding_rate.py:299: `results = scan_funding_rates(...)` → `_results = ...`
- batman_flow_engine/tools/run_loop.py:122: `success = run_cycle(...)` → `_success = ...` or just `run_cycle(...)`
- batman_flow_engine/tools/trade_now.py:151: Remove `action_color` variable (unused)
- batman_flow_engine/tools/trade_now.py:153: Remove `reset` variable (unused)

### W293 — Blank line contains whitespace (3 errors)
FIX: Remove trailing whitespace from blank lines.

Files:
- batman_flow_engine/tools/trade_now.py:198
- nightwing_agent/core/batman_bridge.py:23
- nightwing_agent/core/batman_bridge.py:26

## COMMAND TO VERIFY
```bash
ruff check batman_flow_engine/ nightwing_agent/ --select E,F,W --ignore E501
```

## AFTER FIXING, ALSO RUN
```bash
make test  # Ensure no tests broke
```
