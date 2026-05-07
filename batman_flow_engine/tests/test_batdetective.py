"""Tests for BATDETECTIVE macro intelligence (core/batdetective.py +
core/macro_rules.py + core/macro_alerts.py + core/macro_fetchers/banxico.py).

Pure unit tests — no network calls. The fetchers are mocked at the
``run_batdetective_cycle`` boundary via the ``sources`` parameter.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _enable_batdetective_for_tests(monkeypatch):
    """Override the session-level env-var disable so BATDETECTIVE tests run.

    Tests pass `sources=` explicitly (bypassing the disable check anyway),
    but we also clear the env var in case any helper checks it directly.
    """
    monkeypatch.delenv("BATMAN_DISABLE_BATDETECTIVE", raising=False)


# ─────────────────────── macro_rules ───────────────────────


def test_apply_impact_rules_banxico_hike_returns_bearish_p2p():
    from core.macro_rules import apply_impact_rules

    event = {
        "source": "banxico",
        "event_type": "rate_decision",
        "headline": "Banxico decisión: alza de tasa de interés a 11.25%",
        "severity": "high",
        "currencies_affected": ["MXN"],
    }
    impact = apply_impact_rules(event)
    assert impact["confidence"] >= 0.80
    assert "C" in impact["impact_on_scanners"]
    c_impact = impact["impact_on_scanners"]["C"]
    assert c_impact["direction"] == "bearish"
    assert c_impact["expected_edge_delta"] < 0


def test_apply_impact_rules_banxico_cut_returns_bullish_p2p():
    from core.macro_rules import apply_impact_rules

    event = {
        "source": "banxico",
        "event_type": "rate_decision",
        "headline": "Banxico recorta tasa de referencia 50 puntos base",
        "severity": "high",
        "currencies_affected": ["MXN"],
    }
    impact = apply_impact_rules(event)
    assert impact["confidence"] >= 0.75
    assert impact["impact_on_scanners"]["C"]["direction"] == "bullish"
    assert impact["impact_on_scanners"]["C"]["expected_edge_delta"] > 0


def test_apply_impact_rules_fed_hike_widens_p2p():
    from core.macro_rules import apply_impact_rules

    event = {
        "source": "fed",
        "event_type": "rate_decision",
        "headline": "FOMC raises federal funds rate by 75 bps",
        "severity": "high",
        "currencies_affected": ["USD"],
    }
    impact = apply_impact_rules(event)
    assert impact["confidence"] >= 0.75
    assert impact["impact_on_scanners"]["C"]["direction"] == "bullish"


def test_apply_impact_rules_argentina_geopolitical_widens_ars():
    from core.macro_rules import apply_impact_rules

    event = {
        "source": "gdelt",
        "event_type": "geopolitical",
        "headline": "Argentina election triggers protests across Buenos Aires",
        "severity": "high",
        "currencies_affected": ["ARS"],
    }
    impact = apply_impact_rules(event)
    assert "C" in impact["impact_on_scanners"]
    assert impact["impact_on_scanners"]["C"]["direction"] == "bullish"


def test_apply_impact_rules_stablecoin_depeg_fires_h_scanner():
    from core.macro_rules import apply_impact_rules

    event = {
        "source": "gdelt",
        "event_type": "stablecoin_event",
        "headline": "USDC briefly depegs from USD amid bank concern",
        "severity": "critical",
        "currencies_affected": ["STABLE"],
    }
    impact = apply_impact_rules(event)
    assert impact["confidence"] >= 0.85
    assert "H" in impact["impact_on_scanners"]
    assert impact["impact_on_scanners"]["H"]["direction"] == "bullish"


def test_apply_impact_rules_unmatched_event_returns_zero_confidence():
    from core.macro_rules import apply_impact_rules

    event = {
        "source": "banxico",
        "event_type": "central_bank",  # general communiqué — no rule fires
        "headline": "Banxico publica boletín de actualización mensual",
        "severity": "low",
        "currencies_affected": ["MXN"],
    }
    impact = apply_impact_rules(event)
    assert impact["confidence"] == 0.0
    assert impact["impact_on_scanners"] == {}


def test_apply_impact_rules_handles_non_dict_input():
    from core.macro_rules import apply_impact_rules

    impact = apply_impact_rules(None)  # type: ignore[arg-type]
    assert impact["confidence"] == 0.0
    assert impact["impact_on_scanners"] == {}


# ─────────────────────── macro_alerts ───────────────────────


def test_format_alert_combines_event_and_impact():
    from core.macro_alerts import format_alert

    event = {
        "source": "banxico",
        "event_type": "rate_decision",
        "severity": "high",
        "headline": "Banxico hike",
        "currencies_affected": ["MXN"],
        "timestamp": "2026-05-04T10:00:00+00:00",
        "source_url": "https://example.com/x",
    }
    impact = {
        "confidence": 0.85,
        "impact_on_scanners": {
            "C": {"expected_edge_delta": -0.005, "direction": "bearish", "reasoning": "..."},
        },
        "reasoning": "summary",
    }
    alert = format_alert(event, impact)
    assert alert["headline"] == "Banxico hike"
    assert alert["confidence"] == 0.85
    assert alert["scanners_affected"] == ["C"]
    assert "scanner_details" in alert
    assert alert["source_url"] == "https://example.com/x"


def test_save_and_load_recent_alerts_roundtrip(tmp_path):
    from core.macro_alerts import load_recent_alerts, save_alert

    log_path = tmp_path / "macro.jsonl"
    alert = {"headline": "test", "confidence": 0.9, "severity": "high"}
    assert save_alert(alert, log_path) is True
    loaded = load_recent_alerts(log_path, limit=10)
    assert len(loaded) == 1
    assert loaded[0]["headline"] == "test"


def test_load_recent_alerts_skips_malformed_rows(tmp_path):
    from core.macro_alerts import load_recent_alerts

    log_path = tmp_path / "macro.jsonl"
    log_path.write_text(
        '{"headline": "ok", "confidence": 0.8}\n' "this is not json\n" '{"headline": "also ok", "confidence": 0.7}\n',
        encoding="utf-8",
    )
    loaded = load_recent_alerts(log_path)
    headlines = {a["headline"] for a in loaded}
    assert headlines == {"ok", "also ok"}


def test_load_recent_alerts_returns_empty_when_file_missing(tmp_path):
    from core.macro_alerts import load_recent_alerts

    loaded = load_recent_alerts(tmp_path / "does_not_exist.jsonl")
    assert loaded == []


def test_load_recent_alerts_orders_newest_first(tmp_path):
    """The dashboard expects newest first."""
    from core.macro_alerts import load_recent_alerts

    log_path = tmp_path / "macro.jsonl"
    log_path.write_text(
        '{"headline": "first"}\n{"headline": "second"}\n{"headline": "third"}\n',
        encoding="utf-8",
    )
    loaded = load_recent_alerts(log_path, limit=10)
    assert [a["headline"] for a in loaded] == ["third", "second", "first"]


# ─────────────── viewed-state (Streamlit Detective Insights) ───────────────


def test_mark_and_load_viewed_alert_roundtrip(tmp_path, monkeypatch):
    import core.macro_alerts as alerts_module
    from core.macro_alerts import (
        is_alert_viewed,
        load_viewed_keys,
        mark_alert_viewed,
    )

    viewed_path = tmp_path / "viewed.jsonl"
    monkeypatch.setattr(alerts_module, "VIEWED_ALERTS", viewed_path)

    alert = {
        "event_timestamp": "2026-05-04T10:00:00+00:00",
        "headline": "FOMC raises rates",
    }
    assert is_alert_viewed(alert) is False
    assert mark_alert_viewed(alert) is True

    viewed_keys = load_viewed_keys()
    assert len(viewed_keys) == 1
    assert is_alert_viewed(alert, viewed_keys) is True


def test_load_viewed_keys_handles_missing_file(tmp_path, monkeypatch):
    import core.macro_alerts as alerts_module
    from core.macro_alerts import load_viewed_keys

    monkeypatch.setattr(alerts_module, "VIEWED_ALERTS", tmp_path / "does_not_exist.jsonl")
    assert load_viewed_keys() == set()


def test_load_viewed_keys_skips_malformed_rows(tmp_path, monkeypatch):
    import core.macro_alerts as alerts_module
    from core.macro_alerts import load_viewed_keys

    viewed = tmp_path / "viewed.jsonl"
    viewed.write_text(
        '{"key": "ok"}\nthis is not json\n{"key": "also-ok"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(alerts_module, "VIEWED_ALERTS", viewed)
    assert load_viewed_keys() == {"ok", "also-ok"}


def test_alert_key_is_stable_across_renders():
    """Two identical-content alerts must produce the same key — the dashboard
    relies on this for filtering already-viewed alerts."""
    from core.macro_alerts import _alert_key

    a = {"event_timestamp": "2026-05-04T10:00:00+00:00", "headline": "X"}
    b = {"event_timestamp": "2026-05-04T10:00:00+00:00", "headline": "X"}
    assert _alert_key(a) == _alert_key(b)
    c = {"event_timestamp": "2026-05-04T10:00:00+00:00", "headline": "Y"}
    assert _alert_key(a) != _alert_key(c)


# ─────────────────────── batdetective orchestrator ───────────────────────


def test_run_batdetective_cycle_filters_low_confidence(monkeypatch, tmp_path):
    """An event whose impact rule fires below threshold must NOT generate
    an alert. (Suppressed to debug log only.)"""
    import core.macro_alerts as alerts_module
    from core.batdetective import run_batdetective_cycle

    # Redirect alerts log to tmp.
    log_path = tmp_path / "macro.jsonl"
    monkeypatch.setattr(alerts_module, "ALERTS_LOG", log_path)

    # Source returns one event whose rule has confidence ~0.55 (Banxico
    # rate_decision without hike/cut keywords).
    def fake_banxico(hours_back=4):
        return [
            {
                "source": "banxico",
                "event_type": "rate_decision",
                "headline": "Banxico publishes monetary policy update",
                "severity": "medium",
                "currencies_affected": ["MXN"],
                "timestamp": "2026-05-04T10:00:00+00:00",
            }
        ]

    alerts = run_batdetective_cycle(
        sources=[("banxico", fake_banxico)],
        confidence_threshold=0.75,
    )
    assert alerts == []
    assert not log_path.exists() or log_path.read_text(encoding="utf-8").strip() == ""


def test_run_batdetective_cycle_persists_high_confidence_alert(monkeypatch, tmp_path):
    import core.macro_alerts as alerts_module
    from core.batdetective import run_batdetective_cycle

    log_path = tmp_path / "macro.jsonl"
    monkeypatch.setattr(alerts_module, "ALERTS_LOG", log_path)

    def fake_fed(hours_back=4):
        return [
            {
                "source": "fed",
                "event_type": "rate_decision",
                "headline": "FOMC raises federal funds rate by 75 bps",
                "severity": "high",
                "currencies_affected": ["USD"],
                "timestamp": "2026-05-04T10:00:00+00:00",
                "source_url": "https://federalreserve.gov/x",
            }
        ]

    alerts = run_batdetective_cycle(
        sources=[("fed", fake_fed)],
        confidence_threshold=0.75,
    )
    assert len(alerts) == 1
    assert alerts[0]["source"] == "fed"
    assert "C" in alerts[0]["scanners_affected"]

    # Persisted to disk.
    assert log_path.exists()
    persisted = [json.loads(ln) for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(persisted) == 1
    assert persisted[0]["source"] == "fed"


def test_run_batdetective_cycle_recovers_from_one_bad_source(monkeypatch, tmp_path):
    """A fetcher that raises must NOT abort the whole cycle."""
    import core.macro_alerts as alerts_module
    from core.batdetective import run_batdetective_cycle

    log_path = tmp_path / "macro.jsonl"
    monkeypatch.setattr(alerts_module, "ALERTS_LOG", log_path)

    def good_source(hours_back=4):
        return [
            {
                "source": "fed",
                "event_type": "rate_decision",
                "headline": "FOMC hike",
                "severity": "high",
                "currencies_affected": ["USD"],
                "timestamp": "2026-05-04T10:00:00+00:00",
            }
        ]

    def bad_source(hours_back=4):
        raise RuntimeError("network down")

    alerts = run_batdetective_cycle(
        sources=[("bad", bad_source), ("fed", good_source)],
        confidence_threshold=0.75,
    )
    assert len(alerts) == 1
    assert alerts[0]["source"] == "fed"


def test_run_batdetective_cycle_empty_sources_returns_no_alerts(tmp_path, monkeypatch):
    import core.macro_alerts as alerts_module
    from core.batdetective import run_batdetective_cycle

    monkeypatch.setattr(alerts_module, "ALERTS_LOG", tmp_path / "macro.jsonl")
    alerts = run_batdetective_cycle(sources=[])
    assert alerts == []


# ─────────────────────── banxico fetcher (network-isolated) ───────────────────────


def test_banxico_fetcher_returns_empty_on_network_error():
    from core.macro_fetchers import banxico

    with patch.object(banxico, "_fetch_rss_xml", return_value=None):
        events = banxico.fetch_banxico_events(hours_back=4)
        assert events == []


def test_banxico_fetcher_parses_rss_and_classifies_rate_decision(monkeypatch):
    """Round-trip a synthetic RSS payload and confirm classification works."""
    from datetime import datetime, timedelta, timezone

    from core.macro_fetchers import banxico

    recent_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    pubdate = recent_dt.strftime("%a, %d %b %Y %H:%M:%S %z")
    fake_rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Banxico decisión de política monetaria: alza de tasa</title>
      <pubDate>{pubdate}</pubDate>
      <link>https://example.com/x</link>
      <description>Detalle del comunicado.</description>
    </item>
  </channel>
</rss>"""
    monkeypatch.setattr(banxico, "_fetch_rss_xml", lambda url=banxico.BANXICO_RSS_URL: fake_rss)

    events = banxico.fetch_banxico_events(hours_back=4)
    assert len(events) == 1
    e = events[0]
    assert e["source"] == "banxico"
    assert e["event_type"] == "rate_decision"
    assert e["severity"] == "high"  # decisión + alza
    assert e["currencies_affected"] == ["MXN"]
    assert e["source_url"] == "https://example.com/x"


def test_banxico_fetcher_skips_old_items(monkeypatch):
    """Items older than hours_back must be filtered out."""
    from datetime import datetime, timedelta, timezone

    from core.macro_fetchers import banxico

    old_dt = datetime.now(timezone.utc) - timedelta(hours=24)
    pubdate = old_dt.strftime("%a, %d %b %Y %H:%M:%S %z")
    fake_rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss><channel><item>
<title>Old news</title>
<pubDate>{pubdate}</pubDate>
<link>x</link><description>old</description>
</item></channel></rss>"""
    monkeypatch.setattr(banxico, "_fetch_rss_xml", lambda url=banxico.BANXICO_RSS_URL: fake_rss)
    assert banxico.fetch_banxico_events(hours_back=4) == []


def test_banxico_fetcher_handles_malformed_xml(monkeypatch):
    from core.macro_fetchers import banxico

    monkeypatch.setattr(banxico, "_fetch_rss_xml", lambda url=banxico.BANXICO_RSS_URL: "not really xml<<<")
    assert banxico.fetch_banxico_events(hours_back=4) == []
