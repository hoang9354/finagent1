"""
modules/ai_analysis.py — AI Analysis Module (Groq)
===================================================
Builds a structured financial data context and calls the Groq API
(llama-3.3-70b-versatile) to generate a seven-section investment report.
Saves output as both Markdown and a formatted Word document.

Get a free Groq API key at: https://console.groq.com  (no credit card needed)
Add to .env:  GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config import AI_MAX_TOKENS, GROQ_API_KEY, GROQ_MODEL, REPORTS_DIR
from modules.report_docx import save_report_as_docx
from modules.report_pptx import save_report_as_pptx

logger = logging.getLogger(__name__)


# ─── News field extractors ────────────────────────────────────────────────────
# yfinance news structure changes across library versions; these helpers
# gracefully handle plain strings, nested dicts, and missing keys.

def _extract_title(article: dict) -> str:
    for key in ("title", "content", "headline", "text", "body"):
        raw = article.get(key)
        if not raw:
            continue
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, dict):
            for nested in ("title", "text", "body", "summary", "headline"):
                val = raw.get(nested)
                if isinstance(val, str) and val.strip():
                    return val.strip()
    return ""


def _extract_summary(article: dict) -> str:
    for key in ("summary", "description", "snippet", "abstract"):
        raw = article.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, dict):
            for nested in ("summary", "text", "body"):
                val = raw.get(nested)
                if isinstance(val, str) and val.strip():
                    return val.strip()
    content = article.get("content")
    if isinstance(content, dict):
        for nested in ("summary", "description", "body"):
            val = content.get(nested)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ""


def _extract_publisher(article: dict) -> str:
    raw = article.get("publisher") or article.get("source") or ""
    if isinstance(raw, dict):
        return raw.get("name", "") or raw.get("title", "")
    return str(raw)


# ─── Context builder ──────────────────────────────────────────────────────────

def _build_context(
    cleaned: Dict[str, pd.DataFrame],
    macro_data: Dict[str, pd.DataFrame],
    news_data: Dict[str, List[dict]],
    returns_matrix: Optional[pd.DataFrame],
    company_info: Optional[Dict[str, dict]] = None,
) -> str:
    lines = []
    company_info = company_info or {}

    # ── Section 1: Company Profiles ───────────────────────────────────────
    lines.append("=" * 80)
    lines.append("SECTION 1 — COMPANY PROFILES")
    lines.append("=" * 80)

    for ticker in cleaned:
        info = company_info.get(ticker, {})
        if not info:
            lines.append(f"\n[{ticker}]  (no company info available)")
            continue

        name       = info.get("longName") or ticker
        sector     = info.get("sector")   or "N/A"
        industry   = info.get("industry") or "N/A"
        country    = info.get("country")  or "N/A"
        city       = info.get("city")     or ""
        emp        = info.get("fullTimeEmployees")
        mcap       = info.get("marketCap")
        pe_trail   = info.get("trailingPE")
        pe_fwd     = info.get("forwardPE")
        pb         = info.get("priceToBook")
        div        = info.get("dividendYield")
        beta       = info.get("beta")
        rec        = (info.get("recommendationKey") or "N/A").upper()
        n_analysts = info.get("numberOfAnalystOpinions") or "N/A"
        target     = info.get("targetMeanPrice")
        summary    = info.get("longBusinessSummary") or "No description available."

        lines.append(f"\n[{ticker}] {name}")
        lines.append(f"  Sector / Industry : {sector} / {industry}")
        lines.append(f"  HQ                : {city}, {country}")
        lines.append(f"  Employees         : {f'{emp:,}' if emp else 'N/A'}")
        lines.append(f"  Website           : {info.get('website') or 'N/A'}")
        lines.append(f"  Market Cap        : {'$'+f'{mcap/1e9:.1f}B' if mcap else 'N/A'}")
        lines.append(f"  Trailing P/E      : {f'{pe_trail:.1f}' if pe_trail else 'N/A'}")
        lines.append(f"  Forward P/E       : {f'{pe_fwd:.1f}'   if pe_fwd   else 'N/A'}")
        lines.append(f"  Price / Book      : {f'{pb:.2f}'        if pb       else 'N/A'}")
        lines.append(f"  Dividend Yield    : {f'{div*100:.2f}%'  if div      else 'None'}")
        lines.append(f"  Beta              : {f'{beta:.2f}'      if beta     else 'N/A'}")
        lines.append(f"  Analyst Rating    : {rec}  ({n_analysts} analysts, target={'$'+f'{target:.2f}' if target else 'N/A'})")
        lines.append(f"  Business Summary  : {summary}")

    # ── Section 2: Price & Return Statistics ──────────────────────────────
    lines.append("\n" + "=" * 80)
    lines.append("SECTION 2 — ASSET PRICE & RETURN STATISTICS (past 12 months)")
    lines.append("=" * 80)
    lines.append(
        f"{'Ticker':<8} {'Price':>8} {'52wH':>8} {'52wL':>8} "
        f"{'PeriodRet%':>11} {'AnnVol%':>9} {'CumRet%':>9} "
        f"{'Vol30d%':>9} {'Outliers':>9}"
    )
    lines.append("-" * 80)

    for ticker, df in cleaned.items():
        close    = df["Close"].dropna()
        ret      = df["Daily_Return"].dropna()
        p_ret    = ((close.iloc[-1] / close.iloc[0]) - 1) * 100
        ann_vol  = ret.std() * (252 ** 0.5) * 100
        cum_ret  = (df["Cumulative_Return"].iloc[-1] * 100) if "Cumulative_Return" in df.columns else 0.0
        vol30    = (df["Volatility_30"].iloc[-1] * 100)     if "Volatility_30"    in df.columns else 0.0
        outliers = int(df.get("Daily_Return_Outlier", pd.Series(False)).sum())
        ma30     = df["MA_30"].iloc[-1] if "MA_30" in df.columns else None
        ma7      = df["MA_7"].iloc[-1]  if "MA_7"  in df.columns else None
        trend    = ""
        if ma30 is not None and not pd.isna(ma30):
            trend = "ABOVE_MA30 (bullish)" if close.iloc[-5:].mean() > ma30 else "BELOW_MA30 (bearish)"

        lines.append(
            f"{ticker:<8} {close.iloc[-1]:>8.2f} {close.max():>8.2f} {close.min():>8.2f} "
            f"{p_ret:>+11.2f} {ann_vol:>9.2f} {cum_ret:>+9.2f} {vol30:>9.2f} {outliers:>9d}"
        )
        ma7_s  = f"{ma7:.2f}"  if ma7  is not None and not pd.isna(ma7)  else "N/A"
        ma30_s = f"{ma30:.2f}" if ma30 is not None and not pd.isna(ma30) else "N/A"
        lines.append(
            f"  ↳ {trend} | MA7={ma7_s}  MA30={ma30_s} "
            f"| Best day: {ret.max()*100:+.2f}%  Worst day: {ret.min()*100:+.2f}%"
        )

    # ── Section 3: Return Distribution ────────────────────────────────────
    lines.append("\n" + "=" * 80)
    lines.append("SECTION 3 — RETURN DISTRIBUTION & RISK-ADJUSTED METRICS")
    lines.append("=" * 80)
    lines.append(f"{'Ticker':<8} {'Mean%/d':>9} {'Std%/d':>9} {'Skew':>8} {'Kurt':>8} {'Sharpe':>9}")
    lines.append("-" * 55)

    for ticker, df in cleaned.items():
        ret    = df["Daily_Return"].dropna()
        sharpe = (ret.mean() / ret.std() * np.sqrt(252)) if ret.std() > 0 else 0
        lines.append(
            f"{ticker:<8} {ret.mean()*100:>+9.4f} {ret.std()*100:>9.4f} "
            f"{ret.skew():>8.3f} {ret.kurtosis():>8.3f} {sharpe:>9.3f}"
        )

    # ── Section 4: Correlations ────────────────────────────────────────────
    if returns_matrix is not None and not returns_matrix.empty:
        lines.append("\n" + "=" * 80)
        lines.append("SECTION 4 — PAIRWISE RETURN CORRELATIONS")
        lines.append("=" * 80)
        corr   = returns_matrix.corr().round(3)
        tlist  = list(corr.columns)
        labels = {
             0.7: "strong positive",  0.4: "moderate positive",
             0.1: "weak positive",   -0.1: "near zero",
            -0.4: "weak negative",
        }
        for i, t1 in enumerate(tlist):
            for t2 in tlist[i + 1:]:
                val   = corr.loc[t1, t2]
                label = "strong negative"
                for threshold, desc in labels.items():
                    if val > threshold:
                        label = desc
                        break
                lines.append(f"  {t1} / {t2} : r = {val:+.3f}  → {label}")

    # ── Section 5: Macro Indicators ───────────────────────────────────────
    if macro_data:
        lines.append("\n" + "=" * 80)
        lines.append("SECTION 5 — MACRO & COMMODITY INDICATORS")
        lines.append("=" * 80)
        for label, df in macro_data.items():
            if df.empty:
                continue
            s = df.iloc[:, 0].dropna()
            if len(s) < 2:
                continue
            chg   = ((float(s.iloc[-1]) / float(s.iloc[0])) - 1) * 100
            vol_a = s.pct_change().std() * np.sqrt(252) * 100
            lines.append(
                f"  {label:<12}  latest={s.iloc[-1]:.3f}  "
                f"period_chg={chg:+.2f}%  "
                f"range=[{s.min():.3f}–{s.max():.3f}]  ann_vol={vol_a:.1f}%"
            )

    # ── Section 6: News Headlines ──────────────────────────────────────────
    lines.append("\n" + "=" * 80)
    lines.append("SECTION 6 — RECENT NEWS HEADLINES & SUMMARIES")
    lines.append("=" * 80)

    any_news = False
    for ticker, articles in news_data.items():
        entries = []
        for art in articles[:5]:
            title     = _extract_title(art)
            summary   = _extract_summary(art)
            publisher = _extract_publisher(art)
            if not title:
                continue
            line = f"    • {title[:130]}"
            if publisher:
                line += f"  [{publisher}]"
            if summary:
                line += f"\n      ↳ {summary[:200]}"
            entries.append(line)
        if entries:
            any_news = True
            lines.append(f"\n  [{ticker}] — {len(entries)} recent articles:")
            lines.extend(entries)

    if not any_news:
        lines.append("  (No recent news available for any ticker)")

    return "\n".join(lines)


# ─── Groq API call ────────────────────────────────────────────────────────────

def _call_groq(context: str) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set.\n"
            "  1. Sign up free at https://console.groq.com\n"
            "  2. Create an API key (no credit card needed)\n"
            "  3. Add to .env:  GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx"
        )

    try:
        from groq import Groq
    except ImportError:
        raise RuntimeError("Run: pip install groq")

    client = Groq(api_key=GROQ_API_KEY)

    system_msg = (
        "You are a senior equity research analyst at a top-tier investment bank, "
        "authoring a formal investment research report for institutional fund managers. "
        "Your writing style is that of a Bloomberg Intelligence or Goldman Sachs research note: "
        "authoritative, analytical, and rich with specific data. "
        "\n\n"
        "CRITICAL FORMATTING RULES — you MUST follow these precisely:\n"
        "1. Write every analysis section as flowing, well-developed PARAGRAPHS — "
        "   minimum 3–5 sentences per company per section. "
        "   DO NOT use bullet points, dashes, or lists of any kind anywhere in the report body.\n"
        "2. Cite exact numbers, percentages, ratios, and dates from the data provided. "
        "   Every claim must be anchored to a specific figure.\n"
        "3. Use Markdown headings only for section and sub-section titles (## and ###). "
        "   All body content must be prose paragraphs.\n"
        "4. Each section must be substantive — aim for at least 150–200 words per section, "
        "   and at least 80–120 words per company within a section.\n"
        "5. Express clear analytical opinions and forward-looking judgements, "
        "   not just neutral summaries of the data.\n"
        "6. Use transitional phrases between companies and sections to maintain narrative flow."
    )

    user_msg = f"""You have received structured financial data for a multi-asset equity portfolio below.
