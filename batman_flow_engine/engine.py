import json
import hashlib
import subprocess
from core.database import init_db, save_engine_run
from core.signals import compute_risk_score
import logging
import datetime
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from typing import Any
from pathlib import Path

import yaml
from pydantic import BaseModel, validator

from core.equities import equity_metrics, returns_matrix
from core.crypto import crypto_metrics
from core.ollama_intel import get_market_intelligence, get_ollama_status
from core.alfred import run_quality_check
from core.flows import flow_score_equity, flow_score_crypto
from core.portfolio import portfolio_projection
from core.news_intel import narrative_intensity
from core.correlations import rolling_corr_stress, top_corr_edges, downside_corr_mean, top_downside_edges
from alerts import write_alerts
from core.scanner_cross_exchange import scan_cross_exchange
from core.scanner_basis import scan_basis
from core.p2p_latam import p2p_premium_analysis
from core.harvey import ingest_opportunities, daily_exposure as harvey_daily_exposure, DB_PATH as HARVEY_DB_PATH
from core.gordon import check as gordon_check

# Phase 2 scanners
from core.scanner_multi_exchange import scan_multi_exchange
from core.scanner_funding_rate import scan_funding_rates
from core.scanner_p2p_cross_currency import scan_cross_currency
from core.scanner_p2p_merchant import scan_merchant_spread
from core.scanner_stablecoin_depeg import scan_stablecoin_depeg

# Phase 3 scanners
from core.scanner_cross_platform_mxn import scan_cross_platform_mxn
from core.scanner_dex import scan_dex_cex
from core.scanner_futures_futures import scan_futures_futures
import os

# ───────────────────────── LOGGING ─────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(Path(__file__).resolve().parent / "engine.log")],
)
logger = logging.getLogger("engine")

# ───────────────────────── PATHS ─────────────────────────
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
REPORTS_DIR = STORAGE_DIR / "reports"
LOGS_DIR = STORAGE_DIR / "logs"
AUDIT_LOG = LOGS_DIR / "audit.log"
MAX_AUDIT_SIZE = 5 * 1024 * 1024  # 5 MB

LOCK_FILE = STORAGE_DIR / "engine.lock"

LATEST_FILE = STORAGE_DIR / "latest.json"
CONFIG_FILE = BASE_DIR / "config.yaml"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ───────────────────────── CONFIG ─────────────────────────
class EngineConfig(BaseModel):
    equities: list[str] = []
    crypto: list[str] = []
    portfolio_weights: dict[str, float] = {}

    max_workers: int = 8
    retry_attempts: int = 2
    retry_delay: float = 0.5

    # news
    news_enabled: bool = True
    news_keywords: list[str] = []
    news_lookback_hours: int = 48
    news_max_records: int = 250

    # stress
    corr_window: int = 60
    top_edges_k: int = 10

    @validator("equities", "crypto")
    def no_duplicates(cls, v):
        if len(v) != len(set(v)):
            dupes = [x for x in v if v.count(x) > 1]
            raise ValueError(f"Duplicados: {set(dupes)}")
        return v

    @validator("max_workers")
    def reasonable_workers(cls, v):
        if v < 1:
            raise ValueError("max_workers debe ser >= 1")
        if v > 32:
            logger.warning("max_workers > 32 puede saturar APIs")
        return v

    @validator("corr_window")
    def corr_window_reasonable(cls, v):
        if v < 20:
            logger.warning("corr_window < 20 puede ser muy ruidoso")
        return v


def load_config() -> EngineConfig:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Config no encontrado: {CONFIG_FILE}")

    raw = yaml.safe_load(CONFIG_FILE.read_text()) or {}

    equities = raw.get("watchlists", {}).get("equities", [])
    crypto = raw.get("watchlists", {}).get("crypto", [])
    weights = raw.get("portfolio", {}).get("weights", {})

    news = raw.get("news_intel", {}) or {}
    engine_cfg = raw.get("engine", {}) or {}
    windows = raw.get("signals", {}).get("windows", {}) or {}

    return EngineConfig(
        equities=equities,
        crypto=crypto,
        portfolio_weights=weights,
        max_workers=int(engine_cfg.get("max_workers", 8)),
        retry_attempts=int(engine_cfg.get("retry_attempts", 2)),
        retry_delay=float(engine_cfg.get("retry_delay", 0.5)),
        news_enabled=bool(news.get("enabled", True)),
        news_keywords=list(news.get("keywords", [])),
        news_lookback_hours=int(news.get("lookback_hours", 48)),
        news_max_records=int(news.get("max_records", 250)),
        corr_window=int(windows.get("corr_window", 60)),
        top_edges_k=int(engine_cfg.get("top_edges_k", 10)),
    )


