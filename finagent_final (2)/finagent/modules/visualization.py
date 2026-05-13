"""
modules/visualization.py — Visualization Module
================================================
Produces four publication-quality charts as required by the brief:

  Chart 1 — Price Trend + Volume Overlay  (line chart / bar volume)
  Chart 2 — Correlation Heatmap           (daily returns across assets)
  Chart 3 — Return Distribution           (histogram + KDE per asset)
  Chart 4 — Rolling Statistics            (moving averages + Bollinger Bands)

All charts are saved to CHARTS_DIR as high-resolution PNGs.
"""

import logging
import os
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")   # headless — no display needed

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import seaborn as sns

from config import (
    CHART_DPI,
    CHARTS_DIR,
    COLORS,
    FIG_SQUARE,
    FIG_TALL,
    FIG_WIDE,
    MA_WINDOWS,
)

logger = logging.getLogger(__name__)

# ─── Style ────────────────────────────────────────────────────────────────────
sns.set_theme(style="darkgrid", font_scale=1.05)
plt.rcParams.update({
    "figure.facecolor": "#1a1a2e",
    "axes.facecolor":   "#16213e",
    "axes.edgecolor":   "#0f3460",
    "axes.labelcolor":  "#e0e0e0",
    "xtick.color":      "#e0e0e0",
    "ytick.color":      "#e0e0e0",
    "text.color":       "#e0e0e0",
    "grid.color":       "#0f3460",
    "grid.linewidth":   0.6,
    "legend.facecolor": "#16213e",
    "legend.edgecolor": "#0f3460",
})


# ─── Public helpers ───────────────────────────────────────────────────────────

def _save(fig: plt.Figure, filename: str, run_id: str = "") -> str:
    """Save figure to CHARTS_DIR, optionally inside a run-specific sub-folder."""
    if run_id:
        out_dir = os.path.join(CHARTS_DIR, run_id)
    else:
        out_dir = CHARTS_DIR
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    fig.savefig(path, dpi=CHART_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("  Saved chart → %s", path)
    return path


# ─── Chart 1: Price Trend + Volume Overlay ───────────────────────────────────

def chart_price_volume(
    cleaned: Dict[str, pd.DataFrame],
    tickers: Optional[List[str]] = None,
    run_id: str = "",
) -> str:
    """
    Multi-panel price trend line + volume bar chart.
    One row per ticker (up to 4 tickers).
    """
    tickers = tickers or list(cleaned.keys())[:4]
    n = len(tickers)
    if n == 0:
        logger.warning("No tickers to plot in chart_price_volume.")
        return ""

    fig = plt.figure(figsize=(FIG_WIDE[0], 5 * n))
    fig.suptitle("Price Trend & Volume", fontsize=16, fontweight="bold", y=1.01)

    for i, ticker in enumerate(tickers):
        df = cleaned.get(ticker)
        if df is None or "Close" not in df.columns:
            continue

        color = COLORS[i % len(COLORS)]

        # ── Price panel ──
        ax_price = fig.add_subplot(n, 2, 2 * i + 1)
        ax_price.plot(df.index, df["Close"], color=color, linewidth=1.5, label="Close")

        # Moving averages overlay
        for w, ls in zip(MA_WINDOWS, ["--", ":"]):
            col = f"MA_{w}"
            if col in df.columns:
                ax_price.plot(df.index, df[col], linestyle=ls, linewidth=1.0,
                              label=f"MA {w}d", alpha=0.8)

        ax_price.set_title(f"{ticker} — Close Price", fontsize=12, fontweight="bold")
        ax_price.set_ylabel("Price (USD)")
        ax_price.legend(loc="upper left", fontsize=8)
        ax_price.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        ax_price.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax_price.xaxis.get_majorticklabels(), rotation=30, ha="right")

        # ── Volume panel ──
        ax_vol = fig.add_subplot(n, 2, 2 * i + 2)
        if "Volume" in df.columns:
            ax_vol.bar(df.index, df["Volume"] / 1e6, color=color, alpha=0.6, width=1)
            ax_vol.set_ylabel("Volume (M)")
        ax_vol.set_title(f"{ticker} — Volume", fontsize=12, fontweight="bold")
        ax_vol.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        ax_vol.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax_vol.xaxis.get_majorticklabels(), rotation=30, ha="right")

    fig.tight_layout()
    return _save(fig, "chart1_price_volume.png", run_id)


