"""
ALFRED (ORACLE) — Data Quality Module

Centralized data quality validation for Batman Lab.
Runs after every engine cycle to ensure signals are based on clean data.

ALFRED validates:
- spot_price is present and valid
- merchant_spread is valid (not null)
- spread_flag is not ANOMALOUS
- premium_quality is VERIFIED or ESTIMATED

Public API:
    run_quality_check() -> dict
    get_latest_dq_score() -> float
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger("alfred")

BASE_DIR = Path(__file__).resolve().parent.parent
OPPORTUNITIES_LOG = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
DATA_QUALITY_LOG = BASE_DIR / "storage" / "logs" / "data_quality.jsonl"

# Minimum acceptable data quality score
MIN_DQ_SCORE = 0.75


def _read_last_n_records(n: int = 50) -> List[dict]:
    """
    Read the last N records from opportunities.jsonl.

    Args:
        n: Number of records to read (default 50)

    Returns:
        List of opportunity records (most recent last)
    """
    if not OPPORTUNITIES_LOG.exists():
        logger.warning(f"Opportunities log not found: {OPPORTUNITIES_LOG}")
        return []

    try:
        with open(OPPORTUNITIES_LOG, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Get last N lines
        recent_lines = lines[-n:] if len(lines) >= n else lines

        records = []
        for line in recent_lines:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON in opportunities log: {e}")
                    continue

        return records

    except Exception as e:
        logger.error(f"Error reading opportunities log: {e}")
        return []


def _validate_record(record: dict) -> Dict[str, bool]:
    """
    Validate a single opportunity record.

    Validation rules differ by record type:
    - Type A (cross-exchange): spot_price required, no premium_quality
    - Type B (spot vs futures): spot_price required, no premium_quality
    - Type C (P2P): spot_price required, premium_quality required

    Returns dict with validation results for each field.
    """
    record_type = record.get("type", "")

    validations = {
        "has_spot_price": False,
        "has_valid_spread": False,
        "not_anomalous": False,
        "has_premium_quality": False,
    }

    # Check spot_price is present and valid (not null, not zero)
    spot_price = record.get("spot_price")
    if spot_price is not None and spot_price > 0:
        validations["has_spot_price"] = True

    # Check spread is present and valid
    # Type A: edge_gross/edge_net, Type B: basis_pct, Type C: merchant_spread
    if record_type == "C":
        spread = record.get("merchant_spread")
        if spread is not None and isinstance(spread, (int, float)):
            validations["has_valid_spread"] = True
    elif record_type == "B":
        # Type B (spot vs futures) uses basis_pct
        basis = record.get("basis_pct")
        if basis is not None and isinstance(basis, (int, float)):
            validations["has_valid_spread"] = True
    else:
        # Type A (cross-exchange): check edge_gross or edge_net
        edge_gross = record.get("edge_gross")
        edge_net = record.get("edge_net")
        if (edge_gross is not None and isinstance(edge_gross, (int, float))) or (
            edge_net is not None and isinstance(edge_net, (int, float))
        ):
            validations["has_valid_spread"] = True

    # Check spread_flag is not ANOMALOUS (only Type C has this)
    spread_flag = record.get("spread_flag", "")
    if record_type == "C":
        validations["not_anomalous"] = spread_flag != "ANOMALOUS"
    else:
        # Type A/B don't have spread_flag, auto-pass
        validations["not_anomalous"] = True

    # Check premium_quality (only required for Type C)
    if record_type == "C":
        premium_quality = record.get("premium_quality", "")
        if premium_quality in ["VERIFIED", "ESTIMATED"]:
            validations["has_premium_quality"] = True
    else:
        # Type A/B don't have premium_quality, auto-pass
        validations["has_premium_quality"] = True

    return validations


def _calculate_dq_score(records: List[dict]) -> Dict[str, any]:
    """
    Calculate data quality score from a list of records.

    dq_score = % of records that pass ALL validations:
        - has valid spot_price
        - has valid spread
        - spread_flag is not ANOMALOUS
        - premium_quality is VERIFIED or ESTIMATED

    Returns:
        Dict with score and detailed breakdown
    """
    if not records:
        return {
            "dq_score": 0.0,
            "total_records": 0,
            "valid_records": 0,
            "issues": ["No records to validate"],
            "breakdown": {},
        }

    total = len(records)
    valid_count = 0
    issues = []

    # Track individual validation metrics
    metrics = {
        "has_spot_price": 0,
        "has_valid_spread": 0,
        "not_anomalous": 0,
        "has_premium_quality": 0,
    }

    # Track issues by market
    market_issues = {}

    for record in records:
        validations = _validate_record(record)

        # Update metrics
        for key, passed in validations.items():
            if passed:
                metrics[key] += 1

        # Check if all validations pass
        if all(validations.values()):
            valid_count += 1
        else:
            # Track what failed and for which market
            market = record.get("market", "unknown")
            if market not in market_issues:
                market_issues[market] = []

            failed = [k for k, v in validations.items() if not v]
            market_issues[market].extend(failed)

    # Calculate percentages
    dq_score = round(valid_count / total, 4) if total > 0 else 0.0

    breakdown = {key: round(count / total, 4) if total > 0 else 0.0 for key, count in metrics.items()}

    # Generate issue summary
    for market, failed_checks in market_issues.items():
        from collections import Counter

        counts = Counter(failed_checks)
        for check, count in counts.most_common(3):
            issues.append(f"{market}: {check} failed {count}x")

    return {
        "dq_score": dq_score,
        "total_records": total,
        "valid_records": valid_count,
        "issues": issues[:10],  # Limit to top 10 issues
        "breakdown": breakdown,
    }


def _append_to_log(report: dict) -> bool:
    """Append quality report to data_quality.jsonl."""
    try:
        DATA_QUALITY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(DATA_QUALITY_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(report) + "\n")
        return True
    except Exception as e:
        logger.error(f"Error writing data quality log: {e}")
        return False


def run_quality_check(n_records: int = 50) -> dict:
    """
    Run a data quality check on the last N opportunity records.

    This is the main entry point for ALFRED.

    Args:
        n_records: Number of recent records to analyze (default 50)

    Returns:
        Dictionary with quality report:
        {
            "cycle_ts": "2026-03-05T00:00:00+00:00",
            "dq_score": 0.85,
            "total_records": 50,
            "valid_records": 42,
            "issues": ["VES: has_spot_price failed 5x", ...],
            "breakdown": {
                "has_spot_price": 0.90,
                "has_valid_spread": 0.98,
                "not_anomalous": 0.95,
                "has_premium_quality": 0.88
            },
            "status": "OK" | "WARNING"
        }
    """
    logger.info(f"ALFRED: Running quality check on last {n_records} records...")

    # Read recent records
    records = _read_last_n_records(n_records)

    # Calculate quality score
    result = _calculate_dq_score(records)

    # Add timestamp and status
    report = {
        "cycle_ts": datetime.now(timezone.utc).isoformat(),
        "dq_score": result["dq_score"],
        "total_records": result["total_records"],
        "valid_records": result["valid_records"],
        "issues": result["issues"],
        "breakdown": result["breakdown"],
        "status": "OK" if result["dq_score"] >= MIN_DQ_SCORE else "WARNING",
    }

    # Log warning if below threshold
    if report["dq_score"] < MIN_DQ_SCORE:
        logger.warning(
            f"ALFRED WARNING: dq_score {report['dq_score']:.2%} < {MIN_DQ_SCORE:.0%} threshold. "
            f"Issues: {', '.join(report['issues'][:3])}"
        )
    else:
        logger.info(f"ALFRED: dq_score {report['dq_score']:.2%} - OK")

    # Append to log
    _append_to_log(report)

    return report


def get_latest_dq_score() -> float:
    """
    Get the most recent data quality score.

    Reads the last entry from data_quality.jsonl.

    Returns:
        Latest dq_score as float, or 0.0 if no data available
    """
    if not DATA_QUALITY_LOG.exists():
        logger.warning("No data quality log found - run run_quality_check() first")
        return 0.0

    try:
        with open(DATA_QUALITY_LOG, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            return 0.0

        # Get last line
        last_line = lines[-1].strip()
        if last_line:
            report = json.loads(last_line)
            return float(report.get("dq_score", 0.0))

        return 0.0

    except Exception as e:
        logger.error(f"Error reading latest dq_score: {e}")
        return 0.0


if __name__ == "__main__":
    # Test run
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    print("Running ALFRED data quality check...")
    report = run_quality_check()
    print(json.dumps(report, indent=2))

    print(f"\nLatest dq_score: {get_latest_dq_score():.2%}")
