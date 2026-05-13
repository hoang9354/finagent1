"""
modules/collection.py — Data Collection Module
===============================================
Collects financial data from Yahoo Finance via the yfinance library.

Data collected:
  1. Stock OHLCV prices      — yfinance Ticker.history()
  2. Macro indicators         — yfinance Ticker.history() for commodities/forex
  3. News headlines           — yfinance Ticker.news
  4. Company fundamentals     — yfinance Ticker.info

Reliability features:
  - Exponential backoff retry on all network calls (max 3 attempts)
  - Per-ticker rate-limit delay (0.5s between requests)
  - DataFrame validation after every fetch
  - Graceful skip on failure — pipeline never crashes from a single bad ticker

No API keys required for any function in this module.
"""

import functools
import logging
import os
import time
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ─── Retry Decorator ─────────────────────────────────────────────────────────

def with_retry(max_attempts: int = 3, backoff_base: float = 2.0):
    """
    Decorator that retries a function up to max_attempts times
    with exponential backoff between each attempt.

    Backoff schedule (backoff_base=2.0):
      Attempt 1 fails → wait 1s  (2^0)
      Attempt 2 fails → wait 2s  (2^1)
      Attempt 3 fails → give up, log error, return None

    Why return None instead of raising?
      Raising would crash the entire pipeline for one bad ticker.
      Returning None lets the caller skip gracefully and continue.

    Args:
        max_attempts: Total number of tries before giving up (default: 3).
        backoff_base: Base for exponential wait time (default: 2.0).

    Returns:
        Decorated function with retry logic built in.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)          # ← attempt the call

                except Exception as e:                  # ← FIXED: plain Exception, no variable
                    last_exc = e
                    wait = backoff_base ** (attempt - 1)  # 1s, 2s, 4s

                    if attempt < max_attempts:
                        logger.warning(
                            "[%s] Attempt %d/%d failed: %s — retrying in %.0fs…",
                            fn.__name__, attempt, max_attempts, e, wait,
                        )
                        time.sleep(wait)
                    else:
                        logger.error(
                            "[%s] All %d attempts failed. Last error: %s",
                            fn.__name__, max_attempts, last_exc,
                        )

            return None     # ← FIXED: return None instead of re-raising — pipeline continues

        return wrapper
    return decorator


# ─── DataFrame Validator ──────────────────────────────────────────────────────

def _validate_dataframe(
    df: Optional[pd.DataFrame],
    label: str,
    min_rows: int = 30,
    required_col: str = "Close",
) -> bool:
    """
    Validate that a fetched DataFrame is safe to use downstream.

    Checks performed:
      - Not None (fetch returned nothing)
      - Not empty
      - Has minimum row count
      - Contains the required column

    Args:
        df:           DataFrame to validate (may be None).
        label:        Ticker or indicator name — used in log messages only.
        min_rows:     Minimum acceptable number of rows (default: 30).
        required_col: Column that must be present (default: "Close").

    Returns:
        True if valid, False if the data should be skipped.
    """
    if df is None:
        logger.warning("[%s] Fetch returned None — skipping.", label)
        return False
    if not isinstance(df, pd.DataFrame):
        logger.warning("[%s] Expected DataFrame, got %s — skipping.", label, type(df))
        return False
    if df.empty:
        logger.warning("[%s] DataFrame is empty — skipping.", label)
        return False
    if len(df) < min_rows:
        logger.warning(
            "[%s] Only %d rows returned (minimum: %d) — data may be incomplete.",
            label, len(df), min_rows,
        )
        # Note: we still return True here — partial data is better than nothing
        # The cleaning module will handle gaps via forward-fill
    if required_col not in df.columns:
        logger.warning("[%s] Required column '%s' missing — skipping.", label, required_col)
        return False

    logger.info(
        "[%s] Validated ✓  %d rows  [%s → %s]",
        label, len(df), df.index[0].date(), df.index[-1].date(),
    )
    return True


# ─── Timezone Helper ──────────────────────────────────────────────────────────

def _strip_timezone(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove timezone info from a DatetimeIndex.

    Why: yfinance returns timezone-aware indices (e.g. UTC or US/Eastern).
    Mixing timezone-aware and timezone-naive indices causes merge errors
    in the cleaning module. Stripping here keeps all frames consistent.

    Args:
        df: DataFrame with a DatetimeIndex (may or may not be tz-aware).

    Returns:
        DataFrame with tz-naive DatetimeIndex (original is not mutated).
    """
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    return df


