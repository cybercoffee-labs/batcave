"""
Local AI Intelligence Engine for Batman Flow Engine.

This module provides AI-powered market analysis by reading daily opportunity data
and sending structured summaries to a local Ollama instance for pattern detection
and risk assessment.

Architecture:
    1. Read today's opportunities from storage/logs/opportunities.jsonl
    2. Build structured market summary (counts, spreads, pairs, data quality)
    3. Send summary to Ollama llama3.2:3b via POST to http://localhost:11434/api/generate
    4. Parse JSON response with robust error handling
    5. Return structured intelligence or fallback dict if unavailable

Public API:
    - get_market_intelligence(date: str = None) -> dict
    - get_ollama_status() -> dict

Dependencies:
    - Ollama running locally on port 11434
    - llama3.2:3b model installed (ollama pull llama3.2:3b)

Author: Batman Research Lab
Version: 1.0
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import requests
from time import sleep

# ───────────────────────── CONSTANTS ─────────────────────────
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"
OLLAMA_TIMEOUT = 30  # seconds
RETRY_ATTEMPTS = 2
RETRY_DELAY = 3  # seconds

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"

logger = logging.getLogger("ollama_intel")


# ───────────────────────── HELPER FUNCTIONS ─────────────────────────


def _read_opportunities_today(date_str: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Read today's opportunities from opportunities.jsonl.

    Args:
        date_str: Optional date string in YYYY-MM-DD format. If None, uses today's date.

    Returns:
        List of opportunity dictionaries for the specified date.

    Raises:
        FileNotFoundError: If opportunities.jsonl does not exist.
    """
    if not LOG_FILE.exists():
        logger.warning(f"Opportunities log not found: {LOG_FILE}")
        return []

    target_date = date_str if date_str else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    opportunities = []

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    # Extract date from timestamp (ISO format: 2026-03-04T12:00:00+00:00)
                    ts = record.get("ts", "")
                    if ts.startswith(target_date):
                        opportunities.append(record)
                except json.JSONDecodeError as e:
                    logger.warning(f"Malformed JSON in opportunities.jsonl: {e}")
                    continue
    except Exception as e:
        logger.error(f"Error reading opportunities.jsonl: {e}")
        return []

    logger.info(f"Read {len(opportunities)} opportunities for {target_date}")
    return opportunities


