"""
modules/report_pptx.py — PowerPoint Slide Deck Generator
=========================================================
Converts the AI analysis Markdown report + chart PNGs into a polished
16:9 investor presentation (.pptx).

Requires Node.js + pptxgenjs:
    npm install -g pptxgenjs

Usage (called automatically by ai_analysis.py when run_pptx=True):
    from modules.report_pptx import save_report_as_pptx

    pptx_path = save_report_as_pptx(
        analysis_text = md_text,
        tickers       = ["AAPL", "MSFT", "NVDA", "GOOGL"],
        cleaned       = cleaned_dict,
        company_info  = company_info_dict,
        output_dir    = "outputs/reports/20260502_143012",
        charts_dir    = "outputs/charts/20260502_143012",
    )

Or run standalone:
    python -m modules.report_pptx \
        --md    outputs/reports/.../ai_analysis_....md \
        --out   outputs/reports/.../FinAgent_Slides.pptx \
        --charts outputs/charts/.../
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Path to the JS generator script (same directory as this file)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_JS_SCRIPT   = os.path.join(_SCRIPT_DIR, "generate_pptx.js")


# ─── Section extractor ────────────────────────────────────────────────────────

# Maps section keys → patterns to match in the Markdown headings
_SECTION_PATTERNS = {
    "company_overview": r"company\s+overview",
    "trend_analysis":   r"trend\s*[&+]\s*price|price\s*[&+]\s*trend",
    "risk_adjusted":    r"return\s+distribution|risk.adjusted",
    "risk_commentary":  r"risk\s+commentary",
    "news_sentiment":   r"news\s+sentiment",
    "cross_asset":      r"cross.asset",
    "investment_view":  r"investment\s+perspective|investment\s+view",
}


def _extract_sections(md: str) -> Dict[str, str]:
    """
    Split the Markdown analysis text into named sections.
    Each section runs from its heading to the next ## heading.
    """
    # Split on ## or # headings
    parts = re.split(r"\n(?=#{1,3} )", md)
    sections: Dict[str, str] = {}

    for part in parts:
        heading_m = re.match(r"^#{1,3} (.+)", part)
        if not heading_m:
            continue
        heading = heading_m.group(1).strip().lower()
        body    = re.sub(r"^#{1,3} .+\n?", "", part, count=1).strip()

        for key, pattern in _SECTION_PATTERNS.items():
            if re.search(pattern, heading, re.IGNORECASE):
                sections[key] = body
                break

    return sections


# ─── Stats extractor ──────────────────────────────────────────────────────────

def _build_stats(
    cleaned: Dict[str, pd.DataFrame],
    company_info: Optional[Dict[str, dict]] = None,
) -> Dict[str, dict]:
    """
    Build a per-ticker stats dict that the JS generator can consume directly.
    All values are plain Python floats/ints/strings — JSON-serialisable.
    """
    company_info = company_info or {}
    result: Dict[str, dict] = {}

    for ticker, df in cleaned.items():
        close    = df["Close"].dropna()
        ret_col  = df["Daily_Return"].dropna()

        period_ret = float((close.iloc[-1] / close.iloc[0]) - 1) if len(close) > 1 else 0.0
        ann_vol    = float(ret_col.std() * (252 ** 0.5)) if len(ret_col) > 1 else 0.0
        sharpe     = float(ret_col.mean() / ret_col.std() * (252 ** 0.5)) if ret_col.std() > 0 else 0.0
        cum_ret    = float(df["Cumulative_Return"].iloc[-1]) if "Cumulative_Return" in df.columns else 0.0
        vol30      = float(df["Volatility_30"].iloc[-1])     if "Volatility_30"    in df.columns else ann_vol
        outliers   = int(df.get("Daily_Return_Outlier", pd.Series(False)).sum())
        skew       = float(ret_col.skew())
        kurt       = float(ret_col.kurtosis())

        info = company_info.get(ticker, {})

        # Serialise info — drop non-JSON-safe values
        safe_info: dict = {}
        for k, v in info.items():
            if v is None:
                safe_info[k] = None
            elif isinstance(v, (int, float)):
                safe_info[k] = float(v) if not (np.isnan(v) if isinstance(v, float) else False) else None
            elif isinstance(v, str):
                safe_info[k] = v
            # Skip other types

        result[ticker] = {
            "price":        float(close.iloc[-1]),
            "high_52w":     float(close.max()),
            "low_52w":      float(close.min()),
            "period_return":period_ret,
            "ann_vol":      ann_vol,
            "vol_30d":      vol30,
            "cum_return":   cum_ret,
            "sharpe":       sharpe,
            "skew":         skew,
            "kurtosis":     kurt,
            "best_day":     float(ret_col.max()),
            "worst_day":    float(ret_col.min()),
            "outliers":     outliers,
            "info":         safe_info,
        }

    return result


# ─── Chart path resolver ──────────────────────────────────────────────────────

_CHART_FILENAMES = {
    "price_volume":  "chart1_price_volume.png",
    "correlation":   "chart2_correlation_heatmap.png",
    "distribution":  "chart3_return_distribution.png",
    "rolling":       "chart4_rolling_stats.png",
    "cumulative":    "chart5_cumulative_returns.png",
}


def _resolve_charts(charts_dir: str) -> Dict[str, str]:
    """Return a dict of chart_key → absolute path (only existing files)."""
    resolved: Dict[str, str] = {}
    if not charts_dir:
        return resolved
    for key, filename in _CHART_FILENAMES.items():
        full = os.path.join(charts_dir, filename)
        if os.path.isfile(full):
            resolved[key] = os.path.abspath(full)
    return resolved


# ─── JS runner ────────────────────────────────────────────────────────────────

def _run_js(data: dict, out_path: str) -> None:
    """
    Write `data` to a temp JSON file, then invoke the Node.js generator.
    Raises RuntimeError if node is unavailable or the script fails.
    """
    if not os.path.isfile(_JS_SCRIPT):
        raise FileNotFoundError(
            f"JS generator not found at: {_JS_SCRIPT}\n"
            "Make sure generate_pptx.js is in the same folder as report_pptx.py"
        )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tf:
        json.dump(data, tf, ensure_ascii=False, indent=2)
        tmp_path = tf.name

    try:
        result = subprocess.run(
            ["node", _JS_SCRIPT, tmp_path, out_path],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Node.js generator failed (exit {result.returncode}):\n"
                f"{result.stderr or result.stdout}"
            )
        # Log node stdout (e.g. "✓ Saved: …")
        for line in (result.stdout or "").splitlines():
            logger.info("  [pptx] %s", line)
    finally:
        os.unlink(tmp_path)


# ─── Public API ───────────────────────────────────────────────────────────────

def save_report_as_pptx(
    analysis_text: str,
    tickers: List[str],
    cleaned: Dict[str, pd.DataFrame],
    company_info: Optional[Dict[str, dict]] = None,
    output_dir: str = "outputs/reports",
    charts_dir: Optional[str] = None,
    run_id: str = "",
) -> str:
    """
    Build and save a formatted PowerPoint presentation.

    Parameters
    ----------
    analysis_text : Markdown text from Groq (output of ai_analysis.py).
    tickers       : List of ticker symbols in display order.
    cleaned       : Dict of cleaned DataFrames (for statistics).
    company_info  : Optional company profile dicts from yfinance.
    output_dir    : Directory where the .pptx will be saved.
    charts_dir    : Path to the run's chart folder (PNG images).
    run_id        : Timestamp string used in the filename.

    Returns
    -------
    Full path to the saved .pptx file, or "" on failure.
    """
    os.makedirs(output_dir, exist_ok=True)
    ts       = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(output_dir, f"FinAgent_Slides_{ts}.pptx")
    generated = datetime.now().strftime("%Y-%m-%d  %H:%M")

    logger.info("Building PPTX payload…")

    sections = _extract_sections(analysis_text)
    logger.info("  Extracted %d analysis sections", len(sections))

    stats = _build_stats(cleaned, company_info)
    logger.info("  Built stats for: %s", ", ".join(stats.keys()))

    charts = _resolve_charts(charts_dir or "")
    logger.info("  Resolved %d chart images", len(charts))

    payload = {
        "tickers":   tickers,
        "generated": generated,
        "stats":     stats,
        "sections":  sections,
        "charts":    charts,
    }

    logger.info("Invoking Node.js PPTX generator…")
    try:
        _run_js(payload, out_path)
    except Exception as exc:
        logger.error("PPTX generation failed: %s", exc)
        return ""

    logger.info("PPTX report saved → %s", out_path)
    return out_path


# ─── Standalone CLI ───────────────────────────────────────────────────────────

def _cli():
    """
    CLI entry point for standalone use:
        python -m modules.report_pptx --md <file.md> [--out <file.pptx>] [--charts <dir>]
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert a FinAgent Markdown report to a PowerPoint presentation."
    )
    parser.add_argument("--md",     required=True,  help="Path to the ai_analysis_*.md file")
    parser.add_argument("--out",    default="",      help="Output .pptx path (auto-named if omitted)")
    parser.add_argument("--charts", default="",      help="Path to the charts directory")
    args = parser.parse_args()

    if not os.path.isfile(args.md):
        print(f"Error: Markdown file not found: {args.md}", file=sys.stderr)
        sys.exit(1)

    with open(args.md, encoding="utf-8") as f:
        analysis_text = f.read()

    out_dir  = os.path.dirname(args.md) or "."
    out_path = args.out or os.path.join(
        out_dir,
        "FinAgent_Slides_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".pptx",
    )

    # ── Extract tickers from the Markdown header ──────────────────────────
    tickers_m = re.search(r"\*\*Assets:\*\*\s*([A-Z, ]+)", analysis_text)
    tickers   = [t.strip() for t in tickers_m.group(1).split(",")] if tickers_m else []

    # CLI mode: no cleaned DataFrames available — pass empty dicts
    logger.info("CLI mode: no cleaned DataFrames — stats table will be empty.")

    sections = _extract_sections(analysis_text)
    charts   = _resolve_charts(args.charts)
    generated = datetime.now().strftime("%Y-%m-%d  %H:%M")

    payload = {
        "tickers":   tickers,
        "generated": generated,
        "stats":     {},
        "sections":  sections,
        "charts":    charts,
    }

    print(f"Generating slides → {out_path}")
    _run_js(payload, out_path)
    print("Done.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
    _cli()
