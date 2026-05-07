"""Visualization helpers for ORACLE V2 backtest reports."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REPORT_DIR = Path(__file__).resolve().parent.parent / "storage" / "reports"


class BacktestVisualizer:
    def __init__(self, report: dict):
        self.report = report

    def generate_all(self) -> list[str]:
        created: list[str] = []
        for generator in (
            self.generate_equity_curve_chart,
            self.generate_profit_by_scanner_chart,
            self.generate_profit_by_hour_heatmap,
        ):
            output = generator()
            if output:
                created.append(output)
        return created

    def generate_equity_curve_chart(self) -> str | None:
        plt = self._import_pyplot()
        if plt is None:
            return None
        equity_curve = self.report.get("equity_curve", [])
        if not equity_curve:
            return None
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        output = REPORT_DIR / "backtest_equity.png"
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(range(len(equity_curve)), equity_curve, color="#0b84f3", linewidth=2)
        ax.set_title("Oracle V2 Equity Curve")
        ax.set_xlabel("Trade Number")
        ax.set_ylabel("Capital")
        ax.grid(alpha=0.25)
        fig.tight_layout()
        fig.savefig(output, dpi=150)
        plt.close(fig)
        return str(output)

    def generate_profit_by_scanner_chart(self) -> str | None:
        plt = self._import_pyplot()
        if plt is None:
            return None
        profit_by_scanner = self.report.get("profit_by_scanner", {})
        if not profit_by_scanner:
            return None
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        output = REPORT_DIR / "backtest_profit_by_scanner.png"
        series = pd.Series(profit_by_scanner).sort_values(ascending=False)
        fig, ax = plt.subplots(figsize=(10, 5))
        colors = ["#2ca02c" if value >= 0 else "#d62728" for value in series.values]
        ax.bar(series.index, series.values, color=colors)
        ax.set_title("Backtest Profit by Scanner")
        ax.set_xlabel("Scanner")
        ax.set_ylabel("PnL")
        ax.tick_params(axis="x", rotation=30)
        fig.tight_layout()
        fig.savefig(output, dpi=150)
        plt.close(fig)
        return str(output)

    def generate_profit_by_hour_heatmap(self) -> str | None:
        plt = self._import_pyplot()
        if plt is None:
            return None
        profit_by_hour = self.report.get("profit_by_hour", {})
        if not profit_by_hour:
            return None
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        output = REPORT_DIR / "backtest_profit_by_hour.png"
        hour_series = pd.Series(profit_by_hour, dtype=float)
        heatmap = pd.DataFrame([hour_series.reindex([str(i) for i in range(24)], fill_value=0.0).values])
        fig, ax = plt.subplots(figsize=(12, 2.8))
        image = ax.imshow(heatmap, aspect="auto", cmap="RdYlGn")
        ax.set_title("Backtest Profit by Hour")
        ax.set_yticks([])
        ax.set_xticks(range(24))
        ax.set_xticklabels([str(i) for i in range(24)])
        ax.set_xlabel("Hour (UTC)")
        fig.colorbar(image, ax=ax, shrink=0.7, label="PnL")
        fig.tight_layout()
        fig.savefig(output, dpi=150)
        plt.close(fig)
        return str(output)

    def _import_pyplot(self):
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            return None
        return plt
