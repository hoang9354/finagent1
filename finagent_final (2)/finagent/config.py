"""
config.py — Central configuration for FinAgent.

All tunable settings live here. Sensitive keys are loaded from .env.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Assets ───────────────────────────────────────────────────────────────────
STOCK_TICKERS    = ["AAPL", "MSFT", "NVDA", "GOOGL"]   # Target stocks to analyse
BENCHMARK_TICKER = "^GSPC"                               # S&P 500 as benchmark
MACRO_SYMBOLS    = {                                     # Macro / commodity proxies
    "Gold":    "GC=F",
    "Oil_WTI": "CL=F",
    "USD_EUR": "EURUSD=X",
}
DATA_PERIOD   = "1y"   # Period fed to yfinance (1y = ~252 trading days)
DATA_INTERVAL = "1d"   # Daily granularity

# ─── API Keys ─────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ─── File Paths ───────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
RAW_DATA_DIR  = os.path.join(BASE_DIR, "data",    "raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "data",    "processed")
CHARTS_DIR    = os.path.join(BASE_DIR, "outputs", "charts")
REPORTS_DIR   = os.path.join(BASE_DIR, "outputs", "reports")
LOGS_DIR      = os.path.join(BASE_DIR, "logs")

# ─── Feature Engineering ──────────────────────────────────────────────────────
MA_WINDOWS       = [7, 30]   # Rolling mean windows (days)
BB_WINDOW        = 20        # Bollinger Band lookback
BB_STD_MULT      = 2.0       # Std-deviation multiplier for Bollinger Bands
OUTLIER_Z_THRESH = 3.0       # |z| > threshold → flagged as outlier

# ─── AI Module ────────────────────────────────────────────────────────────────
GROQ_MODEL    = "llama-3.3-70b-versatile"   # Groq free-tier model
AI_MAX_TOKENS = 3500                         # Max output tokens per call

# ─── Visualisation ────────────────────────────────────────────────────────────
CHART_DPI  = 150
FIG_WIDE   = (14, 8)
FIG_TALL   = (14, 10)
FIG_SQUARE = (10, 8)
COLORS     = ["#2196F3", "#F44336", "#4CAF50", "#FF9800", "#9C27B0"]
