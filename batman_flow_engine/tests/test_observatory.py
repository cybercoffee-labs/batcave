from core.observatory import build_architecture_status, get_persona_registry
from tools.architecture_status import render_terminal_status


def test_persona_registry_contains_core_modules():
    registry = get_persona_registry()
    keys = {item["key"] for item in registry}

    assert "batman" in keys
    assert "harvey" in keys
    assert "gordon" in keys


def test_persona_registry_exposes_repo_state():
    registry = get_persona_registry()
    batman = next(item for item in registry if item["key"] == "batman")

    assert batman["repo_state"] in {"active", "scaffold", "missing"}
    assert "engine.py" in batman["module_paths"]


def test_architecture_status_has_expected_sections():
    snapshot = build_architecture_status()

    assert "summary" in snapshot
    assert "market_flow_summary" in snapshot
    assert "harvey" in snapshot
    assert "temporal" in snapshot
    assert "system_health" in snapshot
    assert "architecture" in snapshot
    assert snapshot["summary"]["signals_total"] >= 0


def test_architecture_status_contains_harvey_metrics():
    snapshot = build_architecture_status()
    harvey = snapshot["harvey"]

    assert "signals_per_scanner" in harvey
    assert "signals_per_market" in harvey
    assert "average_edge_net" in harvey
    assert "average_depth_estimate" in harvey
    assert "viable_signal_percentage" in harvey


def test_terminal_render_contains_core_sections():
    output = render_terminal_status(build_architecture_status())

    assert "BATCAVE Economic Flow Observatory" in output
    assert "Market Flow" in output
    assert "System Health" in output
    assert "Architecture" in output
