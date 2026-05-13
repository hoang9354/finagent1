"""
modules/demo_data.py — Synthetic Demo Data Generator
=====================================================
Generates realistic synthetic financial data using geometric Brownian motion.
Used when running in --demo mode (no internet connection required).

The simulated assets have distinct statistical personalities so the charts
and analysis look meaningful, not random.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List


# Asset "personalities" — (annual_return, annual_vol, start_price)
ASSET_PARAMS = {
    "AAPL":  {"mu": 0.28,  "sigma": 0.26, "S0": 158.0},
    "MSFT":  {"mu": 0.22,  "sigma": 0.22, "S0": 375.0},
    "NVDA":  {"mu": 0.55,  "sigma": 0.52, "S0": 480.0},
    "GOOGL": {"mu": 0.18,  "sigma": 0.24, "S0": 140.0},
}

MACRO_PARAMS = {
    "Gold":    {"mu": 0.08, "sigma": 0.14, "S0": 2020.0},
    "Oil_WTI": {"mu": 0.03, "sigma": 0.30, "S0": 78.0},
    "USD_EUR": {"mu": -0.02,"sigma": 0.07, "S0": 0.92},
}


def _trading_dates(days: int = 252) -> pd.DatetimeIndex:
    """Return the last `days` weekdays ending today."""
    end = datetime.today().date()
    all_days = pd.bdate_range(end=end, periods=days)
    return all_days


def _gbm_path(
    S0: float,
    mu: float,
    sigma: float,
    n: int,
    seed: int = 42,
) -> np.ndarray:
    """
    Simulate a Geometric Brownian Motion price path.

    Parameters
    ----------
    S0    : Initial price
    mu    : Annual drift
    sigma : Annual volatility
    n     : Number of trading days
    seed  : Random seed for reproducibility

    Returns
    -------
    1-D array of length n containing the simulated closing prices.
    """
    rng = np.random.default_rng(seed)
    dt = 1 / 252
    daily_returns = np.exp(
        (mu - 0.5 * sigma ** 2) * dt
        + sigma * np.sqrt(dt) * rng.standard_normal(n)
    )
    prices = S0 * np.cumprod(daily_returns)
    return prices


def _ohlcv_from_close(close: np.ndarray, sigma: float, rng) -> pd.DataFrame:
    """Derive plausible OHLCV columns from a close-price series."""
    n = len(close)
    daily_range = sigma / np.sqrt(252) * close  # ≈ 1-sigma daily price range

    high  = close + rng.uniform(0.0, 1.0, n) * daily_range
    low   = close - rng.uniform(0.0, 1.0, n) * daily_range
    open_ = close * np.exp(rng.normal(0, sigma / np.sqrt(252) * 0.3, n))
    volume = np.abs(rng.normal(loc=50e6, scale=20e6, size=n)).astype(int)

    # Enforce high >= close >= low
    high   = np.maximum(high, close)
    low    = np.minimum(low, close)
    open_  = np.clip(open_, low, high)

    return high, low, open_, volume


def generate_stock_data(
    tickers: List[str] = None,
    n_days: int = 252,
) -> Dict[str, pd.DataFrame]:
    """
    Generate realistic synthetic OHLCV DataFrames.

    Parameters
    ----------
    tickers : Subset of ASSET_PARAMS keys to generate. Defaults to all.
    n_days  : Number of trading days to simulate.

    Returns
    -------
    Dict[ticker → DataFrame] matching the format returned by collection.py
    """
    tickers = tickers or list(ASSET_PARAMS.keys())
    dates = _trading_dates(n_days)
    n     = len(dates)          # actual trading days (may differ from n_days)
    data: Dict[str, pd.DataFrame] = {}

    for i, ticker in enumerate(tickers):
        params = ASSET_PARAMS.get(ticker, {"mu": 0.15, "sigma": 0.25, "S0": 100.0})
        close  = _gbm_path(params["S0"], params["mu"], params["sigma"], n, seed=i * 7)
        rng    = np.random.default_rng(i * 13)
        high, low, open_, volume = _ohlcv_from_close(close, params["sigma"], rng)

        df = pd.DataFrame(
            {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
            index=dates,
        )
        data[ticker] = df

    return data


def generate_macro_data(n_days: int = 252) -> Dict[str, pd.DataFrame]:
    """
    Generate synthetic macro indicator (single Close column) DataFrames.

    Returns
    -------
    Dict[label → single-column DataFrame] matching collection.py format.
    """
    dates = _trading_dates(n_days)
    n     = len(dates)
    data: Dict[str, pd.DataFrame] = {}

    for i, (label, params) in enumerate(MACRO_PARAMS.items()):
        close = _gbm_path(params["S0"], params["mu"], params["sigma"], n, seed=100 + i)
        df    = pd.DataFrame({label: close}, index=dates)
        data[label] = df

    return data


def generate_news_data(tickers: List[str] = None) -> Dict[str, List[dict]]:
    """
    Generate plausible placeholder news headlines for demo mode.

    Returns
    -------
    Dict[ticker → list of news dicts]
    """
    tickers = tickers or list(ASSET_PARAMS.keys())
    sample_headlines = {
        "AAPL":  [
            {"title": "Apple reports record iPhone sales in Q1", "publisher": "Reuters"},
            {"title": "Apple Vision Pro demand exceeds initial projections", "publisher": "Bloomberg"},
            {"title": "Apple expands AI features in iOS update", "publisher": "TechCrunch"},
        ],
        "MSFT":  [
            {"title": "Microsoft Azure revenue surges on AI demand", "publisher": "CNBC"},
            {"title": "Copilot integration drives enterprise adoption", "publisher": "WSJ"},
            {"title": "Microsoft raises quarterly dividend by 10%", "publisher": "MarketWatch"},
        ],
        "NVDA":  [
            {"title": "Nvidia H100 GPU demand outpaces supply globally", "publisher": "Reuters"},
            {"title": "Nvidia data centre revenue hits new record", "publisher": "Bloomberg"},
            {"title": "Analysts raise Nvidia price targets after earnings beat", "publisher": "Barron's"},
        ],
        "GOOGL": [
            {"title": "Alphabet ad revenue rebounds in Q4", "publisher": "CNBC"},
            {"title": "Google Cloud gains market share in enterprise AI", "publisher": "TechCrunch"},
            {"title": "YouTube Shorts monetisation accelerates", "publisher": "WSJ"},
        ],
    }
    return {t: sample_headlines.get(t, []) for t in tickers}


def generate_company_info(tickers: List[str] = None) -> Dict[str, dict]:
    """
    Generate realistic company info dicts for demo mode.
    Mirrors the structure returned by yfinance Ticker.info.
    """
    tickers = tickers or list(ASSET_PARAMS.keys())

    DEMO_INFO = {
        "AAPL": {
            "longName": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "country": "United States",
            "city": "Cupertino",
            "fullTimeEmployees": 161000,
            "longBusinessSummary": (
                "Apple Inc. designs, manufactures, and markets smartphones, personal computers, "
                "tablets, wearables, and accessories worldwide. Its flagship products include the "
                "iPhone, Mac, iPad, Apple Watch, and AirPods. The company also operates a growing "
                "services segment covering the App Store, Apple Music, iCloud, and Apple TV+."
            ),
            "marketCap": 3_050_000_000_000,
            "trailingPE": 32.4,
            "forwardPE": 28.9,
            "priceToBook": 48.2,
            "dividendYield": 0.0051,
            "beta": 1.24,
            "recommendationKey": "buy",
            "numberOfAnalystOpinions": 38,
            "targetMeanPrice": 225.50,
            "website": "https://www.apple.com",
        },
        "MSFT": {
            "longName": "Microsoft Corporation",
            "sector": "Technology",
            "industry": "Software—Infrastructure",
            "country": "United States",
            "city": "Redmond",
            "fullTimeEmployees": 221000,
            "longBusinessSummary": (
                "Microsoft Corporation develops, licenses, and supports software, services, devices, "
                "and solutions worldwide. Its segments include Productivity and Business Processes "
                "(Office, LinkedIn, Dynamics), Intelligent Cloud (Azure, SQL Server), and More "
                "Personal Computing (Windows, Xbox, Surface, Bing). Azure is the company's fastest-"
                "growing division driven by enterprise AI adoption."
            ),
            "marketCap": 2_870_000_000_000,
            "trailingPE": 35.1,
            "forwardPE": 30.2,
            "priceToBook": 13.8,
            "dividendYield": 0.0072,
            "beta": 0.90,
            "recommendationKey": "buy",
            "numberOfAnalystOpinions": 42,
            "targetMeanPrice": 510.00,
            "website": "https://www.microsoft.com",
        },
        "NVDA": {
            "longName": "NVIDIA Corporation",
            "sector": "Technology",
            "industry": "Semiconductors",
            "country": "United States",
            "city": "Santa Clara",
            "fullTimeEmployees": 29600,
            "longBusinessSummary": (
                "NVIDIA Corporation provides graphics, compute and networking solutions. Its GPU "
                "platforms power gaming, professional visualisation, data centre AI workloads, and "
                "autonomous vehicles. The H100 and upcoming Blackwell chips dominate the AI training "
                "accelerator market. Data centre revenue has surpassed gaming as the primary revenue "
                "driver, growing triple-digits year-over-year."
            ),
            "marketCap": 2_320_000_000_000,
            "trailingPE": 68.5,
            "forwardPE": 37.2,
            "priceToBook": 42.6,
            "dividendYield": 0.0003,
            "beta": 1.73,
            "recommendationKey": "strongBuy",
            "numberOfAnalystOpinions": 51,
            "targetMeanPrice": 1050.00,
            "website": "https://www.nvidia.com",
        },
        "GOOGL": {
            "longName": "Alphabet Inc.",
            "sector": "Communication Services",
            "industry": "Internet Content & Information",
            "country": "United States",
            "city": "Mountain View",
            "fullTimeEmployees": 182000,
            "longBusinessSummary": (
                "Alphabet Inc. is the parent company of Google and several subsidiaries. Google "
                "Services (Search, YouTube, Maps, Gmail, Chrome, Android) generates the majority of "
                "revenue through advertising. Google Cloud is the third-largest cloud provider "
                "globally. Other Bets include Waymo (autonomous vehicles) and Verily (life sciences). "
                "The company has integrated generative AI across its product suite via Gemini."
            ),
            "marketCap": 1_780_000_000_000,
            "trailingPE": 22.8,
            "forwardPE": 19.4,
            "priceToBook": 6.7,
            "dividendYield": None,
            "beta": 1.05,
            "recommendationKey": "buy",
            "numberOfAnalystOpinions": 47,
            "targetMeanPrice": 215.00,
            "website": "https://www.alphabet.com",
        },
    }

    return {t: DEMO_INFO.get(t, {}) for t in tickers}