def _build_market_summary(opportunities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build structured market summary from opportunities.

    Args:
        opportunities: List of opportunity dictionaries.

    Returns:
        Dictionary containing:
            - count_by_type: {A, B, C} - Count of opportunities by scanner type
            - best_spread_by_type: {A, B, C} - Maximum absolute spread by type
            - active_pairs: List of unique markets scanned
            - total_opportunities: Total count
            - data_quality: Percentage of records with non-null spot_price
    """
    if not opportunities:
        return {
            "count_by_type": {"A": 0, "B": 0, "C": 0},
            "best_spread_by_type": {"A": 0.0, "B": 0.0, "C": 0.0},
            "active_pairs": [],
            "total_opportunities": 0,
            "data_quality": 0.0,
        }

    count_by_type = {"A": 0, "B": 0, "C": 0}
    best_spread_by_type = {"A": 0.0, "B": 0.0, "C": 0.0}
    active_pairs = set()
    records_with_spot = 0

    for opp in opportunities:
        opp_type = opp.get("type", "")

        # Count by type
        if opp_type in count_by_type:
            count_by_type[opp_type] += 1

        # Track active pairs/markets
        if opp_type == "A":
            pair = opp.get("asset", "")
            if pair:
                active_pairs.add(pair)
            # Scanner A: spread_pct
            spread = abs(opp.get("spread_pct", 0.0))
            best_spread_by_type["A"] = max(best_spread_by_type["A"], spread)

        elif opp_type == "B":
            pair = opp.get("asset", "")
            if pair:
                active_pairs.add(pair)
            # Scanner B: basis_pct
            basis = abs(opp.get("basis_pct", 0.0))
            best_spread_by_type["B"] = max(best_spread_by_type["B"], basis)

        elif opp_type == "C":
            market = opp.get("market", "")
            if market:
                active_pairs.add(f"USDT/{market}")
            # Scanner C: merchant_spread
            spread = abs(opp.get("merchant_spread", 0.0) * 100)  # Convert to %
            best_spread_by_type["C"] = max(best_spread_by_type["C"], spread)

        # Data quality: check for spot_price presence
        if opp.get("spot_price") is not None:
            records_with_spot += 1

    data_quality = (records_with_spot / len(opportunities)) * 100 if opportunities else 0.0

    return {
        "count_by_type": count_by_type,
        "best_spread_by_type": {k: round(v, 4) for k, v in best_spread_by_type.items()},
        "active_pairs": sorted(list(active_pairs)),
        "total_opportunities": len(opportunities),
        "data_quality": round(data_quality, 2),
    }


def _call_ollama(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send market summary to Ollama for AI analysis.

    Args:
        summary: Market summary dictionary from _build_market_summary().

    Returns:
        Dictionary containing AI analysis with fields:
            - summary: One paragraph analysis
            - risk_level: LOW|MEDIUM|HIGH
            - notable_patterns: List of detected patterns
            - recommendation: Actionable research recommendation
            - confidence: Float 0.0-1.0
            - status: 'ok' or 'unavailable'

    Raises:
        requests.exceptions.RequestException: On network errors (caught internally).
    """
    prompt = f"""You are a senior crypto market analyst specializing in LATAM arbitrage.
Given the following market data detected today: {json.dumps(summary)}
Analyze the patterns and respond ONLY with valid JSON containing:
{{
  "summary": "one paragraph analysis",
  "risk_level": "LOW|MEDIUM|HIGH",
  "notable_patterns": ["pattern1", "pattern2"],
  "recommendation": "one actionable research recommendation",
  "confidence": 0.0-1.0
}}
Respond with JSON only. No markdown. No explanation."""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }

    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            logger.info(f"Calling Ollama (attempt {attempt}/{RETRY_ATTEMPTS})...")
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=OLLAMA_TIMEOUT,
            )
            response.raise_for_status()

            data = response.json()
            response_text = data.get("response", "").strip()

            # Parse JSON response
            try:
                parsed = json.loads(response_text)

                # Validate required fields
                required_fields = ["summary", "risk_level", "notable_patterns", "recommendation", "confidence"]
                if all(field in parsed for field in required_fields):
                    parsed["status"] = "ok"
                    logger.info("Successfully received AI analysis from Ollama")
                    return parsed
                else:
                    logger.warning(f"Ollama response missing required fields: {parsed}")
                    last_error = "Missing required fields in response"
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse Ollama JSON response: {e}")
                logger.debug(f"Raw response: {response_text}")
                last_error = f"JSON parse error: {e}"

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama request timed out (attempt {attempt}/{RETRY_ATTEMPTS})")
            last_error = "Request timeout"
            if attempt < RETRY_ATTEMPTS:
                sleep(RETRY_DELAY)

        except requests.exceptions.ConnectionError:
            logger.warning(f"Cannot connect to Ollama (attempt {attempt}/{RETRY_ATTEMPTS})")
            last_error = "Connection error - is Ollama running?"
            if attempt < RETRY_ATTEMPTS:
                sleep(RETRY_DELAY)

        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama request failed: {e}")
            last_error = str(e)
            if attempt < RETRY_ATTEMPTS:
                sleep(RETRY_DELAY)

    # All retries exhausted - return fallback
    logger.warning(f"Ollama unavailable after {RETRY_ATTEMPTS} attempts: {last_error}")
    return {
        "status": "unavailable",
        "error": last_error,
        "summary": "AI analysis unavailable - Ollama service not responding",
        "risk_level": "UNKNOWN",
        "notable_patterns": [],
        "recommendation": "Check Ollama service status and retry",
        "confidence": 0.0,
    }


# ───────────────────────── PUBLIC API ─────────────────────────


