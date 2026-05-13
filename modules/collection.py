"""
modules/collection.py — Data Collection Module
===============================================
Collects financial data from three source types:
  1. Stock prices (OHLCV)     — via yfinance (Yahoo Finance)
  2. Macro indicators          — via yfinance (commodities & forex)
  3. News headlines            — via yfinance built-in news feed
  4. Company fundamentals      — via yfinance Ticker.info

No API keys are required for this module.
"""

import logging
import os
import time
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)
def with_retry(max_attempts: int = 3, backoff_base: float = 2.0, exceptions=(Exception,)):
    """Decorator: retries fn up to max_attempts with exponential backoff."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    wait = backoff_base ** attempt
                    logger.warning(
                        f"{fn.__name__} failed (attempt {attempt+1}/{max_attempts}): {e}. "
                        f"Retrying in {wait:.1f}s..."
                    )
                    if attempt == max_attempts - 1:
                        logger.error(f"{fn.__name__} permanently failed after {max_attempts} attempts.")
                        raise
                    time.sleep(wait)
        return wrapper
    return decorator
# Keys to extract from yfinance Ticker.info
_COMPANY_KEYS = [
    "longName", "sector", "industry", "country", "city", "state",
    "fullTimeEmployees", "longBusinessSummary", "website",
    "marketCap", "trailingPE", "forwardPE", "priceToBook",
    "dividendYield", "beta", "recommendationKey",
    "numberOfAnalystOpinions", "targetMeanPrice",
]


def _strip_timezone(df: pd.DataFrame) -> pd.DataFrame:
    """Remove timezone info from a DatetimeIndex so all frames align cleanly."""
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    return df


# ─── Stock Prices ─────────────────────────────────────────────────────────────
@with_retry(max_attempts=3, backoff_base=2.0)
def fetch_stock_data(
    tickers: List[str],
    period: str = "1y",
    interval: str = "1d",
    save_dir: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Fetch historical OHLCV data for a list of tickers from Yahoo Finance.

    Parameters
    ----------
    tickers   : Ticker symbols, e.g. ["AAPL", "MSFT"]
    period    : yfinance period string — "1y", "6mo", "3mo", etc.
    interval  : Bar size — "1d", "1wk", "1mo"
    save_dir  : If provided, saves each ticker's raw CSV here.

    Returns
    -------
    Dict mapping ticker → OHLCV DataFrame (index: datetime).
    """
    results: Dict[str, pd.DataFrame] = {}

    for ticker in tickers:
        try:
            logger.info("Collecting stock data: %s", ticker)
            df = yf.Ticker(ticker).history(
                period=period, interval=interval, auto_adjust=True
            )
            if df.empty:
                logger.warning("  ✗ %s returned no data — skipping.", ticker)
                continue
            time.sleep(0.5) #Rate-limit courtesy to Yahoo Finance
            df = _strip_timezone(df)
            keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            df = df[keep]

            results[ticker] = df
            logger.info(
                "  ✓ %s: %d rows  [%s → %s]",
                ticker, len(df), df.index[0].date(), df.index[-1].date(),
            )

            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
                df.to_csv(os.path.join(save_dir, f"{ticker}_raw.csv"))

            time.sleep(0.35)

        except Exception as exc:
            logger.error("  ✗ Failed to fetch %s: %s", ticker, exc)

    return results


# ─── Macro Indicators ────────────────────────────────────────────────────────

def fetch_macro_data(
    symbols: Dict[str, str],
    period: str = "1y",
    save_dir: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Fetch macro indicator closing prices from Yahoo Finance.

    Parameters
    ----------
    symbols  : Mapping of label → Yahoo Finance symbol,
               e.g. {"Gold": "GC=F", "Oil_WTI": "CL=F", "USD_EUR": "EURUSD=X"}
    period   : yfinance period string.
    save_dir : Optional directory to persist raw CSVs.

    Returns
    -------
    Dict mapping label → single-column DataFrame (column = label, index: datetime).
    """
    results: Dict[str, pd.DataFrame] = {}

    for label, symbol in symbols.items():
        try:
            logger.info("Collecting macro data: %s (%s)", label, symbol)
            df = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)

            if df.empty:
                logger.warning("  ✗ %s returned no data — skipping.", label)
                continue

            df = _strip_timezone(df)
            df = df[["Close"]].rename(columns={"Close": label})
            results[label] = df
            logger.info("  ✓ %s: %d rows", label, len(df))

            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
                safe = label.replace("/", "_").replace(" ", "_")
                df.to_csv(os.path.join(save_dir, f"{safe}_raw.csv"))

            time.sleep(0.35)

        except Exception as exc:
            logger.error("  ✗ Failed to fetch macro %s: %s", label, exc)

    return results


# ─── News Headlines ───────────────────────────────────────────────────────────

def fetch_news(
    tickers: List[str],
    max_per_ticker: int = 5,
) -> Dict[str, List[dict]]:
    """
    Fetch recent news headlines for each ticker via yfinance.

    Returns
    -------
    Dict mapping ticker → list of raw news dicts from yfinance.
    """
    results: Dict[str, List[dict]] = {}

    for ticker in tickers:
        try:
            logger.info("Collecting news: %s", ticker)
            raw = yf.Ticker(ticker).news or []
            results[ticker] = raw[:max_per_ticker]
            logger.info("  ✓ %s: %d headlines", ticker, len(results[ticker]))
            time.sleep(0.35)
        except Exception as exc:
            logger.error("  ✗ Failed to fetch news for %s: %s", ticker, exc)
            results[ticker] = []

    return results


# ─── Company Fundamentals ────────────────────────────────────────────────────

def fetch_company_info(tickers: List[str]) -> Dict[str, dict]:
    """
    Fetch fundamental company information for each ticker via yfinance.

    Returns
    -------
    Dict mapping ticker → info dict (keys defined in _COMPANY_KEYS).
    """
    results: Dict[str, dict] = {}

    for ticker in tickers:
        try:
            logger.info("Collecting company info: %s", ticker)
            raw  = yf.Ticker(ticker).info or {}
            info = {k: raw.get(k) for k in _COMPANY_KEYS}

            # Truncate long business summary for token efficiency
            summary = info.get("longBusinessSummary") or ""
            if len(summary) > 400:
                info["longBusinessSummary"] = summary[:400] + "…"

            results[ticker] = info
            logger.info(
                "  ✓ %s: %s / %s",
                ticker, info.get("sector", "N/A"), info.get("industry", "N/A"),
            )
            time.sleep(0.35)

        except Exception as exc:
            logger.error("  ✗ Failed to fetch info for %s: %s", ticker, exc)
            results[ticker] = {}

    return results