# ─── Keys to extract from yfinance Ticker.info ───────────────────────────────

_COMPANY_KEYS = [
    "longName", "sector", "industry", "country", "city", "state",
    "fullTimeEmployees", "longBusinessSummary", "website",
    "marketCap", "trailingPE", "forwardPE", "priceToBook",
    "dividendYield", "beta", "recommendationKey",
    "numberOfAnalystOpinions", "targetMeanPrice",
]


# ─── 1. Stock Prices ──────────────────────────────────────────────────────────

@with_retry(max_attempts=3, backoff_base=2.0)      # ← retry on any network failure
def fetch_stock_data(
    tickers: List[str],
    period: str = "1y",
    interval: str = "1d",
    save_dir: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Fetch historical OHLCV price data for a list of stock tickers.

    Data source: Yahoo Finance via yfinance (no API key required).
    Prices are split- and dividend-adjusted (auto_adjust=True).

    Args:
        tickers:  List of ticker symbols, e.g. ["AAPL", "MSFT", "NVDA"].
        period:   Lookback window — "1y", "6mo", "3mo", "ytd", etc.
        interval: Bar frequency — "1d" (daily), "1wk", "1mo".
        save_dir: If provided, each ticker's raw OHLCV is saved as a CSV here.

    Returns:
        Dict mapping ticker symbol → OHLCV DataFrame with DatetimeIndex.
        Tickers that fail validation are excluded (not None — just absent).
    """
    results: Dict[str, pd.DataFrame] = {}

    for ticker in tickers:
        logger.info("Fetching stock: %s", ticker)
        try:
            df = yf.Ticker(ticker).history(
                period=period,
                interval=interval,
                auto_adjust=True,       # adjusts for splits and dividends
            )

            # ── Validate before accepting ─────────────────────────────────
            if not _validate_dataframe(df, ticker):
                continue                # skip invalid — don't crash

            df = _strip_timezone(df)

            # Keep only standard OHLCV columns (some tickers return extra cols)
            keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            df = df[keep]

            results[ticker] = df

            # ── Persist raw data ──────────────────────────────────────────
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
                path = os.path.join(save_dir, f"{ticker}_raw.csv")
                df.to_csv(path)
                logger.info("  Saved raw CSV → %s", path)

        except Exception as exc:
            # Catch anything the retry decorator didn't handle
            logger.error("  ✗ Unexpected error for %s: %s", ticker, exc)
            continue

        # ── Rate-limit courtesy delay ─────────────────────────────────────
        # 500ms between tickers prevents Yahoo Finance from throttling us.
        time.sleep(0.5)

    if not results:
        logger.error("fetch_stock_data: no tickers returned valid data.")

    return results


# ─── 2. Macro Indicators ──────────────────────────────────────────────────────

@with_retry(max_attempts=3, backoff_base=2.0)      # ← ADDED: was missing retry before
def fetch_macro_data(
    symbols: Dict[str, str],
    period: str = "1y",
    save_dir: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Fetch macro-economic indicator closing prices from Yahoo Finance.

    Fetches commodity and forex data that provides market context
    for the AI analysis (e.g. Gold, Oil, USD/EUR exchange rate).

    Args:
        symbols:  Dict mapping display label → Yahoo Finance symbol.
                  Example: {"Gold": "GC=F", "Oil_WTI": "CL=F"}
        period:   Lookback window (same as fetch_stock_data).
        save_dir: Optional directory to persist raw CSVs.

    Returns:
        Dict mapping label → single-column DataFrame (column named = label).
    """
    results: Dict[str, pd.DataFrame] = {}

    for label, symbol in symbols.items():
        logger.info("Fetching macro: %s (%s)", label, symbol)
        try:
            df = yf.Ticker(symbol).history(
                period=period, interval="1d", auto_adjust=True
            )

            # ── Validate ──────────────────────────────────────────────────
            if not _validate_dataframe(df, label):
                continue

            df = _strip_timezone(df)
            df = df[["Close"]].rename(columns={"Close": label})

            results[label] = df
            logger.info("  ✓ %s: %d rows collected", label, len(df))

            # ── Persist ───────────────────────────────────────────────────
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
                safe_name = label.replace("/", "_").replace(" ", "_")
                df.to_csv(os.path.join(save_dir, f"{safe_name}_raw.csv"))

        except Exception as exc:
            logger.error("  ✗ Failed to fetch macro %s: %s", label, exc)
            continue

        time.sleep(0.5)      # ← ADDED: rate-limit delay (was 0.35 before)

    return results


# ─── 3. News Headlines ────────────────────────────────────────────────────────

@with_retry(max_attempts=3, backoff_base=2.0)      # ← ADDED: was missing retry before
def fetch_news(
    tickers: List[str],
    max_per_ticker: int = 5,
) -> Dict[str, List[dict]]:
    """
    Fetch recent news headlines and summaries for each ticker via yfinance.

    Note on data quality: yfinance news provides titles and brief summaries
    only — not full article text. This is sufficient for AI sentiment context
    but not for detailed NLP analysis. For deeper news analysis, integrate
    NewsAPI (see modules/news_collection.py).

    Args:
        tickers:        List of ticker symbols.
        max_per_ticker: Maximum headlines to keep per ticker (default: 5).

    Returns:
        Dict mapping ticker → list of news dicts from yfinance.
        Each dict contains keys: title, publisher, link, providerPublishTime.
        Returns empty list for any ticker that fails — never raises.
    """
    results: Dict[str, List[dict]] = {}

    for ticker in tickers:
        logger.info("Fetching news: %s", ticker)
        try:
            raw = yf.Ticker(ticker).news or []
            headlines = raw[:max_per_ticker]
            results[ticker] = headlines
            logger.info("  ✓ %s: %d headlines", ticker, len(headlines))

        except Exception as exc:
            logger.error("  ✗ Failed to fetch news for %s: %s", ticker, exc)
            results[ticker] = []         # empty list, not None — safe for downstream

        time.sleep(0.5)      # ← ADDED: rate-limit delay (was 0.35 before)

    return results


# ─── 4. Company Fundamentals ──────────────────────────────────────────────────

@with_retry(max_attempts=3, backoff_base=2.0)      # ← ADDED: was missing retry before
def fetch_company_info(tickers: List[str]) -> Dict[str, dict]:
    """
    Fetch fundamental company data for each ticker via yfinance Ticker.info.

    Data collected per ticker:
      - Identity: name, sector, industry, country
      - Size: market cap, employee count
      - Valuation: trailing P/E, forward P/E, price-to-book
      - Income: dividend yield
      - Risk: beta (market sensitivity)
      - Analyst consensus: recommendation, analyst count, mean price target
      - Description: truncated business summary (max 400 chars for token efficiency)

    Args:
        tickers: List of ticker symbols.

    Returns:
        Dict mapping ticker → info dict. Missing keys default to None.
        Returns empty dict for failed tickers — never raises.
    """
    results: Dict[str, dict] = {}

    for ticker in tickers:
        logger.info("Fetching company info: %s", ticker)
        try:
            raw = yf.Ticker(ticker).info or {}
            info = {k: raw.get(k) for k in _COMPANY_KEYS}

            # Truncate long business summary — saves tokens in AI context
            summary = info.get("longBusinessSummary") or ""
            if len(summary) > 400:
                info["longBusinessSummary"] = summary[:400] + "…"

            results[ticker] = info
            logger.info(
                "  ✓ %s: %s / %s",
                ticker,
                info.get("sector", "N/A"),
                info.get("industry", "N/A"),
            )

        except Exception as exc:
            logger.error("  ✗ Failed to fetch info for %s: %s", ticker, exc)
            results[ticker] = {}        # empty dict, not None — safe for downstream

        time.sleep(0.5)      # ← ADDED: rate-limit delay (was 0.35 before)

    return results