Write a comprehensive, institutional-grade investment analysis report with exactly seven sections as specified.
All body text MUST be written as continuous prose paragraphs — absolutely no bullet points or lists.

{context}

---

## 1. Company Overview

For each of the four companies, write a detailed prose paragraph (minimum 100 words each) that covers
the core business model and primary revenue segments, the company's competitive positioning within its
industry (whether it is a market dominant, a fast-growing challenger, or a specialised niche player),
and any notable strategic developments signalled by the recent news headlines. Integrate the news context
naturally into your description of each company's current strategic posture. Transition smoothly between
companies using phrases such as "Turning to...", "In contrast,", or "Similarly,...".

## 2. Trend & Price Analysis

For each asset, write a detailed analytical paragraph (minimum 100 words each) examining the current
closing price relative to its 52-week high and low — express the percentage distance from each extreme.
Discuss the period return and cumulative return in the context of peer ranking — which asset has
outperformed and which has lagged, and by how much. Analyse the MA7 versus MA30 relationship and
articulate what this crossover or gap signals about near-term momentum and trend direction. Reference
the best and worst single-day moves and explain what those extreme sessions reveal about event-driven
price risk for each company.

## 3. Return Distribution & Risk-Adjusted Performance

For each asset, write a substantive paragraph (minimum 100 words each) analysing the distribution of
daily returns. Discuss the mean daily return and express its compounded annualised implication.
Explain the skewness figure — does the return distribution lean toward positive surprises or negative
tail events, and what does this mean for investor expectations? Discuss kurtosis: is there evidence of
fat-tail risk, indicating the potential for extreme daily moves beyond what a normal distribution would
predict? Conclude each company's paragraph with a clear statement of its Sharpe ratio and what that
ratio implies about the efficiency of its risk-adjusted return relative to peers.

