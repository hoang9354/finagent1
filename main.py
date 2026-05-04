"""
main.py — FinAgent Pipeline Orchestrator
=========================================
Runs the full end-to-end financial data agent:

  Phase 1 → Data Collection  (stocks + macro + news + company profiles)
  Phase 2 → Data Cleaning    (missing values, outliers, feature engineering)
  Phase 3 → Visualisation    (4 required charts + 1 bonus)
  Phase 4 → AI Analysis      (Groq-powered report in Markdown + Word)

Usage
-----
  python main.py           # Live data from Yahoo Finance
  python main.py --demo    # Synthetic data (no internet required)

Requires:
  • An active internet connection  (skipped in --demo mode)
  • GROQ_API_KEY set in .env       (Phase 4 only — all other phases work without it)
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime

# ─── Logging setup (before importing project modules) ────────────────────────
os.makedirs("logs", exist_ok=True)
LOG_FILE = os.path.join("logs", f"finagent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ─── Project imports ──────────────────────────────────────────────────────────
import config as cfg
from modules.collection import (
    fetch_stock_data, fetch_macro_data, fetch_news, fetch_company_info,
)
from modules.demo_data import (
    generate_stock_data, generate_macro_data, generate_news_data, generate_company_info,
)
from modules.cleaning import clean_stock_data, build_returns_matrix
from modules.visualization import (
    chart_price_volume,
    chart_correlation_heatmap,
    chart_return_distribution,
    chart_rolling_stats,
    chart_cumulative_returns,
)
from modules.ai_analysis import run_ai_analysis


# ─── Directory bootstrap ──────────────────────────────────────────────────────

def _bootstrap_dirs() -> None:
    for d in [cfg.RAW_DATA_DIR, cfg.PROCESSED_DIR,
              cfg.CHARTS_DIR, cfg.REPORTS_DIR, cfg.LOGS_DIR]:
        os.makedirs(d, exist_ok=True)


# ─── Console helpers ──────────────────────────────────────────────────────────

DIVIDER = "─" * 65

def _banner(title: str) -> None:
    print(f"\n{DIVIDER}\n  {title}\n{DIVIDER}")

def _check(label: str) -> None:
    print(f"  ✓  {label}")

def _warn(label: str) -> None:
    print(f"  ⚠  {label}")


# ─── Phase 1 — Data Collection ───────────────────────────────────────────────

def phase_collect(demo: bool = False, run_id: str = ""):
    mode_tag = "  [DEMO MODE — synthetic data]" if demo else ""
    _banner(f"Phase 1 — Data Collection{mode_tag}")
    t0 = time.time()

    if demo:
        print("\n  Generating synthetic market data (Geometric Brownian Motion)…")
        stock_data   = generate_stock_data(tickers=cfg.STOCK_TICKERS)
        _check(f"{len(stock_data)} synthetic stock series generated")

        macro_data   = generate_macro_data()
        _check(f"{len(macro_data)} synthetic macro series generated")

        news_data    = generate_news_data(tickers=cfg.STOCK_TICKERS)
        _check(f"{sum(len(v) for v in news_data.values())} placeholder headlines loaded")

        company_info = generate_company_info(tickers=cfg.STOCK_TICKERS)
        _check(f"{len(company_info)} company profiles generated")

    else:
        print(f"\n  Stocks : {', '.join(cfg.STOCK_TICKERS)}")
        stock_data = fetch_stock_data(
            tickers=cfg.STOCK_TICKERS,
            period=cfg.DATA_PERIOD,
            interval=cfg.DATA_INTERVAL,
            save_dir=cfg.RAW_DATA_DIR,
        )
        _check(f"{len(stock_data)}/{len(cfg.STOCK_TICKERS)} stocks collected")

        print(f"\n  Macro  : {', '.join(cfg.MACRO_SYMBOLS.keys())}")
        macro_data = fetch_macro_data(
            symbols=cfg.MACRO_SYMBOLS,
            period=cfg.DATA_PERIOD,
            save_dir=cfg.RAW_DATA_DIR,
        )
        _check(f"{len(macro_data)}/{len(cfg.MACRO_SYMBOLS)} macro series collected")

        print("\n  News   : fetching recent headlines…")
        news_data = fetch_news(tickers=cfg.STOCK_TICKERS, max_per_ticker=5)
        _check(f"{sum(len(v) for v in news_data.values())} headlines across {len(news_data)} tickers")

        print("\n  Company info : fetching profiles…")
        company_info = fetch_company_info(tickers=cfg.STOCK_TICKERS)
        _check(f"{len(company_info)} company profiles fetched")

    print(f"\n  Collection complete in {time.time() - t0:.1f}s")
    return stock_data, macro_data, news_data, company_info


# ─── Phase 2 — Cleaning ──────────────────────────────────────────────────────

def phase_clean(stock_data: dict):
    _banner("Phase 2 — Data Cleaning & Feature Engineering")
    t0 = time.time()

    cleaned, logs = clean_stock_data(stock_data, save_dir=cfg.PROCESSED_DIR)

    for ticker, log in logs.items():
        _check(
            f"{ticker}: {log.get('duplicates_removed', 0)} dupes removed | "
            f"{log.get('missing_filled', 0)} NaNs filled | "
            f"{log.get('outliers_flagged', 0)} outliers flagged"
        )

    returns_matrix = build_returns_matrix(cleaned)
    _check(f"Returns matrix: {returns_matrix.shape[0]} rows × {returns_matrix.shape[1]} assets")

    print(f"\n  Cleaning complete in {time.time() - t0:.1f}s")
    return cleaned, returns_matrix


# ─── Phase 3 — Visualisation ─────────────────────────────────────────────────

def phase_visualise(cleaned: dict, returns_matrix, run_id: str = ""):
    _banner("Phase 3 — Visualisation")
    t0 = time.time()
    charts = {}

    for label, fn, key in [
        ("Chart 1 — Price Trend + Volume",             chart_price_volume,        "price_volume"),
        ("Chart 2 — Correlation Heatmap",              chart_correlation_heatmap, "correlation"),
        ("Chart 3 — Return Distribution",              chart_return_distribution, "distribution"),
        ("Chart 4 — Rolling Statistics & Bollinger",   chart_rolling_stats,       "rolling"),
        ("Bonus   — Cumulative Returns Comparison",    chart_cumulative_returns,  "cumulative"),
    ]:
        print(f"\n  {label}…")
        arg = returns_matrix if key == "correlation" else cleaned
        path = fn(arg, run_id=run_id)
        if path:
            charts[key] = path
            _check(f"Saved: {os.path.basename(path)}")

    print(f"\n  {len(charts)} charts generated in {time.time() - t0:.1f}s  →  {cfg.CHARTS_DIR}")
    return charts


# ─── Phase 4 — AI Analysis ───────────────────────────────────────────────────

def phase_ai_analysis(
    cleaned: dict,
    macro_data: dict,
    news_data: dict,
    returns_matrix,
    company_info: dict = None,
    run_id: str = "",
    charts_dir: str = "",
):
    _banner("Phase 4 — AI Analysis (Groq)")

    if not cfg.GROQ_API_KEY:
        _warn("GROQ_API_KEY not found in .env — skipping AI analysis.")
        _warn("Get a free key at https://console.groq.com then add it to .env")
        return None

    t0     = time.time()
    result = run_ai_analysis(
        cleaned=cleaned,
        macro_data=macro_data,
        news_data=news_data,
        returns_matrix=returns_matrix,
        company_info=company_info,
        run_id=run_id,
        charts_dir=charts_dir,
    )

    if result:
        elapsed = time.time() - t0
        _check(f"Markdown report → {os.path.basename(result.get('md',   ''))}")
        _check(f"Word report     → {os.path.basename(result.get('docx', ''))}  ({elapsed:.1f}s)")
    else:
        _warn("AI analysis returned no output.")

    return result


# ─── Pipeline Summary ─────────────────────────────────────────────────────────

def print_summary(cleaned: dict, charts: dict, result, total_elapsed: float, run_id: str = ""):
    _banner("Pipeline Summary")

    print(f"\n  Assets analysed : {', '.join(cleaned.keys())}")
    chart_dir = os.path.join(cfg.CHARTS_DIR, run_id) if run_id else cfg.CHARTS_DIR
    print(f"  Charts saved    : {len(charts)}  →  {chart_dir}")

    if result:
        print(f"  AI report (md)  : {result.get('md',   '(none)')}")
        print(f"  AI report (docx): {result.get('docx', '(none)')}")
    else:
        print("  AI report       : (not generated — see Phase 4 output)")

    print(f"  Log file        : {LOG_FILE}")
    print(f"\n  Total run time  : {total_elapsed:.1f}s")
    print(f"\n{DIVIDER}")
    print("  FinAgent run complete. Good luck with the submission! 🚀")
    print(DIVIDER)

    # Quick per-asset stats
    print("\n  ── Per-Asset Quick Stats ─────────────────────────────────\n")
    print(f"  {'Ticker':<8} {'Return':>10} {'Ann.Vol':>10} {'Price':>10} {'Trend'}")
    print(f"  {'─'*8} {'─'*10} {'─'*10} {'─'*10} {'─'*20}")
    for ticker, df in cleaned.items():
        try:
            close = df["Close"].dropna()
            ret   = ((close.iloc[-1] / close.iloc[0]) - 1) * 100
            vol   = df["Daily_Return"].dropna().std() * (252 ** 0.5) * 100
            trend = ""
            if "MA_30" in df.columns and len(df) >= 5:
                trend = "↑ Above MA30" if close.iloc[-5:].mean() > df["MA_30"].iloc[-1] else "↓ Below MA30"
            print(f"  {ticker:<8} {ret:>+9.2f}% {vol:>9.2f}%  ${close.iloc[-1]:>8.2f}  {trend}")
        except Exception:
            print(f"  {ticker:<8}  (stats unavailable)")
    print()


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FinAgent — AI-Powered Financial Data Agent")
    parser.add_argument(
        "--demo", action="store_true",
        help="Run with synthetic data (no internet required).",
    )
    args = parser.parse_args()

    t0     = time.time()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n{'═'*65}")
    print("  FinAgent — AI-Powered Financial Data Agent")
    if args.demo:
        print("  Mode: DEMO (synthetic data)")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*65}")

    _bootstrap_dirs()

    stock_data, macro_data, news_data, company_info = phase_collect(demo=args.demo, run_id=run_id)
    if not stock_data:
        logger.error("No stock data collected. Check your internet connection.")
        sys.exit(1)

    cleaned, returns_matrix = phase_clean(stock_data)
    if not cleaned:
        logger.error("Cleaning produced no usable data. Exiting.")
        sys.exit(1)

    charts = phase_visualise(cleaned, returns_matrix, run_id=run_id)
    charts_dir = os.path.join(cfg.CHARTS_DIR, run_id) if run_id else cfg.CHARTS_DIR
    result = phase_ai_analysis(cleaned, macro_data, news_data, returns_matrix, company_info, run_id=run_id, charts_dir=charts_dir)

    print_summary(cleaned, charts, result, time.time() - t0, run_id)


if __name__ == "__main__":
    main()