def get_ollama_status() -> Dict[str, Any]:
    """
    Check if Ollama is running and which models are available.

    Returns:
        Dictionary containing:
            - available: bool - Whether Ollama is reachable
            - model: str - Model name being used
            - models_installed: List[str] - List of installed models (if available)
            - version: str - Ollama version (if available)
            - error: str - Error message if unavailable

    Example:
        >>> status = get_ollama_status()
        >>> print(status)
        {
            "available": True,
            "model": "llama3.2:3b",
            "models_installed": ["llama3.2:3b", "llama3.2:1b"],
            "version": "0.1.0"
        }
    """
    try:
        # Check version endpoint
        version_url = "http://localhost:11434/api/version"
        version_resp = requests.get(version_url, timeout=5)
        version_resp.raise_for_status()
        version_data = version_resp.json()

        # Check available models
        tags_url = "http://localhost:11434/api/tags"
        tags_resp = requests.get(tags_url, timeout=5)
        tags_resp.raise_for_status()
        tags_data = tags_resp.json()

        models_installed = [m.get("name", "") for m in tags_data.get("models", [])]
        model_available = OLLAMA_MODEL in models_installed

        return {
            "available": True,
            "model": OLLAMA_MODEL,
            "model_installed": model_available,
            "models_installed": models_installed,
            "version": version_data.get("version", "unknown"),
        }

    except requests.exceptions.ConnectionError:
        return {
            "available": False,
            "model": OLLAMA_MODEL,
            "error": "Cannot connect to Ollama - is it running? (http://localhost:11434)",
        }
    except requests.exceptions.RequestException as e:
        return {
            "available": False,
            "model": OLLAMA_MODEL,
            "error": f"Ollama check failed: {str(e)}",
        }