# ───────────────────────── RETRY ─────────────────────────
def retry(attempts: int = 2, delay: float = 0.5):
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < attempts:
                        wait = delay * (2 ** (attempt - 1))
                        logger.warning(
                            "%s intento %d/%d falló: %s — reintentando en %.1fs",
                            func.__name__,
                            attempt,
                            attempts,
                            exc,
                            wait,
                        )
                        time.sleep(wait)
            raise last_exc

        return wrapper

    return decorator


# ───────────────────────── PROCESSORS ─────────────────────────
def process_equity(ticker: str, retries: int, delay: float):
    @retry(attempts=retries, delay=delay)
    def _inner():
        m = equity_metrics(ticker)
        flow = None
        if m.get("status") in ("ok", "ok_daily"):
            flow = flow_score_equity(
                m.get("vol_z", 0),
                m.get("rvol", 1),
                m.get("rv20_ann", 0),
                m.get("dollar_vol", 1),
            )
        return ticker, m, flow

    return _inner()


def process_crypto(symbol: str, retries: int, delay: float):
    @retry(attempts=retries, delay=delay)
    def _inner():
        m = crypto_metrics(symbol)
        flow = None
        if m.get("status") == "ok":
            flow = flow_score_crypto(
                m.get("spread", 0),
                m.get("depth_0_5pct", 1),
                m.get("rv_ann", 0),
                m.get("dollar_vol_1h", 1),
            )
        return symbol, m, flow

    return _inner()


