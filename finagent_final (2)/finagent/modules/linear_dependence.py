"""
modules/linear_dependence.py — Linear Dependence Testing Module
================================================================
Tests for linear dependence in stock return time series using five
complementary approaches:

  Test 1 — Autocorrelation (Ljung-Box)
           Does each asset's own past returns predict its future returns?
           H₀: no autocorrelation (returns are serially independent)

  Test 2 — Durbin-Watson
           Detects first-order serial autocorrelation in residuals.
           DW ≈ 2 → no autocorrelation; DW < 2 → positive; DW > 2 → negative

  Test 3 — Pearson Cross-Correlation Matrix
           Linear co-movement between all pairs of assets.
           Includes statistical significance (p-values).

  Test 4 — Granger Causality
           Does the return history of asset A significantly improve the
           forecast of asset B's returns? Tests all directed pairs.
           H₀: asset A does NOT Granger-cause asset B

  Test 5 — Engle-Granger Cointegration
           Do any pairs of price series share a long-run linear equilibrium?
           H₀: no cointegration (price series are not linearly bound)

All results are returned as a structured dict and printed as a
formatted report to the console and log. A CSV summary is also saved.
"""

import logging
import os
from itertools import permutations, combinations
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

# Significance threshold
ALPHA = 0.05


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _significance(p: float) -> str:
    """Convert p-value to a readable significance label."""
    if p < 0.001:
        return "*** (p<0.001)"
    if p < 0.01:
        return "**  (p<0.01)"
    if p < 0.05:
        return "*   (p<0.05)"
    return "    (n.s.)"


def _verdict(reject: bool) -> str:
    return "REJECT H₀" if reject else "FAIL TO REJECT H₀"


