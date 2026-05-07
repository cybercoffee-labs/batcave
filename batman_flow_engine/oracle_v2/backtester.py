"""Historical backtester for Batman opportunity logs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

OPPORTUNITIES_FILE = Path(__file__).resolve().parent.parent / "storage" / "logs" / "opportunities.jsonl"
REPORT_FILE = Path(__file__).resolve().parent.parent / "storage" / "backtest_results.json"
SLIPPAGE_PCT = 0.3
COMMISSION_PCT = 0.1


@dataclass
class SimulatedTrade:
    opp_id: str
    ts: str
    scanner_id: str
    asset: str
    pair: str
    hour: int
    gross_edge_pct: float
    realized_edge_pct: float
    capital_before: float
    pnl: float
    capital_after: float
    outcome: str
    duration_minutes: float = 0.0


class Backtester:
    def __init__(self, capital: float = 1000.0):
        self.initial_capital = capital
        self.capital = capital
        self.trades: list[dict[str, Any]] = []
        self._report: dict[str, Any] | None = None

    def run(self, min_edge: float = 1.0, max_trades_per_day: int = 5):
        """
        Replay all opportunities from JSONL.
        Simulate execution with:
        - Entry at logged price
        - Exit at logged edge_net minus slippage (0.3%)
        - Commission: 0.1% per trade
        - Max trades per day limit
        """
        self.capital = self.initial_capital
        self.trades = []
        self._report = None

        df = self._load_opportunities()
        if df.empty:
            return self.trades

        eligible = df[df["edge_net"] >= float(min_edge)].copy()
        if eligible.empty:
            return self.trades

        eligible["trade_day"] = eligible["ts"].dt.date
        eligible.sort_values(["trade_day", "edge_net", "ts"], ascending=[True, False, True], inplace=True)
        selected = eligible.groupby("trade_day", group_keys=False).head(int(max_trades_per_day)).copy()
        selected.sort_values("ts", inplace=True)

        for row in selected.itertuples(index=False):
            capital_before = self.capital
            realized_edge_pct = float(row.edge_net) - SLIPPAGE_PCT - COMMISSION_PCT
            pnl = capital_before * (realized_edge_pct / 100.0)
            self.capital += pnl
            trade = SimulatedTrade(
                opp_id=str(row.opp_id),
                ts=row.ts.isoformat(),
                scanner_id=str(row.scanner_id),
                asset=str(row.asset),
                pair=str(row.pair),
                hour=int(row.hour),
                gross_edge_pct=round(float(row.edge_net), 6),
                realized_edge_pct=round(realized_edge_pct, 6),
                capital_before=round(capital_before, 6),
                pnl=round(pnl, 6),
                capital_after=round(self.capital, 6),
                outcome="win" if pnl >= 0 else "loss",
            )
            self.trades.append(asdict(trade))

        return self.trades

    def generate_report(self) -> dict:
        """
        Returns:
        - total_trades
        - winning_trades
        - losing_trades
        - win_rate
        - total_pnl
        - max_drawdown
        - sharpe_ratio
        - best_trade
        - worst_trade
        - avg_trade_duration
        - profit_by_scanner (which scanner makes most money)
        - profit_by_hour (best hours to trade)
        - profit_by_pair (best pairs)
        - equity_curve (list of capital over time)
        """
        if not self.trades:
            report = {
                "initial_capital": round(self.initial_capital, 2),
                "final_capital": round(self.capital, 2),
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
                "best_trade": None,
                "worst_trade": None,
                "avg_trade_duration": 0.0,
                "profit_by_scanner": {},
                "profit_by_hour": {},
                "profit_by_pair": {},
                "equity_curve": [round(self.initial_capital, 2)],
            }
            self._write_report(report)
            self._report = report
            return report

        trades_df = pd.DataFrame(self.trades)
        equity_series = trades_df["capital_after"]
        running_peak = equity_series.cummax()
        drawdowns = ((equity_series - running_peak) / running_peak.replace(0, pd.NA)) * 100.0
        returns = trades_df["pnl"] / trades_df["capital_before"].replace(0, pd.NA)

        total_trades = int(len(trades_df))
        winning_trades = int((trades_df["pnl"] >= 0).sum())
        losing_trades = int((trades_df["pnl"] < 0).sum())
        win_rate = (winning_trades / total_trades) * 100.0 if total_trades else 0.0

        report = {
            "initial_capital": round(self.initial_capital, 2),
            "final_capital": round(self.capital, 2),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2),
            "total_pnl": round(self.capital - self.initial_capital, 2),
            "max_drawdown": round(abs(drawdowns.min()) if not drawdowns.empty else 0.0, 2),
            "sharpe_ratio": round(self._sharpe_ratio(returns), 4),
            "best_trade": self._trade_snapshot(trades_df.loc[trades_df["pnl"].idxmax()]),
            "worst_trade": self._trade_snapshot(trades_df.loc[trades_df["pnl"].idxmin()]),
            "avg_trade_duration": round(float(trades_df["duration_minutes"].mean()), 2),
            "profit_by_scanner": self._rounded_series(trades_df.groupby("scanner_id")["pnl"].sum()),
            "profit_by_hour": self._rounded_series(trades_df.groupby("hour")["pnl"].sum(), key_cast=int),
            "profit_by_pair": self._rounded_series(trades_df.groupby("pair")["pnl"].sum()),
            "equity_curve": [round(self.initial_capital, 2)] + [round(v, 2) for v in equity_series.tolist()],
        }
        self._write_report(report)
        self._report = report
        return report

    def _load_opportunities(self) -> pd.DataFrame:
        if not OPPORTUNITIES_FILE.exists():
            return pd.DataFrame()

        rows: list[dict[str, Any]] = []
        for raw_line in OPPORTUNITIES_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(payload)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        if "ts" not in df.columns:
            return pd.DataFrame()

        df["ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=True)
        df = df[df["ts"].notna()].copy()
        if df.empty:
            return df

        df["edge_net"] = pd.to_numeric(df.get("edge_net"), errors="coerce").fillna(0.0)
        df["scanner_id"] = df.get("scanner_id", pd.Series(dtype=str)).fillna("UNKNOWN")
        df["asset"] = df.get("asset", pd.Series(dtype=str)).fillna("UNKNOWN")
        df["market"] = df.get("market", pd.Series(dtype=str)).fillna("")
        df["route"] = df.get("route", pd.Series(dtype=str)).fillna("")
        df["hour"] = df["ts"].dt.hour
        df["pair"] = df.apply(self._pair_label, axis=1)
        return df

    def _pair_label(self, row: pd.Series) -> str:
        route = str(row.get("route", "") or "").strip()
        if route:
            return route
        market = str(row.get("market", "") or "").strip()
        asset = str(row.get("asset", "") or "UNKNOWN").strip()
        if market and market != asset:
            return f"{asset}/{market}"
        return asset or "UNKNOWN"

    def _sharpe_ratio(self, returns: pd.Series) -> float:
        clean = returns.dropna()
        if clean.empty:
            return 0.0
        std = float(clean.std(ddof=0))
        if std == 0:
            return 0.0
        return (float(clean.mean()) / std) * (len(clean) ** 0.5)

    def _trade_snapshot(self, row: pd.Series) -> dict:
        return {
            "opp_id": str(row["opp_id"]),
            "scanner_id": str(row["scanner_id"]),
            "pair": str(row["pair"]),
            "pnl": round(float(row["pnl"]), 2),
            "realized_edge_pct": round(float(row["realized_edge_pct"]), 4),
            "ts": str(row["ts"]),
        }

    def _rounded_series(self, series: pd.Series, key_cast: type | None = None) -> dict:
        if series.empty:
            return {}
        result = {}
        for key, value in series.sort_values(ascending=False).items():
            out_key = key_cast(key) if key_cast is not None else str(key)
            result[str(out_key)] = round(float(value), 2)
        return result

    def _write_report(self, report: dict[str, Any]) -> None:
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    backtester = Backtester(capital=1000.0)
    backtester.run(min_edge=1.0)
    print(json.dumps(backtester.generate_report(), indent=2))