## 4. Risk Commentary

Write a cohesive multi-paragraph risk analysis (minimum 250 words total) that first ranks all four
assets from highest to lowest annualised volatility and provides quantitative context for each ranking.
Then compare the 30-day rolling volatility against the full-period annualised volatility for each
asset — is near-term risk expanding or contracting relative to the historical norm, and what does this
suggest about the current market environment for each stock? Dedicate a separate paragraph to the macro
environment: analyse the trend, period change, and annualised volatility of Gold, WTI Oil, and the
USD/EUR exchange rate, and discuss the implications of each for the equity holdings. Conclude with a
paragraph on the portfolio-level correlation structure — which pairs move in lockstep and which offer
genuine diversification, and what this means for a multi-asset investor managing concentration risk.

## 5. News Sentiment & Narrative Analysis

For each company that has news coverage, write a detailed analytical paragraph (minimum 100 words each)
that first characterises the overall sentiment as Bullish, Bearish, or Mixed, and provides clear
reasoning grounded in the specific headlines. Identify the single most market-moving headline and
explain the likely directional price impact and magnitude. Discuss the forward-looking catalysts or
risks that emerge from the news narrative — what events or developments should investors monitor?
Conclude each company's paragraph by explicitly noting whether the news narrative is consistent with or
contradicts the quantitative price and return data — and explain the significance of any such divergence.

