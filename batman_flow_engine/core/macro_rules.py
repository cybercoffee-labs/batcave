"""Macro impact rules — translate a MacroEvent into a per-scanner expectation.

This is the "Burry/Dalio" core of BATDETECTIVE: deterministic, hand-coded
financial logic that says "when X happens in the macro world, scanner Y
typically widens / contracts / behaves differently". The output is a
machine-readable forecast that the engine surfaces to the operator
alongside scanner output, so a human can decide whether to ACT, IGNORE,
or WATCH.

Output contract (from apply_impact_rules):
    {
        "confidence": float in [0.0, 1.0],
        "impact_on_scanners": {
            "<scanner_letter>": {
                "expected_edge_delta": float,   # +0.005 = +0.5% edge widening
                "direction": "bullish" | "bearish" | "neutral",
                "reasoning": str,
            },
            ...
        },
        "reasoning": str,    # one-line summary across scanners
    }

Confidence threshold for alerting is decided by macro_alerts (default 0.75).

Conventions
-----------
- "bullish" for a scanner = scanner is more likely to find a tradable edge.
- expected_edge_delta is signed: positive = wider edge, negative = tighter.
- All numbers are educated guesses, NOT historical fits. Tune over time.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("batman.macro_rules")


def _empty_impact() -> dict[str, Any]:
    return {
        "confidence": 0.0,
        "impact_on_scanners": {},
        "reasoning": "",
    }


def _bull(delta: float, why: str) -> dict[str, Any]:
    return {"expected_edge_delta": delta, "direction": "bullish", "reasoning": why}


def _bear(delta: float, why: str) -> dict[str, Any]:
    return {"expected_edge_delta": delta, "direction": "bearish", "reasoning": why}


def _is_rate_hike(headline: str) -> bool:
    h = headline.lower()
    return any(token in h for token in ("hike", "raise", "increase", "alza", "sube", "subir"))


def _is_rate_cut(headline: str) -> bool:
    h = headline.lower()
    return any(token in h for token in ("cut", "reduce", "lower", "baja", "recorta", "reducir"))


def apply_impact_rules(event: dict[str, Any]) -> dict[str, Any]:
    """Translate a single MacroEvent dict into a scanner-impact forecast.

    Always returns a dict with the contract above. Rules that don't fire
    return confidence=0.0 and an empty impact_on_scanners — the
    orchestrator filters those out before alerting.
    """
    impact = _empty_impact()
    if not isinstance(event, dict):
        return impact

    source = event.get("source", "")
    event_type = event.get("event_type", "")
    headline = event.get("headline", "") or ""
    severity = event.get("severity", "low")
    currencies = event.get("currencies_affected", []) or []

    # ─────────────── Banxico rate decision ───────────────
    if source == "banxico" and event_type == "rate_decision":
        if _is_rate_hike(headline):
            impact["confidence"] = 0.85
            impact["impact_on_scanners"] = {
                "C": _bear(-0.005, "Banxico hike → MXN strength → P2P premium contracts"),
                "I": _bear(-0.003, "Banxico hike → MXN strength → cross-platform MXN edge tightens"),
            }
        elif _is_rate_cut(headline):
            impact["confidence"] = 0.80
            impact["impact_on_scanners"] = {
                "C": _bull(+0.007, "Banxico cut → MXN weakness/outflow → P2P premium widens"),
                "I": _bull(+0.004, "Banxico cut → MXN weakness → cross-platform MXN edge widens"),
            }
        else:
            impact["confidence"] = 0.55
            impact["impact_on_scanners"] = {
                "C": {
                    "expected_edge_delta": 0.0,
                    "direction": "neutral",
                    "reasoning": "Banxico rate decision (direction unclear from headline)",
                },
            }

    # ─────────────── Banxico FX intervention ───────────────
    elif source == "banxico" and event_type == "fx_intervention":
        impact["confidence"] = 0.90
        impact["impact_on_scanners"] = {
            "C": _bear(-0.008, "Banxico defends MXN → P2P premium snaps tighter on intervention"),
            "I": _bear(-0.005, "Banxico defends MXN → cross-platform MXN edge tightens"),
        }

    # ─────────────── Fed rate decision (USD strength → emerging FX weakness) ───────────────
    elif source == "fed" and event_type == "rate_decision":
        if _is_rate_hike(headline):
            impact["confidence"] = 0.80
            impact["impact_on_scanners"] = {
                "C": _bull(+0.006, "Fed hike → USD strength → MXN weakness → P2P premium widens"),
                "F": _bull(+0.005, "Fed hike → cross-currency P2P stress (USD/MXN) widens"),
            }
        elif _is_rate_cut(headline):
            impact["confidence"] = 0.75
            impact["impact_on_scanners"] = {
                "C": _bear(-0.004, "Fed cut → USD weakness → MXN relief → P2P premium tightens"),
            }

    # ─────────────── Fed FOMC unscheduled / balance sheet action ───────────────
    elif source == "fed" and event_type == "balance_sheet":
        impact["confidence"] = 0.70
        impact["impact_on_scanners"] = {
            "A": _bull(+0.004, "Fed balance-sheet action → cross-exchange spreads widen on volatility"),
            "E": _bull(+0.003, "Fed balance-sheet action → funding rates dislocate"),
        }

    # ─────────────── GDELT geopolitical risk in Argentina ───────────────
    elif source == "gdelt" and event_type == "geopolitical" and "ARS" in currencies:
        impact["confidence"] = 0.70
        impact["impact_on_scanners"] = {
            "C": _bull(+0.008, "Argentina political risk → ARS weakness → P2P premium widens"),
            "F": _bull(+0.006, "Argentina political risk → cross-currency P2P stress"),
        }

    # ─────────────── GDELT geopolitical risk in Mexico ───────────────
    elif source == "gdelt" and event_type == "geopolitical" and "MXN" in currencies:
        impact["confidence"] = 0.65
        impact["impact_on_scanners"] = {
            "C": _bull(+0.005, "Mexico political/social risk → MXN weakness → P2P premium widens"),
        }

    # ─────────────── Stablecoin depeg event (any source) ───────────────
    elif event_type == "stablecoin_event" or "depeg" in headline.lower():
        impact["confidence"] = 0.90
        impact["impact_on_scanners"] = {
            "H": _bull(+0.010, "Stablecoin depeg event → scanner H (depeg detector) edge spikes"),
            "C": _bull(+0.004, "Stablecoin stress → P2P USDT premium widens defensively"),
        }

    # ─────────────── Bitcoin volatility / crypto news ───────────────
    elif "BTC" in currencies or "bitcoin" in headline.lower():
        if any(token in headline.lower() for token in ("crash", "spike", "volatility", "halt")):
            impact["confidence"] = 0.75
            impact["impact_on_scanners"] = {
                "A": _bull(+0.003, "BTC volatility → cross-exchange spreads widen"),
                "E": _bull(+0.002, "BTC volatility → funding rates dislocate"),
                "K": _bull(+0.002, "BTC volatility → futures vs futures spread widens"),
            }

    if impact["impact_on_scanners"]:
        scanners = ", ".join(sorted(impact["impact_on_scanners"].keys()))
        impact["reasoning"] = (
            f"source={source} type={event_type} severity={severity} → scanners affected: {scanners} "
            f"(confidence={impact['confidence']:.0%})"
        )
    else:
        impact["reasoning"] = f"source={source} type={event_type} → no rule matched"

    return impact
