# FinAgent — AI-Powered Financial Data Agent

> IT Application in Banking and Finance — Midterm Assessment 2026

An end-to-end autonomous financial data pipeline that collects live market data,
cleans and engineers features, produces publication-quality visualisations, and
generates a detailed investment report via the Groq AI API (free, no credit card).

---

## Project Structure

```
finagent/
├── .env.example          ← API key template (copy to .env)
├── config.py             ← All settings & constants
├── main.py               ← Pipeline orchestrator (run this)
├── requirements.txt      ← Python dependencies
├── modules/
│   ├── collection.py     ← Phase 1: data collection
│   ├── cleaning.py       ← Phase 2: cleaning + feature engineering
│   ├── visualization.py  ← Phase 3: chart generation
│   ├── ai_analysis.py    ← Phase 4: Groq AI analysis
│   ├── report_docx.py    ← Phase 4: Word document generator
│   └── demo_data.py      ← Synthetic data for offline/demo mode
├── data/
│   ├── raw/              ← Raw CSVs saved by collection module
│   └── processed/        ← Cleaned CSVs saved by cleaning module
├── outputs/
│   ├── charts/
│   │   └── <run_id>/     ← Each run gets its own timestamped folder
│   └── reports/
│       └── <run_id>/     ← Matching folder for .md and .docx reports
└── logs/                 ← One log file per pipeline run
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure your API key

```bash
# Windows
copy .env.example .env

# Mac / Linux
cp .env.example .env
```

Open `.env` and paste your Groq key:

```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Get a free key (no credit card) at **https://console.groq.com**.

### 3. Run the pipeline

```bash
# Live data from Yahoo Finance:
python main.py

# Synthetic demo data (no internet required):
python main.py --demo
```

All outputs are written automatically. Each run creates its own
timestamped sub-folder so previous runs are never overwritten.

---

## Data Sources

| Type | Provider | What Is Collected |
|---|---|---|
| **Stock OHLCV** | Yahoo Finance (`yfinance`) | Daily prices & volume for AAPL, MSFT, NVDA, GOOGL |
| **Macro Indicators** | Yahoo Finance (`yfinance`) | Gold (GC=F), WTI Oil (CL=F), USD/EUR (EURUSD=X) |
| **News Headlines** | Yahoo Finance (built-in) | Up to 5 recent articles per ticker with summaries |
| **Company Profiles** | Yahoo Finance (`yfinance`) | Sector, P/E, market cap, analyst rating, description |

---

## Pipeline Phases

### Phase 1 — Data Collection (`modules/collection.py`)
- Fetches 1 year of daily OHLCV via `yfinance` with `auto_adjust=True`
- Retrieves commodity & forex macro closing prices
- Collects recent news headlines and article summaries per ticker
- Fetches company fundamentals: sector, industry, market cap, P/E ratios,
  dividend yield, beta, analyst rating, and price target
- All raw data saved to `data/raw/` as CSVs
- No API keys required for this phase

### Phase 2 — Cleaning & Feature Engineering (`modules/cleaning.py`)
- **Missing values** — forward-fill → back-fill → drop fully-empty rows
- **Duplicates** — detected, logged, and removed (keeps last occurrence)
- **Type normalisation** — datetime index enforcement, numeric coercion
- **Outlier detection** — z-score flagging (`|z| > 3.0`) on daily returns;
  flagged rows are kept and marked in a `Daily_Return_Outlier` column
- **Engineered features** added to each DataFrame:

| Column | Description |
|---|---|
| `Daily_Return` | Percentage close-to-close change |
| `MA_7` | 7-day rolling mean of close price |
| `MA_30` | 30-day rolling mean of close price |
| `BB_Upper` / `BB_Middle` / `BB_Lower` | Bollinger Bands (20-day window, ±2σ) |
| `Volatility_30` | Annualised 30-day rolling volatility |
| `Cumulative_Return` | Buy-and-hold cumulative return from day 0 |

### Phase 3 — Visualisation (`modules/visualization.py`)
Each run saves charts into `outputs/charts/<run_id>/` — nothing is overwritten.

| # | Chart | Filename |
|---|---|---|
| 1 | Price Trend + Volume Overlay (MA7, MA30) | `chart1_price_volume.png` |
| 2 | Daily Return Correlation Heatmap | `chart2_correlation_heatmap.png` |
| 3 | Return Distribution — Histogram + KDE | `chart3_return_distribution.png` |
| 4 | Rolling Statistics & Bollinger Bands | `chart4_rolling_stats.png` |
| 5 | Cumulative Returns Comparison *(bonus)* | `chart5_cumulative_returns.png` |

### Phase 4 — AI Analysis (`modules/ai_analysis.py` + `modules/report_docx.py`)
Uses the **Groq API** (`llama-3.3-70b-versatile`) to generate a structured
seven-section investment report. Outputs are saved to `outputs/reports/<run_id>/`.

**Context sent to the model** (plain-text tables, not JSON):
- Company profiles (sector, market cap, P/E, beta, analyst rating)
- Price & return statistics (52-week range, period return, volatility, outliers)
- Return distribution metrics (mean, std, skew, kurtosis, Sharpe ratio)
- Pairwise return correlations with plain-English labels
- Macro indicator summary (Gold, Oil, USD/EUR)
- Recent news headlines with publisher and article summaries