## 6. Cross-Asset Comparison

Write a structured comparative analysis in prose (minimum 250 words total) that systematically compares
all four assets across multiple dimensions. Begin with a Sharpe ratio ranking paragraph — rank all
assets from most to least efficient on a risk-adjusted basis and explain the gaps between them in
analytical terms. Follow with a diversification paragraph examining which pairs exhibit the strongest
and weakest correlations, and articulate what this means practically for a two- or three-stock
portfolio. Then write a valuation comparison paragraph covering the trailing P/E, forward P/E, and
Price-to-Book ratios of all four companies — identify which is the most expensive and which offers
relative value, and explain the premium or discount in terms of growth expectations. Conclude with an
analyst consensus paragraph comparing each company's current price against the mean analyst price
target and discussing what the analyst community's recommendation implies about upside or downside.

## 7. Investment Perspective & Key Metrics to Watch

Write a final, forward-looking section (minimum 250 words) structured as four cohesive paragraphs.
The first paragraph should make the case for the single most attractive asset among the four — argue
why its combination of growth, valuation, momentum, and risk profile makes it the most compelling
investment at current prices, citing at least three specific quantitative reasons. The second paragraph
should identify and explain the single most risky asset — discuss what makes it particularly vulnerable,
whether that is elevated volatility, stretched valuation, negative price momentum, or macro sensitivity,
again with at least three specific data points. The third paragraph should identify, for each of the
four assets, one specific metric or upcoming event that investors must monitor most closely in the
near term, and explain why that particular indicator is the most critical risk or opportunity signal
for that company. The fourth and final paragraph should deliver an overall portfolio recommendation:
if a diversified investor could hold only two of the four assets, which pair would you select and why,
addressing both risk-adjusted return and diversification benefit in your reasoning.