# ───────────────────────── HASH / AUDIT ─────────────────────────
def hash_data(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def write_audit(ts: str, digest: str, filename: str):
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        if AUDIT_LOG.exists() and AUDIT_LOG.stat().st_size > MAX_AUDIT_SIZE:
            rotated = AUDIT_LOG.with_name("audit.log.1")
            if rotated.exists():
                rotated.unlink()
            AUDIT_LOG.rename(rotated)
    except Exception:
        pass

    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{ts} | {digest} | {filename}\n")


# ───────────────────────── ENGINE ─────────────────────────
def _build_engine_result(cfg: EngineConfig) -> dict[str, Any]:
    start = datetime.datetime.now(datetime.timezone.utc)

    result: dict[str, Any] = {
        "timestamp": start.isoformat(),
        "equities": {},
        "crypto": {},
        "flows": {},
        "portfolio": {},
        "stress": {},
        "narrative": {},
        "errors": [],
    }

    # Parallel collection: equities + crypto
    with ThreadPoolExecutor(max_workers=cfg.max_workers) as pool:
        futs = {}
        for t in cfg.equities:
            futs[pool.submit(process_equity, t, cfg.retry_attempts, cfg.retry_delay)] = ("equity", t)
        for s in cfg.crypto:
            futs[pool.submit(process_crypto, s, cfg.retry_attempts, cfg.retry_delay)] = ("crypto", s)

        for fut in as_completed(futs):
            kind, name = futs[fut]
            try:
                sym, metrics, flow = fut.result()
                if kind == "equity":
                    result["equities"][sym] = metrics
                else:
                    result["crypto"][sym] = metrics
                if flow is not None:
                    result["flows"][sym] = flow
                logger.info("✓ %s %s", kind, sym)
            except Exception as exc:
                logger.error("✗ %s %s: %s", kind, name, exc, exc_info=True)
                target = "equities" if kind == "equity" else "crypto"
                result[target][name] = {"error": str(exc)}
                result["errors"].append(
                    {
                        "asset": name,
                        "type": kind,
                        "error": str(exc),
                        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    }
                )

    # Portfolio + Stress (single returns_matrix call)
    if cfg.equities:
        try:
            rets = returns_matrix(cfg.equities)
            result["portfolio"] = portfolio_projection(rets, cfg.portfolio_weights)

            stress = rolling_corr_stress(rets, window=cfg.corr_window)
            edges_df = top_corr_edges(rets, window=cfg.corr_window, k=cfg.top_edges_k)
            edges = edges_df.to_dict(orient="records") if not edges_df.empty else []

            down = downside_corr_mean(rets, benchmark="SPY", window=cfg.corr_window, q=0.2)
            down_edges_df = top_downside_edges(rets, benchmark="SPY", window=cfg.corr_window, q=0.2, k=cfg.top_edges_k)
            down_edges = down_edges_df.to_dict(orient="records") if not down_edges_df.empty else []

            vol_z_vals = []
            for sym, data in result.get("equities", {}).items():
                if isinstance(data, dict):
                    vz = data.get("vol_z")
                    if vz is not None:
                        try:
                            v = float(vz)
                            if not np.isnan(v):
                                vol_z_vals.append(v)
                        except (TypeError, ValueError):
                            pass

            if vol_z_vals:
                vol_z_mean = float(np.mean(vol_z_vals))
                vol_z_p90 = float(np.percentile(vol_z_vals, 90))
                vol_z_gt2_pct = float(sum(v > 2 for v in vol_z_vals) / len(vol_z_vals))
            else:
                vol_z_mean, vol_z_p90, vol_z_gt2_pct = None, None, 0.0

            vol_shock = {"vol_z_mean": vol_z_mean, "vol_z_p90": vol_z_p90, "vol_z_gt2_pct": vol_z_gt2_pct}

            cs = stress.get("corr_stress") or 0.0
            dc = down.get("downside_corr_mean") or 0.0
            vg = vol_z_gt2_pct or 0.0

            triggers = []
            regime_label = "NORMAL"

            if (cs > 0.75 and dc > 0.75) or (vg >= 0.75 and cs > 0.55):
                regime_label = "PANIC"
                if cs > 0.75 and dc > 0.75:
                    triggers.extend(["corr_stress>0.75", "downside_corr_mean>0.75"])
                if vg >= 0.75 and cs > 0.55:
                    triggers.extend(["vol_z_gt2_pct>=0.75", "corr_stress>0.55"])

            if regime_label == "NORMAL":
                stress_conds = [
                    ("corr_stress>0.55", cs > 0.55),
                    ("downside_corr_mean>0.55", dc > 0.55),
                    ("vol_z_gt2_pct>=0.40", vg >= 0.40),
                ]
                if sum(1 for _, c in stress_conds if c) >= 2:
                    regime_label = "STRESS"
                    triggers.extend(name for name, c in stress_conds if c)

            if regime_label == "NORMAL":
                tension_conds = [
                    ("corr_stress>0.40", cs > 0.40),
                    ("downside_corr_mean>0.40", dc > 0.40),
                    ("vol_z_gt2_pct>=0.25", vg >= 0.25),
                ]
                if any(c for _, c in tension_conds):
                    regime_label = "TENSION"
                    triggers.extend(name for name, c in tension_conds if c)

            triggers = sorted(set(triggers))

            result["stress"] = {
                **stress,
                "top_edges": edges,
                "downside_corr_mean": down.get("downside_corr_mean"),
                "downside_quantile": 0.2,
                "tail_points": down.get("tail_points"),
                "downside_top_edges": down_edges,
                "vol_shock": vol_shock,
                "regime": {"label": regime_label, "triggers": triggers},
            }

            # Deltas vs prev
            prev_stress = None
            prev_path = STORAGE_DIR / "prev.json"
            if prev_path.exists():
                try:
                    prev_stress = json.load(open(prev_path)).get("stress")
                except Exception:
                    pass

            cs_curr = result["stress"].get("corr_stress")
            dc_curr = result["stress"].get("downside_corr_mean")
            vg_curr = result["stress"].get("vol_shock", {}).get("vol_z_gt2_pct")
            prev_cs = prev_dc = prev_vg = prev_regime = None
            if prev_stress and isinstance(prev_stress, dict):
                prev_cs = prev_stress.get("corr_stress")
                prev_dc = prev_stress.get("downside_corr_mean")
                prev_vg = prev_stress.get("vol_shock", {}).get("vol_z_gt2_pct")
                prev_regime = prev_stress.get("regime", {}).get("label")

            result["stress"]["deltas"] = {
                "corr_stress_delta": (cs_curr - prev_cs) if (cs_curr is not None and prev_cs is not None) else None,
                "downside_corr_delta": (dc_curr - prev_dc) if (dc_curr is not None and prev_dc is not None) else None,
                "vol_z_gt2_pct_delta": (vg_curr - prev_vg) if (vg_curr is not None and prev_vg is not None) else None,
                "prev_regime": prev_regime,
                "regime_changed": (prev_regime is not None and prev_regime != result["stress"]["regime"]["label"]),
            }

        except Exception as exc:
            result["portfolio"] = {"error": str(exc)}
            result["stress"] = {"error": str(exc)}
            result["errors"].append(
                {
                    "asset": "portfolio/stress",
                    "type": "portfolio/stress",
                    "error": str(exc),
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            )

    # Narrative
    try:
        if cfg.news_enabled and cfg.news_keywords:
            result["narrative"] = narrative_intensity(
                cfg.news_keywords, lookback_hours=cfg.news_lookback_hours, max_records=cfg.news_max_records
            )
        else:
            result["narrative"] = {"status": "disabled_or_no_keywords"}
    except Exception as exc:
        result["narrative"] = {"error": str(exc)}
        result["errors"].append(
            {
                "asset": "narrative",
                "type": "narrative",
                "error": str(exc),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        )

    end = datetime.datetime.now(datetime.timezone.utc)

    # ───────────────────────── DATA QUALITY ─────────────────────────
    equities_total = len(cfg.equities)
    crypto_total = len(cfg.crypto)
    equities_ok = sum(1 for v in result["equities"].values() if v.get("status") in ["ok", "ok_daily"])
    crypto_ok = sum(1 for v in result["crypto"].values() if v.get("status") == "ok")
    equities_ratio = equities_ok / equities_total if equities_total else 1.0
    crypto_ratio = crypto_ok / crypto_total if crypto_total else 1.0
    overall_ratio = min(equities_ratio, crypto_ratio)

    if overall_ratio >= 0.85:
        dq_status, breaker = "ok", False
    elif overall_ratio >= 0.60:
        dq_status, breaker = "partial", False
    else:
        dq_status, breaker = "degraded", True

    result["dq"] = {
        "equities_ok_ratio": round(equities_ratio, 3),
        "crypto_ok_ratio": round(crypto_ratio, 3),
        "overall_status": dq_status,
        "breaker_triggered": breaker,
    }

    if breaker:
        regime = result.get("stress", {}).get("regime")
        if isinstance(regime, dict):
            regime["label"] = "DATA_DEGRADED"
            regime.setdefault("triggers", []).append("dq_breaker")

    result["meta"] = {
        "duration_sec": (end - start).total_seconds(),
        "equities_total": len(cfg.equities),
        "crypto_total": len(cfg.crypto),
        "equities_ok": equities_ok,
        "crypto_ok": crypto_ok,
        "errors": len(result["errors"]),
    }

    try:
        init_db()
        save_engine_run(result)
        compute_risk_score(result)
    except Exception:
        pass

    try:
        from core.dual_writer import log_engine_run

        log_engine_run(result)
    except Exception:
        pass

    # ───────────────────────── ALL 11 SCANNERS ─────────────────────────
    scanner_results: list[Any] = []

    # Scanner A: Cross-Exchange
    try:
        scanner_results.append(scan_cross_exchange(log_to_file=True))
    except Exception as e:
        logger.error("Scanner A (cross-exchange) failed: %s", e)

    # Scanner B: Spot vs Futures Basis
    try:
        scanner_results.append(scan_basis(log_to_file=True))
    except Exception as e:
        logger.error("Scanner B (basis) failed: %s", e)

    # Scanner C: P2P Premium
    try:
        scanner_results.append(p2p_premium_analysis(log_to_file=True))
    except Exception as e:
        logger.error("Scanner C (p2p premium) failed: %s", e)

    # Scanner D: Multi-Exchange (20 coins × 5 exchanges)
    try:
        scanner_results.append(scan_multi_exchange(log_to_file=True))
    except Exception as e:
        logger.error("Scanner D (multi-exchange) failed: %s", e)

    # Scanner E: Funding Rate
    try:
        scanner_results.append(scan_funding_rates(log_to_file=True))
    except Exception as e:
        logger.error("Scanner E (funding rate) failed: %s", e)

    # Scanner F: Cross-Currency P2P
    try:
        scanner_results.append(scan_cross_currency(log_to_file=True))
    except Exception as e:
        logger.error("Scanner F (cross-currency) failed: %s", e)

    # Scanner G: P2P Merchant Spread
    try:
        scanner_results.append(scan_merchant_spread(log_to_file=True))
    except Exception as e:
        logger.error("Scanner G (merchant spread) failed: %s", e)

    # Scanner H: Stablecoin Depeg
    try:
        scanner_results.append(scan_stablecoin_depeg(log_to_file=True))
    except Exception as e:
        logger.error("Scanner H (stablecoin depeg) failed: %s", e)

    # Scanner I: Cross-Platform MXN
    try:
        scanner_results.append(scan_cross_platform_mxn(log_to_file=True))
    except Exception as e:
        logger.error("Scanner I (cross-platform MXN) failed: %s", e)

    # Scanner J: DEX vs CEX (Uniswap/PancakeSwap/Raydium vs Binance)
    try:
        scanner_results.append(scan_dex_cex(log_to_file=True))
    except Exception as e:
        logger.error("Scanner J (DEX vs CEX) failed: %s", e)

    # Scanner K: Futures vs Futures (Binance/OKX/Bybit perpetuals)
    try:
        scanner_results.append(scan_futures_futures(log_to_file=True))
    except Exception as e:
        logger.error("Scanner K (futures vs futures) failed: %s", e)

    current_cycle_opportunities = _current_cycle_opportunities(scanner_results)
    current_cycle_total = len(current_cycle_opportunities)
    current_cycle_viable = sum(1 for opportunity in current_cycle_opportunities if opportunity.get("viable") is True)
    result["_current_cycle_opportunity_counts"] = {
        "total": current_cycle_total,
        "viable": current_cycle_viable,
    }
    result["meta"]["opportunities_total_cycle"] = current_cycle_total
    result["meta"]["opportunities_viable_cycle"] = current_cycle_viable

    return result


def _enrich_runtime_metadata(result: dict[str, Any]) -> None:
    ollama_status = get_ollama_status()
    ollama_available = ollama_status.get("available", False)
    result["ollama_status"] = "AVAILABLE" if ollama_available else "UNAVAILABLE"
    result["ollama_details"] = ollama_status

    if ollama_available:
        logger.info("Generating market intelligence with Ollama...")
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(get_market_intelligence)
                try:
                    intelligence = future.result(timeout=45)
                    result["intelligence"] = intelligence
                    logger.info("Intelligence generated: %s", intelligence.get("status", "unknown"))
                except TimeoutError:
                    logger.warning("Intelligence generation timed out after 45s - skipping")
                    result["intelligence"] = {"status": "timeout", "error": "Timed out after 45s"}
        except Exception as exc:
            logger.error("Intelligence generation failed: %s", exc)
            result["intelligence"] = {"status": "error", "error": str(exc)}
    else:
        logger.info("Ollama unavailable - skipping intelligence generation")

    logger.info("Running ALFRED data quality check...")
    try:
        data_quality = run_quality_check()
        result["data_quality"] = data_quality
        logger.info("Data quality: %.2f%% (%s)", data_quality["dq_score"] * 100, data_quality["status"])
    except Exception as exc:
        logger.error("ALFRED quality check failed: %s", exc)
        result["data_quality"] = {"status": "ERROR", "error": str(exc)}


def _persist_run(result: dict[str, Any]) -> None:
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    digest = hash_data(result)
    report_path = REPORTS_DIR / f"{ts}.json"
    payload = json.dumps(result, indent=2, default=str)

    report_path.write_text(payload, encoding="utf-8")
    LATEST_FILE.write_text(payload, encoding="utf-8")

    write_audit(ts, digest, report_path.name)
    write_alerts(STORAGE_DIR, flow_threshold=6.0)

    logger.info("Report: %s", report_path)
    logger.info("Hash: %s", digest)


def _viable_opportunity_ratio(n: int = 50) -> float | None:
    """Return fraction of last *n* opportunity records where viable=True.

    Reads from opportunities.jsonl. Returns None if the file is absent or
    contains fewer than 5 records (too small a sample to be meaningful).
    """
    log = LOGS_DIR / "opportunities.jsonl"
    if not log.exists():
        return None
    try:
        lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
        records = [json.loads(ln) for ln in lines[-n:]]
        if len(records) < 5:
            return None
        viable = sum(1 for r in records if r.get("viable") is True)
        return round(viable / len(records), 4)
    except Exception:
        return None


def _current_cycle_opportunities(scanner_results: list[Any]) -> list[dict[str, Any]]:
    """Normalize scanner return values into current-cycle opportunity records."""
    opportunities: list[dict[str, Any]] = []

    for scanner_result in scanner_results:
        if isinstance(scanner_result, list):
            opportunities.extend(item for item in scanner_result if isinstance(item, dict))
            continue

        if not isinstance(scanner_result, dict):
            continue

        nested_results = scanner_result.get("results")
        if isinstance(nested_results, dict):
            opportunities.extend(
                item for item in nested_results.values() if isinstance(item, dict) and item.get("status") == "ok"
            )
            continue

        opportunities.append(scanner_result)

    return opportunities


def _current_cycle_opportunity_counts(result: dict[str, Any]) -> tuple[int, int]:
    """Return same-cycle counts, preferring in-memory scanner output over persisted state."""
    direct_counts = result.get("_current_cycle_opportunity_counts")
    if isinstance(direct_counts, dict):
        total = direct_counts.get("total")
        viable = direct_counts.get("viable")
        if isinstance(total, int) and isinstance(viable, int):
            return total, viable

    meta = result.get("meta") or {}
    total = meta.get("opportunities_total_cycle")
    viable = meta.get("opportunities_viable_cycle")
    if isinstance(total, int) and isinstance(viable, int):
        return total, viable

    return 0, 0


# ───────────────────────── COMMANDER ─────────────────────────
def _harvey_is_initialized() -> bool:
    """Return True if HARVEY has recorded at least one signal in the last 2 hours.

    A 2-hour window covers 6 missed engine cycles (engine runs every 20 min).
    Returns False if the DB is absent, the table is missing, or no recent row exists.
    """
    if not HARVEY_DB_PATH.exists():
        return False
    try:
        import sqlite3 as _sqlite3

        with _sqlite3.connect(HARVEY_DB_PATH) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "signals" not in tables:
                return False
            (count,) = conn.execute(
                "SELECT COUNT(*) FROM signals WHERE timestamp >= datetime('now', '-2 hours')"
            ).fetchone()
            return count > 0
    except Exception:
        return False


def commander_decision(result: dict[str, Any]) -> dict[str, Any]:
    """
    COMMANDER gate — explicit viability decision for opportunity emission.

    Called after GORDON check, before HARVEY ingestion. ALFRED and GORDON are
    hard pre-ingestion blockers. HARVEY freshness is warning-only here so the
    ingestion step can self-heal a stale ledger.

    Gates:
        1. alfred_dq   — data_quality.dq_score >= 0.80
        2. gordon_ok   — gordon.status == "OK" (ALERT also blocks)
        3. harvey_init — HARVEY has recorded a signal in the last 2 hours
                          (warning-only pre-ingestion)

    Returns:
        {
            "viable":     bool,
            "blocked_by": [str, ...],   # empty when viable=True
            "gates":      [{"gate": str, "passed": bool, ...}, ...],
            "timestamp":  str,
        }
    """
    gates: list[dict] = []
    blocked_by: list[str] = []

    # Gate 1: ALFRED dq_score >= 0.80
    dq_score = (result.get("data_quality") or {}).get("dq_score")
    if dq_score is None:
        gates.append({"gate": "alfred_dq", "passed": False, "dq_score": None, "reason": "dq_score_missing"})
        blocked_by.append("alfred_dq_score_missing")
    elif dq_score < 0.80:
        gates.append(
            {
                "gate": "alfred_dq",
                "passed": False,
                "dq_score": round(dq_score, 4),
                "reason": f"dq_score_{dq_score:.2f}_below_0.80",
            }
        )
        blocked_by.append(f"alfred_dq_score_{dq_score:.2f}_below_0.80")
    else:
        gates.append({"gate": "alfred_dq", "passed": True, "dq_score": round(dq_score, 4)})

    # Gate 2: GORDON status must be exactly "OK" (ALERT is not sufficient)
    gordon_status = (result.get("gordon") or {}).get("status")
    if gordon_status != "OK":
        gates.append(
            {
                "gate": "gordon_ok",
                "passed": False,
                "gordon_status": gordon_status,
                "reason": f"gordon_status_{gordon_status}",
            }
        )
        blocked_by.append(f"gordon_status_{gordon_status}")
    else:
        gates.append({"gate": "gordon_ok", "passed": True, "gordon_status": gordon_status})

    # Gate 3: HARVEY freshness — at least one signal recorded in the last 2 hours
    harvey_ready = _harvey_is_initialized()
    if not harvey_ready:
        gates.append({"gate": "harvey_init", "passed": False, "reason": "harvey_no_recent_signals"})
        logger.warning("COMMANDER warning: HARVEY stale before ingestion — harvey_no_recent_signals")
    else:
        gates.append({"gate": "harvey_init", "passed": True})

    viable = not blocked_by
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if viable:
        logger.info("COMMANDER decision: viable=True — all gates passed")
    else:
        logger.warning("COMMANDER decision: viable=False — blocked_by=%s", blocked_by)

    return {
        "viable": viable,
        "blocked_by": blocked_by,
        "gates": gates,
        "timestamp": ts,
    }


def run_engine(cfg: EngineConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    logger.info("ENGINE START — equities=%d crypto=%d scanners=11", len(cfg.equities), len(cfg.crypto))

    if LOCK_FILE.exists():
        try:
            stored_pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            stored_pid = None

        pid_is_engine = False
        if stored_pid is not None:
            try:
                os.kill(stored_pid, 0)  # signal 0 = existence check only
                # PID exists — verify it is actually our engine process, not a recycled PID.
                # PermissionError means the process is owned by another user → definitely not us.
                result = subprocess.run(
                    ["ps", "-p", str(stored_pid), "-o", "args="],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                cmdline = result.stdout.strip()
                pid_is_engine = bool(cmdline) and any(kw in cmdline for kw in ("engine.py", "run_loop.py", "runner.py"))
            except ProcessLookupError:
                pid_is_engine = False  # process is gone
            except PermissionError:
                pid_is_engine = False  # owned by another user — PID was recycled
            except Exception:
                # ps failed for an unexpected reason; be conservative
                pid_is_engine = True

        if pid_is_engine:
            logger.warning("Engine already running (PID %s). Aborting.", stored_pid)
            return {"status": "already_running", "lock_file": str(LOCK_FILE), "pid": stored_pid}

        logger.warning(
            "Stale lock file found (PID %s — not an engine process) — removing and continuing.",
            stored_pid,
        )
        LOCK_FILE.unlink(missing_ok=True)

    try:
        LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
        result = _build_engine_result(cfg)
        _enrich_runtime_metadata(result)

        # Compute HARVEY daily exposure (single source of truth) before gate checks
        harvey_exposure: dict[str, float] = {}
        for _fiat in ("MXN", "ARS"):
            try:
                harvey_exposure[_fiat] = harvey_daily_exposure(_fiat)
            except Exception as _exc:
                logger.warning("HARVEY daily_exposure(%s) failed: %s", _fiat, _exc)

        # GORDON gate — runs after ALFRED, before HARVEY
        gordon_result = gordon_check(result, exposure=harvey_exposure)
        result["gordon"] = gordon_result
        if gordon_result["status"] == "BLOCKED":
            logger.warning(
                "GORDON BLOCKED — signal emission aborted: %s",
                gordon_result["blocked_by"],
            )
            result.pop("_current_cycle_opportunity_counts", None)
            _persist_run(result)
            return result

        # COMMANDER gate — explicit viability decision
        commander = commander_decision(result)
        result["commander"] = commander

        # ───────────── RISK SCORES — computed after all gates, persisted per cycle ─────────────
        try:
            from database.postgres import get_concentration_risk, save_risk_score

            _dq = (result.get("data_quality") or {}).get("dq_score")
            _gordon_status = gordon_result.get("status")
            _regime_label = ((result.get("stress") or {}).get("regime") or {}).get("label")
            _cycle_opps_total, _cycle_opps_viable = _current_cycle_opportunity_counts(result)

            # operational_readiness: data reliability + governance gate
            _gordon_ok = 1.0 if _gordon_status == "OK" else (0.5 if _gordon_status == "ALERT" else 0.0)
            _operational_readiness = round((_dq or 0.0) * 0.6 + _gordon_ok * 0.4, 4)

            # technical_risk: ALFRED dq_score (1.0 = clean data)
            _technical_risk = round(_dq or 0.0, 4)

            # market_behavior: regime label lookup
            _regime_map = {"NORMAL": 1.0, "TENSION": 0.85, "STRESS": 0.5, "DATA_DEGRADED": 0.3, "PANIC": 0.1}
            _market_behavior = _regime_map.get(_regime_label, 0.7)

            # governance_risk: control-state composite
            #   gordon_ok (0/0.5/1.0) × 0.50 — gate health is the primary signal
            #   dq_score            × 0.30 — poor data quality degrades governance confidence
            #   market_behavior     × 0.20 — market stress elevates governance risk
            # Reaches 1.0 only when GORDON=OK + perfect data + NORMAL regime.
            _governance_risk = round(_gordon_ok * 0.50 + (_dq or 0.0) * 0.30 + _market_behavior * 0.20, 4)

            # financial_attractiveness: viable opportunity ratio from this engine run
            # 1.0 = all current-cycle opps are viable; 0.0 = none are; None = insufficient data
            _financial_attractiveness = (
                round(_cycle_opps_viable / _cycle_opps_total, 4) if _cycle_opps_total >= 5 else None
            )

            # concentration_risk: from portfolio_positions via PG
            _conc = get_concentration_risk()
            _concentration_risk = _conc.get("score")

            # composite: weighted average of available scores
            _score_weights = [
                (_operational_readiness, 0.20),
                (_technical_risk, 0.15),
                (_governance_risk, 0.15),
                (_market_behavior, 0.15),
                (_financial_attractiveness, 0.15) if _financial_attractiveness is not None else None,
                (_concentration_risk, 0.20) if _concentration_risk is not None else None,
            ]
            _valid = [(s, w) for item in _score_weights if item is not None for s, w in [item]]
            _total_w = sum(w for _, w in _valid)
            _composite = round(sum(s * w for s, w in _valid) / _total_w, 4) if _total_w > 0 else None

            _cycle_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
            _risk_payload = {
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "cycle_id": _cycle_id,
                "operational_readiness": _operational_readiness,
                "concentration_risk": _concentration_risk,
                "technical_risk": _technical_risk,
                "governance_risk": _governance_risk,
                "market_behavior": _market_behavior,
                "financial_attractiveness": _financial_attractiveness,
                "composite_score": _composite,
                "dq_score": _dq,
                "gordon_status": _gordon_status,
                "regime_label": _regime_label,
                "top_position_pct": _conc.get("top_position_pct"),
                "hhi": _conc.get("hhi"),
            }
            result["risk_scores"] = _risk_payload
            save_risk_score(_risk_payload)
            logger.info(
                "RISK SCORES — operational_readiness=%.3f concentration=%.3f composite=%s",
                _operational_readiness,
                _concentration_risk if _concentration_risk is not None else 0.0,
                f"{_composite:.3f}" if _composite is not None else "N/A",
            )
        except Exception as _exc:
            logger.warning("Risk score computation failed (non-fatal): %s", _exc)
            result.setdefault("risk_scores", {"error": str(_exc)})

        result.pop("_current_cycle_opportunity_counts", None)
        _persist_run(result)
        if commander["viable"]:
            ingest_opportunities()
        else:
            logger.warning(
                "COMMANDER blocked — opportunity ingestion skipped: %s",
                commander["blocked_by"],
            )
        return result
    finally:
        try:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()
        except Exception:
            pass


def main():
    run_engine()


if __name__ == "__main__":
    main()