**Seven report sections generated:**
1. Company Overview — business model, segments, market position
2. Trend & Price Analysis — MA signals, best/worst single-day moves
3. Return Distribution & Risk-Adjusted Performance — Sharpe, skew, kurtosis
4. Risk Commentary — volatility ranking, rolling vs annualised vol, macro factors
5. News Sentiment & Narrative — per-ticker sentiment, headline impact, contradictions
6. Cross-Asset Comparison — P/E, P/B, beta, analyst targets vs price
7. Investment Perspective — most attractive / most risky asset, one metric to watch each

**Two output files per run:**
- `ai_analysis_<run_id>.md` — raw Markdown report
- `FinAgent_Report_<run_id>.docx` — formatted Word document with cover page,
  stats table, styled headings, bullet points, and page numbers

---

## Demo Mode

Running with `--demo` generates synthetic market data using Geometric Brownian
Motion — no internet connection or API key required (except Groq for Phase 4).

```bash
python main.py --demo
```

Synthetic assets have distinct statistical personalities (NVDA high-vol/high-drift,
MSFT low-vol/moderate-drift, etc.) so charts and analysis look meaningful.

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `STOCK_TICKERS` | `["AAPL","MSFT","NVDA","GOOGL"]` | Assets to analyse |
| `BENCHMARK_TICKER` | `"^GSPC"` | S&P 500 benchmark reference |
| `DATA_PERIOD` | `"1y"` | Historical window fed to yfinance |
| `DATA_INTERVAL` | `"1d"` | Bar size (daily) |
| `GROQ_API_KEY` | *(from .env)* | Groq API key for Phase 4 |
| `GROQ_MODEL` | `"llama-3.3-70b-versatile"` | Groq model used for analysis |
| `AI_MAX_TOKENS` | `3500` | Max output tokens per Groq call |
| `OUTLIER_Z_THRESH` | `3.0` | Z-score threshold for outlier flagging |
| `BB_WINDOW` | `20` | Bollinger Band lookback period |
| `BB_STD_MULT` | `2.0` | Bollinger Band standard deviation multiplier |
| `MA_WINDOWS` | `[7, 30]` | Rolling mean windows in days |

---

## Output Structure per Run

```
outputs/
├── charts/
│   └── 20260502_143012/
│       ├── chart1_price_volume.png
│       ├── chart2_correlation_heatmap.png
│       ├── chart3_return_distribution.png
│       ├── chart4_rolling_stats.png
│       └── chart5_cumulative_returns.png
└── reports/
    └── 20260502_143012/
        ├── ai_analysis_20260502_143012.md
        └── FinAgent_Report_20260502_143012.docx
```

---

## API Key Management

- Keys are loaded from `.env` using `python-dotenv`
- `.env` is listed in `.gitignore` — **never commit it**
- `.env.example` is provided as a safe template for collaborators
- Phases 1–3 require no API key at all
- Phase 4 skips gracefully with a clear message if `GROQ_API_KEY` is missing

---

## Requirements

- Python 3.10+
- Internet connection (skipped in `--demo` mode)
- Groq API key (Phase 4 only — free at https://console.groq.com)

---

## Dependencies

```
yfinance          — stock, macro, news, and company data
pandas / numpy    — data processing and feature engineering
matplotlib        — chart rendering (headless / Agg backend)
seaborn           — heatmap and distribution styling
scipy             — KDE for return distribution charts
groq              — Groq AI API client
python-docx       — Word document generation
python-dotenv     — .env file loading
```

---

## Suggested Git Commit History

```
feat: initialise project structure and config
feat: implement data collection (OHLCV, macro, news, company profiles)
feat: implement cleaning pipeline and feature engineering
feat: implement all 5 visualisation charts with run-id isolation
feat: integrate Groq AI analysis with 7-section report prompt
feat: add Word document report generator (report_docx.py)
feat: add synthetic demo data mode (demo_data.py)
refactor: thread run_id through all phases for isolated outputs
refactor: clean up all module docstrings and remove stale references
docs: update README to match final codebase
```

---

## Common Evaluator Questions

**Q: Why Yahoo Finance instead of a paid provider?**  
No API key required, covers stocks, commodities, forex, news, and company
fundamentals in one library — ideal for a self-contained academic project.

**Q: How does the pipeline handle stock splits and dividends?**  
`yfinance` is called with `auto_adjust=True`, which back-adjusts all historical
prices for splits and dividends automatically. The cleaning module additionally
flags large single-day moves (`|z| > 3`) as outliers.

**Q: Why Groq instead of OpenAI or Anthropic?**  
Groq offers a free tier (no credit card) with 14,400 requests/day and runs
`llama-3.3-70b-versatile` — a powerful open-weight model. This makes the project
fully reproducible without any billing setup.

**Q: How do you prevent AI hallucinations in the report?**  
The model receives a compact plain-text context table with all key statistics
pre-computed from the actual data. The prompt explicitly instructs the model to
cite specific numbers from the provided data and not extrapolate beyond it.

**Q: Why are outputs saved per-run instead of overwriting?**  
Each `python main.py` invocation generates a unique `run_id` (timestamp) used
as a sub-folder for both charts and reports. This preserves historical runs for
comparison and prevents accidental data loss.

**Q: How would you scale this to 500 assets?**  
Replace sequential fetching with `asyncio` / `httpx` concurrent requests, store
data in a time-series database (TimescaleDB or InfluxDB), batch Groq calls to
process assets in groups, and add a caching layer to avoid re-fetching unchanged
historical data.
