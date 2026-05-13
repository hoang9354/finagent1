"""
modules/cleaning.py — Data Cleaning & Processing Module
========================================================
Handles the full cleaning pipeline for raw financial DataFrames:

  1. Duplicate detection & removal (with logging)
  2. Missing-value handling  (forward-fill → back-fill → drop)
  3. Data-type normalisation (dates, numerics)
  4. Outlier detection       (z-score flagging on daily returns)
  5. Feature engineering:
       • Daily return
       • 7-day & 30-day rolling mean (Close)
       • 30-day rolling volatility  (annualised)
       • Bollinger Bands            (20-day, ±2 σ)
       • Cumulative return
"""

import logging
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from config import (
    BB_STD_MULT,
    BB_WINDOW,
    MA_WINDOWS,
    OUTLIER_Z_THRESH,
)

logger = logging.getLogger(__name__)


# ─── Public API ───────────────────────────────────────────────────────────────

def clean_stock_data(
    raw_data: Dict[str, pd.DataFrame],
    save_dir: str = None,
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, dict]]:
    """
    Clean and enrich raw OHLCV DataFrames.

    Parameters
    ----------
    raw_data : Dict[ticker → raw DataFrame] from the collection module.
    save_dir : If provided, saves each processed CSV here.

    Returns
    -------
    cleaned  : Dict[ticker → enriched DataFrame]
    logs     : Dict[ticker → dict of cleaning actions performed]
    """
    cleaned: Dict[str, pd.DataFrame] = {}
    logs: Dict[str, dict] = {}

    for ticker, df in raw_data.items():
        logger.info("Cleaning: %s", ticker)

        df, ticker_log = _clean_single(df.copy(), ticker)

        if df.empty:
            logger.warning("  ✗ %s is empty after cleaning — skipping.", ticker)
            continue

        cleaned[ticker] = df
        logs[ticker] = ticker_log

        if save_dir:
            import os
            os.makedirs(save_dir, exist_ok=True)
            path = os.path.join(save_dir, f"{ticker}_clean.csv")
            df.to_csv(path)
            logger.info("  Saved cleaned → %s", path)

    return cleaned, logs


def build_returns_matrix(cleaned: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Combine the Daily_Return column of every ticker into one aligned DataFrame.

    Useful for correlation analysis and portfolio-level statistics.

    Returns
    -------
    DataFrame with shape (trading_days × n_assets), columns = ticker symbols.
    """
    frames = {
        ticker: df["Daily_Return"]
        for ticker, df in cleaned.items()
        if "Daily_Return" in df.columns
    }
    if not frames:
        return pd.DataFrame()

    combined = pd.DataFrame(frames).dropna(how="all")
    return combined


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _clean_single(df: pd.DataFrame, ticker: str) -> Tuple[pd.DataFrame, dict]:
    """Run the full cleaning & feature-engineering pipeline on one ticker."""
    action_log: dict = {}

    # ── 1. Ensure DatetimeIndex ────────────────────────────────────────────
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # ── 2. Normalise numeric columns ──────────────────────────────────────
    numeric_cols = df.select_dtypes(exclude="number").columns.tolist()
    for col in numeric_cols:
        try:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        except Exception:
            pass
    action_log["type_normalisation"] = f"Coerced {len(numeric_cols)} non-numeric columns"

    # ── 3. Remove duplicate index entries ─────────────────────────────────
    n_before = len(df)
    df = df[~df.index.duplicated(keep="last")]
    n_dupes = n_before - len(df)
    action_log["duplicates_removed"] = n_dupes
    if n_dupes:
        logger.info("  %s: removed %d duplicate rows", ticker, n_dupes)

    # ── 4. Handle missing values ──────────────────────────────────────────
    n_missing_before = df.isnull().sum().sum()

    # Forward-fill (carries last known price forward over weekends / holidays)
    df = df.ffill()
    # Back-fill for any leading NaNs
    df = df.bfill()
    # Drop rows that are still fully NaN (e.g., truly empty rows)
    df = df.dropna(how="all")

    n_missing_after = df.isnull().sum().sum()
    action_log["missing_filled"] = int(n_missing_before - n_missing_after)
    logger.info(
        "  %s: filled %d missing values",
        ticker,
        action_log["missing_filled"],
    )

    # ── 5. Feature Engineering ────────────────────────────────────────────
    df = _engineer_features(df, ticker, action_log)

    # ── 6. Outlier Detection on Daily Return ──────────────────────────────
    if "Daily_Return" in df.columns:
        df = _flag_outliers(df, "Daily_Return", ticker, action_log)

    logger.info("  %s: ✓ cleaned  (%d rows, %d cols)", ticker, len(df), len(df.columns))
    return df, action_log


def _engineer_features(df: pd.DataFrame, ticker: str, log: dict) -> pd.DataFrame:
    """Add derived features to the OHLCV DataFrame."""
    if "Close" not in df.columns:
        logger.warning("  %s: no 'Close' column — skipping feature engineering.", ticker)
        return df

    close = df["Close"]

    # Daily percentage return
    df["Daily_Return"] = close.pct_change()

    # Rolling means
    for window in MA_WINDOWS:
        col = f"MA_{window}"
        df[col] = close.rolling(window=window, min_periods=1).mean()

    # Bollinger Bands (based on BB_WINDOW-day close)
    bb_mean = close.rolling(window=BB_WINDOW, min_periods=1).mean()
    bb_std = close.rolling(window=BB_WINDOW, min_periods=1).std()
    df["BB_Middle"] = bb_mean
    df["BB_Upper"] = bb_mean + BB_STD_MULT * bb_std
    df["BB_Lower"] = bb_mean - BB_STD_MULT * bb_std

    # Annualised 30-day rolling volatility (std of daily returns × √252)
    df["Volatility_30"] = (
        df["Daily_Return"].rolling(window=30, min_periods=10).std() * np.sqrt(252)
    )

    # Cumulative return (base = 1.0 on day 0)
    df["Cumulative_Return"] = (1 + df["Daily_Return"].fillna(0)).cumprod() - 1

    log["features_added"] = [
        "Daily_Return",
        *[f"MA_{w}" for w in MA_WINDOWS],
        "BB_Middle", "BB_Upper", "BB_Lower",
        "Volatility_30",
        "Cumulative_Return",
    ]

    return df


def _flag_outliers(
    df: pd.DataFrame,
    col: str,
    ticker: str,
    log: dict,
) -> pd.DataFrame:
    """
    Flag rows where |z-score| of `col` exceeds OUTLIER_Z_THRESH.
    Creates a boolean column `{col}_Outlier`.
    Does NOT remove the rows — outliers are flagged for transparency.
    """
    series = df[col].dropna()
    if len(series) < 10:
        return df

    mean = series.mean()
    std = series.std()

    if std == 0:
        df[f"{col}_Outlier"] = False
        return df

    z_scores = (df[col] - mean) / std
    df[f"{col}_Outlier"] = z_scores.abs() > OUTLIER_Z_THRESH

    n_outliers = int(df[f"{col}_Outlier"].sum())
    log["outliers_flagged"] = n_outliers

    if n_outliers:
        logger.info(
            "  %s: flagged %d outliers in %s (|z| > %.1f)",
            ticker,
            n_outliers,
            col,
            OUTLIER_Z_THRESH,
        )

    return df