# ─── Chart 2: Correlation Heatmap ─────────────────────────────────────────────

def chart_correlation_heatmap(returns_matrix: pd.DataFrame, run_id: str = "") -> str:
    """
    Pearson correlation heatmap of daily returns across all assets.
    """
    if returns_matrix.empty:
        logger.warning("Returns matrix is empty — skipping heatmap.")
        return ""

    corr = returns_matrix.corr()

    fig, ax = plt.subplots(figsize=FIG_SQUARE)
    fig.suptitle("Daily Return Correlation Heatmap", fontsize=15, fontweight="bold")

    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)   # hide upper triangle

    sns.heatmap(
        corr,
        ax=ax,
        mask=~mask & (corr != corr),   # show all cells
        annot=True,
        fmt=".2f",
        cmap="RdYlGn",
        vmin=-1, vmax=1,
        linewidths=0.5,
        linecolor="#0f3460",
        cbar_kws={"shrink": 0.8, "label": "Pearson r"},
        annot_kws={"size": 11, "weight": "bold"},
    )

    ax.set_title("Assets: " + "  |  ".join(corr.columns.tolist()),
                 fontsize=9, pad=10)
    ax.tick_params(axis="x", rotation=30)
    ax.tick_params(axis="y", rotation=0)

    fig.tight_layout()
    return _save(fig, "chart2_correlation_heatmap.png", run_id)


# ─── Chart 3: Return Distribution ─────────────────────────────────────────────

def chart_return_distribution(
    cleaned: Dict[str, pd.DataFrame],
    tickers: Optional[List[str]] = None,
    run_id: str = "",
) -> str:
    """
    Histogram + KDE of daily returns for each asset on the same axes.
    Individual subplots with summary statistics annotated.
    """
    tickers = tickers or list(cleaned.keys())
    valid = [t for t in tickers if t in cleaned and "Daily_Return" in cleaned[t].columns]
    if not valid:
        logger.warning("No valid tickers for return distribution plot.")
        return ""

    n = len(valid)
    cols = min(n, 2)
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(FIG_WIDE[0], 4 * rows))
    fig.suptitle("Distribution of Daily Returns", fontsize=15, fontweight="bold")

    axes_flat = np.array(axes).flatten() if n > 1 else [axes]

    for i, ticker in enumerate(valid):
        ax = axes_flat[i]
        returns = cleaned[ticker]["Daily_Return"].dropna()
        color = COLORS[i % len(COLORS)]

        # Histogram
        ax.hist(returns, bins=60, color=color, alpha=0.45, density=True,
                label="Histogram")

        # KDE overlay
        from scipy.stats import gaussian_kde
        kde = gaussian_kde(returns)
        x_range = np.linspace(returns.min(), returns.max(), 300)
        ax.plot(x_range, kde(x_range), color=color, linewidth=2, label="KDE")

        # Vertical lines: mean & ± 1σ
        mu, sigma = returns.mean(), returns.std()
        ax.axvline(mu, color="white", linestyle="--", linewidth=1.2, label=f"μ={mu:.4f}")
        ax.axvline(mu + sigma, color="yellow", linestyle=":", linewidth=1, alpha=0.7)
        ax.axvline(mu - sigma, color="yellow", linestyle=":", linewidth=1, alpha=0.7,
                   label=f"±1σ={sigma:.4f}")
        ax.axvline(0, color="red", linestyle="-", linewidth=0.8, alpha=0.5)

        # Annotation box
        stats_text = (
            f"μ  = {mu*100:+.3f}%\n"
            f"σ  = {sigma*100:.3f}%\n"
            f"Skew = {returns.skew():.2f}\n"
            f"Kurt = {returns.kurtosis():.2f}"
        )
        ax.text(0.97, 0.97, stats_text, transform=ax.transAxes,
                fontsize=8, verticalalignment="top", horizontalalignment="right",
                bbox=dict(boxstyle="round,pad=0.4", facecolor="#0f3460", alpha=0.8))

        ax.set_title(f"{ticker} Daily Returns", fontsize=11, fontweight="bold")
        ax.set_xlabel("Daily Return")
        ax.set_ylabel("Density")
        ax.legend(fontsize=8)

    # Hide any unused subplots
    for j in range(i + 1, len(axes_flat)):
        axes_flat[j].set_visible(False)

    fig.tight_layout()
    return _save(fig, "chart3_return_distribution.png", run_id)


