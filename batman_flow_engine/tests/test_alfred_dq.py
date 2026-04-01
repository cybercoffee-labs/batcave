"""
Tests for ALFRED (core/alfred.py) — data quality validation.

Covers:
- has_spot_price check accepting reference_price when spot_price is absent
- has_spot_price check still passing when spot_price is present (no regression)
- has_spot_price failing when neither field is present
- dq_score improvement when Type F records carry reference_price
"""

from core.alfred import _validate_record, _calculate_dq_score


# ─────────────────────────────────────────────────────────────────────────────
# has_spot_price: normalized contract tests
# ─────────────────────────────────────────────────────────────────────────────


def test_validate_type_f_passes_with_reference_price():
    """Type F record with reference_price and no spot_price must pass has_spot_price."""
    record = {
        "type": "F",
        "reference_price": 17.00,  # official FX rate — no direct spot_price
        "edge_net": 1.5,
        "cross_premium_spread": 2.5,
        "spread_flag": "NORMAL",
        "premium_quality": "VERIFIED",
    }
    result = _validate_record(record)
    assert result["has_spot_price"] is True


def test_validate_type_f_fails_without_either_price():
    """Type F record with neither spot_price nor reference_price must fail has_spot_price."""
    record = {
        "type": "F",
        "edge_net": 1.5,
        "cross_premium_spread": 2.5,
    }
    result = _validate_record(record)
    assert result["has_spot_price"] is False


def test_validate_type_f_fails_with_zero_reference_price():
    """reference_price of 0 must not satisfy has_spot_price (same rule as spot_price)."""
    record = {
        "type": "F",
        "reference_price": 0.0,
        "edge_net": 1.5,
    }
    result = _validate_record(record)
    assert result["has_spot_price"] is False


def test_validate_type_c_spot_price_still_works():
    """Type C records with spot_price must still pass — no regression."""
    record = {
        "type": "C",
        "spot_price": 17.894,
        "merchant_spread": 0.52,
        "spread_flag": "NORMAL",
        "premium_quality": "VERIFIED",
    }
    result = _validate_record(record)
    assert result["has_spot_price"] is True


def test_validate_type_c_both_fields_present():
    """When both spot_price and reference_price are present, has_spot_price passes."""
    record = {
        "type": "C",
        "spot_price": 17.894,
        "reference_price": 17.00,
        "merchant_spread": 0.52,
        "spread_flag": "NORMAL",
        "premium_quality": "VERIFIED",
    }
    result = _validate_record(record)
    assert result["has_spot_price"] is True


def test_validate_type_a_unaffected():
    """Type A records without either price field still fail has_spot_price (no change)."""
    record = {
        "type": "A",
        "edge_gross": 0.08,
        "edge_net": 0.05,
    }
    result = _validate_record(record)
    assert result["has_spot_price"] is False


# ─────────────────────────────────────────────────────────────────────────────
# dq_score impact: before vs after normalized Type F records
# ─────────────────────────────────────────────────────────────────────────────


def _make_valid_type_c_record(i: int) -> dict:
    return {
        "type": "C",
        "spot_price": 17.894 + i * 0.01,
        "merchant_spread": 0.52,
        "spread_flag": "NORMAL",
        "premium_quality": "VERIFIED",
    }


def _make_type_f_without_reference(buy_fiat: str, sell_fiat: str) -> dict:
    """Simulates a pre-Patch-C Type F record — no reference_price, no spot_price."""
    return {
        "type": "F",
        "market": f"{buy_fiat}/{sell_fiat}",
        "edge_net": 1.5,
        "cross_premium_spread": 2.5,
        # no spot_price, no reference_price
    }


def _make_type_f_with_reference(buy_fiat: str, sell_fiat: str, spot_rate: float) -> dict:
    """Simulates a post-Patch-C Type F record — reference_price present."""
    return {
        "type": "F",
        "market": f"{buy_fiat}/{sell_fiat}",
        "edge_net": 1.5,
        "cross_premium_spread": 2.5,
        "reference_price": spot_rate,
    }


def test_dq_score_degrades_without_reference_price():
    """50 records: 39 valid Type C + 11 Type F without reference_price → dq_score < 1.0."""
    records = [_make_valid_type_c_record(i) for i in range(39)]
    records += [_make_type_f_without_reference("COP", "MXN") for _ in range(11)]

    result = _calculate_dq_score(records)

    assert result["dq_score"] < 1.0
    assert result["valid_records"] == 39
    # Breakdown: has_spot_price fails for the 11 Type F records
    assert result["breakdown"]["has_spot_price"] < 1.0


def test_dq_score_recovers_with_reference_price():
    """50 records: 39 valid Type C + 11 Type F with reference_price → dq_score = 1.0."""
    records = [_make_valid_type_c_record(i) for i in range(39)]
    records += [
        _make_type_f_with_reference("COP", "MXN", 4000.0),
        _make_type_f_with_reference("COP", "ARS", 4000.0),
        _make_type_f_with_reference("COP", "VES", 4000.0),
        _make_type_f_with_reference("MXN", "ARS", 17.00),
        _make_type_f_with_reference("MXN", "VES", 17.00),
        _make_type_f_with_reference("ARS", "VES", 1000.0),
        _make_type_f_with_reference("MXN", "COP", 17.00),
        _make_type_f_with_reference("ARS", "COP", 1000.0),
        _make_type_f_with_reference("VES", "COP", 45.0),
        _make_type_f_with_reference("VES", "MXN", 45.0),
        _make_type_f_with_reference("VES", "ARS", 45.0),
    ]

    result = _calculate_dq_score(records)

    assert result["dq_score"] == 1.0
    assert result["valid_records"] == 50
    assert result["breakdown"]["has_spot_price"] == 1.0


def test_dq_score_exact_ratio_without_reference():
    """Reproduce the observed 0.78: 39 valid out of 50 = 39/50."""
    records = [_make_valid_type_c_record(i) for i in range(39)]
    records += [_make_type_f_without_reference("COP", "MXN") for _ in range(11)]

    result = _calculate_dq_score(records)

    assert result["dq_score"] == round(39 / 50, 4)  # 0.78