def get_market_intelligence(date: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate AI-powered market intelligence from today's opportunities.

    This is the main entry point for the intelligence module. It reads today's
    opportunities, builds a summary, sends it to Ollama for analysis, and returns
    structured intelligence.

    Args:
        date: Optional date string in YYYY-MM-DD format. If None, uses today's date.

    Returns:
        Dictionary containing:
            - status: str - 'ok', 'unavailable', or 'no_data'
            - date: str - Date analyzed
            - summary: str - One paragraph AI analysis
            - risk_level: str - LOW|MEDIUM|HIGH|UNKNOWN
            - notable_patterns: List[str] - Detected patterns
            - recommendation: str - Actionable recommendation
            - confidence: float - AI confidence 0.0-1.0
            - market_summary: dict - Raw market data summary
            - opportunities_count: int - Number of opportunities analyzed
            - error: str - Error message if unavailable

    Example:
        >>> intel = get_market_intelligence()
        >>> print(intel['summary'])
        'MXN P2P market showing elevated merchant spreads...'
        >>> print(intel['risk_level'])
        'MEDIUM'
    """
    target_date = date if date else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info(f"Generating market intelligence for {target_date}...")

    # Step 1: Read opportunities
    opportunities = _read_opportunities_today(target_date)

    if not opportunities:
        logger.warning(f"No opportunities found for {target_date}")
        return {
            "status": "no_data",
            "date": target_date,
            "summary": "No market opportunities detected for the specified date",
            "risk_level": "UNKNOWN",
            "notable_patterns": [],
            "recommendation": "Wait for market data to accumulate",
            "confidence": 0.0,
            "market_summary": {},
            "opportunities_count": 0,
        }

    # Step 2: Build market summary
    market_summary = _build_market_summary(opportunities)

    # Step 3: Send to Ollama for analysis
    intelligence = _call_ollama(market_summary)

    # Step 4: Enrich with metadata
    intelligence["date"] = target_date
    intelligence["market_summary"] = market_summary
    intelligence["opportunities_count"] = len(opportunities)

    logger.info(f"Market intelligence generated: {intelligence.get('status', 'unknown')}")

    return intelligence


def analyze_opportunity(opp: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a single opportunity to Ollama for risk analysis.

    BARBARA (Batgirl's Oracle) analyzes individual opportunities and provides
    a risk assessment, recommended action, and confidence level.

    Args:
        opp: Opportunity dictionary containing at minimum:
            - type: Scanner type (A-H)
            - edge_net: Edge percentage (or equivalent field)
            - asset: Asset being traded
            - exchange/venue: Where the opportunity exists

    Returns:
        Dictionary containing:
            - risk: int (1-10) - Risk level
            - action: str - "act", "wait", or "skip"
            - confidence: float (0-1) - AI confidence
            - reasoning: str - Explanation for the recommendation
            - status: str - "ok" or "error"
            - error: str - Error message if status is "error"

    Example:
        >>> opp = {"type": "D", "edge_net": 0.45, "asset": "BTC/USDT", "venue": "Binance"}
        >>> result = analyze_opportunity(opp)
        >>> print(result)
        {"risk": 3, "action": "act", "confidence": 0.85, "reasoning": "..."}
    """
    # Extract key fields from opportunity
    opp_type = opp.get("type", "UNKNOWN")
    edge_net = opp.get("edge_net") or opp.get("spread_pct") or opp.get("basis_pct") or opp.get("p2p_premium") or 0
    asset = opp.get("asset") or opp.get("market") or "UNKNOWN"
    exchange = opp.get("venue") or opp.get("exchange") or opp.get("exchange_buy") or "UNKNOWN"

    prompt = f"""You are a crypto arbitrage risk analyst. Analyze this opportunity: Type={opp_type}, Edge={edge_net}%, Asset={asset}, Exchange={exchange}. Rate risk 1-10, recommend action (act/wait/skip), confidence 0-1. Respond in JSON only: {{"risk":N,"action":"...","confidence":N,"reasoning":"..."}}"""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }

    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            logger.info(f"BARBARA analyzing opportunity (attempt {attempt}/{RETRY_ATTEMPTS})...")
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=OLLAMA_TIMEOUT,
            )
            response.raise_for_status()

            data = response.json()
            response_text = data.get("response", "").strip()

            # Parse JSON response
            try:
                parsed = json.loads(response_text)

                # Validate required fields
                required_fields = ["risk", "action", "confidence", "reasoning"]
                if all(field in parsed for field in required_fields):
                    # Validate risk is 1-10
                    risk = parsed.get("risk")
                    if isinstance(risk, (int, float)) and 1 <= risk <= 10:
                        parsed["risk"] = int(risk)
                    else:
                        logger.warning(f"Invalid risk value: {risk}, defaulting to 5")
                        parsed["risk"] = 5

                    # Validate action is one of the expected values
                    action = parsed.get("action", "").lower()
                    if action not in ("act", "wait", "skip"):
                        logger.warning(f"Invalid action value: {action}, defaulting to 'wait'")
                        parsed["action"] = "wait"
                    else:
                        parsed["action"] = action

                    # Validate confidence is 0-1
                    conf = parsed.get("confidence")
                    if isinstance(conf, (int, float)) and 0 <= conf <= 1:
                        parsed["confidence"] = float(conf)
                    else:
                        logger.warning(f"Invalid confidence value: {conf}, defaulting to 0.5")
                        parsed["confidence"] = 0.5

                    parsed["status"] = "ok"
                    logger.info(f"BARBARA analysis complete: risk={parsed['risk']} action={parsed['action']}")
                    return parsed
                else:
                    missing = [f for f in required_fields if f not in parsed]
                    logger.warning(f"BARBARA response missing fields: {missing}")
                    last_error = f"Missing required fields: {missing}"

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse BARBARA JSON response: {e}")
                logger.debug(f"Raw response: {response_text}")
                last_error = f"JSON parse error: {e}"

        except requests.exceptions.Timeout:
            logger.warning(f"BARBARA request timed out (attempt {attempt}/{RETRY_ATTEMPTS})")
            last_error = "Request timeout"
            if attempt < RETRY_ATTEMPTS:
                sleep(RETRY_DELAY)

        except requests.exceptions.ConnectionError:
            logger.warning(f"Cannot connect to Ollama for BARBARA (attempt {attempt}/{RETRY_ATTEMPTS})")
            last_error = "Connection error - is Ollama running?"
            if attempt < RETRY_ATTEMPTS:
                sleep(RETRY_DELAY)

        except requests.exceptions.RequestException as e:
            logger.error(f"BARBARA request failed: {e}")
            last_error = str(e)
            if attempt < RETRY_ATTEMPTS:
                sleep(RETRY_DELAY)

    # All retries exhausted - return error dict
    logger.warning(f"BARBARA unavailable after {RETRY_ATTEMPTS} attempts: {last_error}")
    return {"error": last_error or "Unknown error"}


# ───────────────────────── MAIN (for testing) ─────────────────────────


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    print("=== OLLAMA STATUS CHECK ===")
    status = get_ollama_status()
    print(json.dumps(status, indent=2))
    print()

    print("=== MARKET INTELLIGENCE ===")
    intel = get_market_intelligence()
    print(json.dumps(intel, indent=2, default=str))