def _aligned_returns(cleaned: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Build a single aligned DataFrame of daily returns for all tickers.
    Rows with any NaN are dropped so all tests use the same observations.
    """
    frames = {
        ticker: df["Daily_Return"]
        for ticker, df in cleaned.items()
        if "Daily_Return" in df.columns
    }
    return pd.DataFrame(frames).dropna()


# ─── Test 1: Ljung-Box Autocorrelation ───────────────────────────────────────

def test_autocorrelation(
    cleaned: Dict[str, pd.DataFrame],
    lags: int = 10,
) -> Dict[str, dict]:
    """
    Ljung-Box test for serial autocorrelation in each asset's daily returns.

    Parameters
    ----------
    cleaned : Dict of cleaned DataFrames.
    lags    : Number of lags to test.

    Returns
    -------
    Dict[ticker → {lb_stat, lb_pvalue, reject_h0, interpretation}]
    """
    try:
        from statsmodels.stats.diagnostic import acorr_ljungbox
    except ImportError:
        logger.error("statsmodels not installed. Run: pip install statsmodels")
        return {}

    results = {}
    logger.info("Test 1 — Ljung-Box Autocorrelation (lags=%d)", lags)

    for ticker, df in cleaned.items():
        ret = df["Daily_Return"].dropna()
        if len(ret) < lags + 5:
            logger.warning("  %s: insufficient data for Ljung-Box test.", ticker)
            continue

        lb = acorr_ljungbox(ret, lags=[lags], return_df=True)
        stat  = float(lb["lb_stat"].iloc[-1])
        pval  = float(lb["lb_pvalue"].iloc[-1])
        reject = pval < ALPHA

        results[ticker] = {
            "lb_statistic": round(stat, 4),
            "lb_pvalue":    round(pval, 6),
            "lags_tested":  lags,
            "reject_h0":    reject,
            "interpretation": (
                f"Significant autocorrelation detected at lag {lags} "
                f"({_significance(pval).strip()}) — returns are NOT serially independent."
                if reject else
                f"No significant autocorrelation at lag {lags} — returns appear serially independent."
            ),
        }
        logger.info(
            "  %s: LB=%.4f  p=%.6f  %s  → %s",
            ticker, stat, pval, _significance(pval), _verdict(reject),
        )

    return results


# ─── Test 2: Durbin-Watson ────────────────────────────────────────────────────

def test_durbin_watson(cleaned: Dict[str, pd.DataFrame]) -> Dict[str, dict]:
    """
    Durbin-Watson statistic for first-order serial autocorrelation.
    Computed on each asset's daily returns treated as residuals.

    DW ≈ 2.0  → no autocorrelation
    DW < 1.5  → positive autocorrelation
    DW > 2.5  → negative autocorrelation
    """
    try:
        from statsmodels.stats.stattools import durbin_watson
    except ImportError:
        logger.error("statsmodels not installed. Run: pip install statsmodels")
        return {}

    results = {}
    logger.info("Test 2 — Durbin-Watson First-Order Autocorrelation")

    for ticker, df in cleaned.items():
        ret = df["Daily_Return"].dropna().values
        if len(ret) < 10:
            continue

        dw = durbin_watson(ret)

        if dw < 1.5:
            direction    = "Positive autocorrelation"
            reject       = True
        elif dw > 2.5:
            direction    = "Negative autocorrelation"
            reject       = True
        else:
            direction    = "No significant autocorrelation"
            reject       = False

        results[ticker] = {
            "dw_statistic":   round(float(dw), 4),
            "reject_h0":      reject,
            "direction":      direction,
            "interpretation": (
                f"DW={dw:.4f} — {direction}. "
                + ("Returns show linear serial dependence." if reject
                   else "Returns are consistent with serial independence.")
            ),
        }
        logger.info("  %s: DW=%.4f  → %s", ticker, dw, direction)

    return results


# ─── Test 3: Cross-Correlation with Significance ─────────────────────────────

def test_cross_correlation(
    cleaned: Dict[str, pd.DataFrame],
) -> Dict[str, dict]:
    """
    Pearson correlation between all pairs of asset daily returns,
    with two-tailed t-test p-values.

    Returns
    -------
    Dict["{t1}/{t2}" → {correlation, t_stat, p_value, reject_h0, n_obs}]
    """
    returns = _aligned_returns(cleaned)
    if returns.empty or returns.shape[1] < 2:
        logger.warning("Insufficient assets for cross-correlation test.")
        return {}

    results = {}
    tickers = list(returns.columns)
    logger.info("Test 3 — Pearson Cross-Correlation with Significance")

    for t1, t2 in combinations(tickers, 2):
        x  = returns[t1].values
        y  = returns[t2].values
        n  = len(x)
        r, pval = stats.pearsonr(x, y)

        # t-statistic: t = r * sqrt(n-2) / sqrt(1-r²)
        t_stat = r * np.sqrt(n - 2) / np.sqrt(max(1 - r ** 2, 1e-10))
        reject = pval < ALPHA

        pair = f"{t1}/{t2}"
        results[pair] = {
            "correlation": round(r,    4),
            "t_statistic": round(t_stat, 4),
            "p_value":     round(pval,  6),
            "n_obs":       n,
            "reject_h0":   reject,
            "interpretation": (
                f"r={r:+.4f} {_significance(pval).strip()} — "
                + ("Significant linear co-movement detected." if reject
                   else "No significant linear relationship.")
            ),
        }
        logger.info(
            "  %s: r=%+.4f  t=%.4f  p=%.6f  %s  → %s",
            pair, r, t_stat, pval, _significance(pval), _verdict(reject),
        )

    return results


# ─── Test 4: Granger Causality ────────────────────────────────────────────────

def test_granger_causality(
    cleaned: Dict[str, pd.DataFrame],
    max_lag: int = 5,
) -> Dict[str, dict]:
    """
    Granger causality test for all directed pairs (A → B).
    Tests whether past returns of A improve the forecast of B's returns.

    H₀: A does NOT Granger-cause B  (past A adds no predictive power for B)

    Parameters
    ----------
    max_lag : Maximum number of lags to test (1 … max_lag).

    Returns
    -------
    Dict["{cause} → {effect}" → {min_p, best_lag, reject_h0, f_stat}]
    """
    try:
        import warnings
        from statsmodels.tsa.stattools import grangercausalitytests
    except ImportError:
        logger.error("statsmodels not installed. Run: pip install statsmodels")
        return {}

    returns = _aligned_returns(cleaned)
    if returns.empty or returns.shape[1] < 2:
        return {}

    results = {}
    tickers = list(returns.columns)
    logger.info("Test 4 — Granger Causality (max_lag=%d)", max_lag)

    for cause, effect in permutations(tickers, 2):
        pair_key = f"{cause} → {effect}"
        try:
            # grangercausalitytests expects [effect, cause] column order
            data = returns[[effect, cause]].dropna()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                gc = grangercausalitytests(data, maxlag=max_lag, verbose=False)

            # Collect the best (minimum) p-value across all lags (F-test)
            lag_results = {}
            for lag, res in gc.items():
                f_stat = res[0]["ssr_ftest"][0]
                p_val  = res[0]["ssr_ftest"][1]
                lag_results[lag] = {"f_stat": f_stat, "p_value": p_val}

            best_lag  = min(lag_results, key=lambda l: lag_results[l]["p_value"])
            best_p    = lag_results[best_lag]["p_value"]
            best_f    = lag_results[best_lag]["f_stat"]
            reject    = best_p < ALPHA

            results[pair_key] = {
                "best_lag":    best_lag,
                "f_statistic": round(best_f,  4),
                "p_value":     round(best_p,  6),
                "reject_h0":   reject,
                "all_lags":    {l: {"f_stat": round(v["f_stat"], 4),
                                    "p_value": round(v["p_value"], 6)}
                                for l, v in lag_results.items()},
                "interpretation": (
                    f"{cause} DOES Granger-cause {effect} at lag {best_lag} "
                    f"(F={best_f:.4f}, p={best_p:.6f} {_significance(best_p).strip()})."
                    if reject else
                    f"{cause} does NOT Granger-cause {effect} "
                    f"(best p={best_p:.6f} at lag {best_lag})."
                ),
            }
            logger.info(
                "  %s: F=%.4f  p=%.6f  best_lag=%d  %s  → %s",
                pair_key, best_f, best_p, best_lag,
                _significance(best_p), _verdict(reject),
            )

        except Exception as exc:
            logger.warning("  Granger test failed for %s: %s", pair_key, exc)

    return results


# ─── Test 5: Engle-Granger Cointegration ─────────────────────────────────────

def test_cointegration(
    cleaned: Dict[str, pd.DataFrame],
) -> Dict[str, dict]:
    """
    Engle-Granger cointegration test on price levels for all asset pairs.
    Tests whether two non-stationary price series share a long-run
    linear equilibrium relationship (i.e., their spread is stationary).

    H₀: no cointegration (the pair does NOT share a long-run equilibrium)

    Returns
    -------
    Dict["{t1}/{t2}" → {eg_stat, p_value, reject_h0, interpretation}]
    """
    try:
        from statsmodels.tsa.stattools import coint
    except ImportError:
        logger.error("statsmodels not installed. Run: pip install statsmodels")
        return {}

    tickers = list(cleaned.keys())
    if len(tickers) < 2:
        return {}

    # Build aligned price DataFrame
    price_frames = {
        ticker: cleaned[ticker]["Close"].dropna()
        for ticker in tickers
    }
    prices = pd.DataFrame(price_frames).dropna()

    results = {}
    logger.info("Test 5 — Engle-Granger Cointegration")

    for t1, t2 in combinations(tickers, 2):
        pair = f"{t1}/{t2}"
        try:
            eg_stat, p_val, crit_vals = coint(prices[t1], prices[t2])
            reject = p_val < ALPHA

            results[pair] = {
                "eg_statistic":     round(eg_stat, 4),
                "p_value":          round(p_val,   6),
                "critical_values":  {
                    "1%":  round(crit_vals[0], 4),
                    "5%":  round(crit_vals[1], 4),
                    "10%": round(crit_vals[2], 4),
                },
                "reject_h0":   reject,
                "interpretation": (
                    f"{t1} and {t2} ARE cointegrated {_significance(p_val).strip()} — "
                    "they share a long-run linear equilibrium. "
                    "A mean-reversion (pairs trading) strategy may be viable."
                    if reject else
                    f"{t1} and {t2} are NOT cointegrated (p={p_val:.4f}) — "
                    "no stable long-run linear relationship detected."
                ),
            }
            logger.info(
                "  %s: EG=%.4f  p=%.6f  %s  → %s",
                pair, eg_stat, p_val, _significance(p_val), _verdict(reject),
            )

        except Exception as exc:
            logger.warning("  Cointegration test failed for %s: %s", pair, exc)

    return results


# ─── Summary Report ───────────────────────────────────────────────────────────

def _print_section(title: str, data: dict, key_fields: list):
    """Print a formatted section of the results table to the console."""
    divider = "─" * 72
    print(f"\n  {title}")
    print(f"  {divider}")
    for name, res in data.items():
        print(f"\n  [{name}]")
        for field in key_fields:
            val = res.get(field, "N/A")
            print(f"    {field:<22} : {val}")
        print(f"    {'interpretation':<22} : {res.get('interpretation','')}")
    print(f"  {divider}")


def print_results(results: dict):
    """Pretty-print the full linear dependence test results to console."""
    print("\n" + "═" * 72)
    print("  LINEAR DEPENDENCE TEST RESULTS")
    print("  Significance level: α = 0.05")
    print("═" * 72)

    if results.get("autocorrelation"):
        _print_section(
            "TEST 1 — Ljung-Box Autocorrelation",
            results["autocorrelation"],
            ["lb_statistic", "lb_pvalue", "lags_tested", "reject_h0"],
        )

    if results.get("durbin_watson"):
        _print_section(
            "TEST 2 — Durbin-Watson",
            results["durbin_watson"],
            ["dw_statistic", "direction", "reject_h0"],
        )

    if results.get("cross_correlation"):
        _print_section(
            "TEST 3 — Pearson Cross-Correlation",
            results["cross_correlation"],
            ["correlation", "t_statistic", "p_value", "n_obs", "reject_h0"],
        )

    if results.get("granger_causality"):
        _print_section(
            "TEST 4 — Granger Causality",
            results["granger_causality"],
            ["best_lag", "f_statistic", "p_value", "reject_h0"],
        )

    if results.get("cointegration"):
        _print_section(
            "TEST 5 — Engle-Granger Cointegration",
            results["cointegration"],
            ["eg_statistic", "p_value", "reject_h0"],
        )


def save_results_csv(results: dict, output_path: str):
    """
    Flatten all test results into a single CSV for easy review.
    """
    rows = []

    for test_name, test_data in results.items():
        if not isinstance(test_data, dict):
            continue
        for subject, res in test_data.items():
            if not isinstance(res, dict):
                continue
            row = {
                "test":          test_name,
                "subject":       subject,
                "reject_h0":     res.get("reject_h0", ""),
                "interpretation": res.get("interpretation", ""),
            }
            # Add numeric fields
            for k, v in res.items():
                if k not in ("reject_h0", "interpretation", "all_lags",
                             "critical_values", "direction"):
                    row[k] = v
            rows.append(row)

    if rows:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        pd.DataFrame(rows).to_csv(output_path, index=False)
        logger.info("Linear dependence results saved → %s", output_path)


# ─── Public API ───────────────────────────────────────────────────────────────

def run_linear_dependence_tests(
    cleaned: Dict[str, pd.DataFrame],
    output_dir: Optional[str] = None,
    run_id: str = "",
    lb_lags: int = 10,
    granger_max_lag: int = 5,
) -> dict:
    """
    Run all five linear dependence tests on the cleaned return data.

    Parameters
    ----------
    cleaned         : Dict[ticker → cleaned DataFrame] from cleaning module.
    output_dir      : If provided, saves a CSV summary here.
    run_id          : Timestamp string used for the output filename.
    lb_lags         : Ljung-Box lag depth (default 10).
    granger_max_lag : Maximum lag for Granger causality tests (default 5).

    Returns
    -------
    Dict with keys: autocorrelation, durbin_watson, cross_correlation,
                    granger_causality, cointegration.
    """
    logger.info("Running linear dependence tests on %d assets…", len(cleaned))

    results = {
        "autocorrelation":   test_autocorrelation(cleaned, lags=lb_lags),
        "durbin_watson":     test_durbin_watson(cleaned),
        "cross_correlation": test_cross_correlation(cleaned),
        "granger_causality": test_granger_causality(cleaned, max_lag=granger_max_lag),
        "cointegration":     test_cointegration(cleaned),
    }

    print_results(results)

    if output_dir:
        ts  = run_id or __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        csv = os.path.join(output_dir, f"linear_dependence_{ts}.csv")
        save_results_csv(results, csv)

    logger.info("Linear dependence tests complete.")
    return results