Write with conviction. This report will be presented to a panel of institutional investors and graded
on analytical depth, quantitative precision, and clarity of argument.
"""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=8000,
        temperature=0.35,
    )
    return response.choices[0].message.content


# ─── Public API ───────────────────────────────────────────────────────────────

def run_ai_analysis(
    cleaned: Dict[str, pd.DataFrame],
    macro_data: Dict[str, pd.DataFrame],
    news_data: Dict[str, List[dict]],
    returns_matrix: Optional[pd.DataFrame] = None,
    company_info: Optional[Dict[str, dict]] = None,
    run_id: str = "",
    charts_dir: str = "",
) -> dict:
    """
    Build context, call Groq, save Markdown + Word report + PowerPoint deck.

    Returns
    -------
    Dict with keys "md", "docx", and "pptx" pointing to the saved files,
    or an empty dict on failure.
    """
    logger.info("Building data context for Groq analysis…")
    context    = _build_context(cleaned, macro_data, news_data, returns_matrix, company_info)
    word_count = len(context.split())
    logger.info("  Context: ~%d words (~%d tokens)", word_count, int(word_count * 1.3))

    logger.info("Calling Groq (%s) for financial analysis…", GROQ_MODEL)
    try:
        analysis_text = _call_groq(context)
    except Exception as exc:
        logger.error("AI analysis failed: %s", exc)
        return {}

    # ── Save Markdown ──────────────────────────────────────────────────────
    out_dir = os.path.join(REPORTS_DIR, run_id) if run_id else REPORTS_DIR
    os.makedirs(out_dir, exist_ok=True)
    ts      = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = os.path.join(out_dir, f"ai_analysis_{ts}.md")
    header      = (
        f"# FinAgent Investment Analysis Report\n\n"
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
        f"**Provider:** Groq — {GROQ_MODEL}  \n"
        f"**Assets:** {', '.join(cleaned.keys())}  \n\n---\n\n"
    )
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(header + analysis_text)
    logger.info("Markdown report saved → %s", md_path)

    # ── Save Word Document ─────────────────────────────────────────────────
    docx_path = ""
    try:
        docx_path = save_report_as_docx(
            analysis_text=analysis_text,
            tickers=list(cleaned.keys()),
            cleaned=cleaned,
            company_info=company_info,
            output_dir=out_dir,
            charts_dir=charts_dir or "",
        )
        logger.info("Word report saved → %s", docx_path)
    except Exception as exc:
        logger.error("DOCX generation failed: %s", exc)

    # ── Save PowerPoint Deck ───────────────────────────────────────────────
    pptx_path = ""
    try:
        pptx_path = save_report_as_pptx(
            analysis_text=analysis_text,
            tickers=list(cleaned.keys()),
            cleaned=cleaned,
            company_info=company_info,
            output_dir=out_dir,
            charts_dir=charts_dir or "",
            run_id=ts,
        )
        logger.info("PowerPoint deck saved → %s", pptx_path)
    except Exception as exc:
        logger.error("PPTX generation failed: %s", exc)

    return {"md": md_path, "docx": docx_path, "pptx": pptx_path}