# ─── Chart 4: Rolling Statistics + Bollinger Bands ───────────────────────────

def chart_rolling_stats(
    cleaned: Dict[str, pd.DataFrame],
    tickers: Optional[List[str]] = None,
    run_id: str = "",
) -> str:
    """
    Close price with 7-day MA, 30-day MA, and Bollinger Bands (±2σ).
    One subplot per ticker.
    """
    tickers = tickers or list(cleaned.keys())[:4]
    valid = [t for t in tickers if t in cleaned and "BB_Upper" in cleaned[t].columns]
    if not valid:
        logger.warning("No valid tickers for rolling statistics chart.")
        return ""

    n = len(valid)
    fig, axes = plt.subplots(n, 1, figsize=(FIG_WIDE[0], 4 * n), sharex=False)
    if n == 1:
        axes = [axes]
    fig.suptitle("Rolling Statistics & Bollinger Bands", fontsize=15, fontweight="bold")

    for i, ticker in enumerate(valid):
        ax = axes[i]
        df = cleaned[ticker]
        color = COLORS[i % len(COLORS)]

        # Close price
        ax.plot(df.index, df["Close"], color=color, linewidth=1.5, label="Close", zorder=3)

        # Moving averages
        if "MA_7" in df.columns:
            ax.plot(df.index, df["MA_7"], color="#FFC107", linewidth=1.0,
                    linestyle="--", label="MA 7d", alpha=0.85)
        if "MA_30" in df.columns:
            ax.plot(df.index, df["MA_30"], color="#E91E63", linewidth=1.0,
                    linestyle="-.", label="MA 30d", alpha=0.85)

        # Bollinger Bands — shaded band
        if all(c in df.columns for c in ["BB_Upper", "BB_Lower", "BB_Middle"]):
            ax.plot(df.index, df["BB_Upper"], color="#76FF03", linewidth=0.8,
                    linestyle=":", label="BB Upper", alpha=0.7)
            ax.plot(df.index, df["BB_Lower"], color="#76FF03", linewidth=0.8,
                    linestyle=":", label="BB Lower", alpha=0.7)
            ax.fill_between(df.index, df["BB_Lower"], df["BB_Upper"],
                            alpha=0.07, color="#76FF03")

        # Annotate current price
        last_price = df["Close"].iloc[-1]
        ax.annotate(
            f"  ${last_price:.2f}",
            xy=(df.index[-1], last_price),
            fontsize=9, color="white",
            xytext=(5, 0), textcoords="offset points",
        )

        ax.set_title(f"{ticker} — Rolling Statistics", fontsize=11, fontweight="bold")
        ax.set_ylabel("Price (USD)")
        ax.legend(loc="upper left", fontsize=8, ncol=3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")

    fig.tight_layout()
    return _save(fig, "chart4_rolling_stats.png", run_id)


# ─── Bonus: Cumulative Return Comparison ─────────────────────────────────────

def chart_cumulative_returns(
    cleaned: Dict[str, pd.DataFrame],
    tickers: Optional[List[str]] = None,
    run_id: str = "",
) -> str:
    """
    Bonus chart: Normalised cumulative returns for all assets on one axis.
    Allows direct buy-and-hold performance comparison.
    """
    tickers = tickers or list(cleaned.keys())
    fig, ax = plt.subplots(figsize=FIG_WIDE)
    fig.suptitle("Cumulative Returns — Buy & Hold Comparison",
                 fontsize=15, fontweight="bold")

    plotted = 0
    for i, ticker in enumerate(tickers):
        df = cleaned.get(ticker)
        if df is None or "Cumulative_Return" not in df.columns:
            continue
        ax.plot(df.index, df["Cumulative_Return"] * 100,
                label=ticker, color=COLORS[i % len(COLORS)], linewidth=1.8)
        plotted += 1

    if plotted == 0:
        plt.close(fig)
        return ""

    ax.axhline(0, color="white", linewidth=0.7, linestyle="--", alpha=0.5)
    ax.set_ylabel("Cumulative Return (%)")
    ax.set_xlabel("Date")
    ax.legend(fontsize=10)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.1f}%"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")

    fig.tight_layout()
    return _save(fig, "chart5_cumulative_returns.png", run_id)
