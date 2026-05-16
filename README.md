# FinAgent — AI-Powered Financial Data Agent

> IT Application in Banking and Finance — Midterm Assessment 2026

An end-to-end autonomous financial data pipeline that collects live market data from two independent sources, cleans and engineers features, produces publication-quality visualisations, and generates a detailed investment report via the Groq AI API.

---

## Project Structure

```
finagent/
├── .env.example              API key template (copy to .env)
├── config.py                 All settings & constants
├── main.py                   Pipeline orchestrator (run this)
├── requirements.txt          Python dependencies
├── modules/
│   ├── collection.py         Phase 1a: Yahoo Finance data collection
│   ├── news_collection.py    Phase 1b: NewsAPI headlines (second data source)
│   ├── cleaning.py           Phase 2: cleaning + feature engineering
│   ├── visualization.py      Phase 3: chart generation
│   ├── ai_analysis.py        Phase 4: Groq AI analysis
│   ├── report_docx.py        Phase 4: Word document generator
│   └── demo_data.py          Synthetic data for offline/demo mode
├── data/
│   ├── raw/                  Raw CSVs saved by collection module
│   └── processed/            Cleaned CSVs saved by cleaning module
├── outputs/
│   ├── charts/
│   │   └── <run_id>/         Each run gets its own timestamped folder
│   └── reports/
│       └── <run_id>/         Matching folder for .md and .docx reports
└── logs/                     One log file per pipeline run
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
# Windows
copy .env.example .env

# Mac / Linux
cp .env.example .env
```

Open `.env` and fill in your keys:

```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
NEWSAPI_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

| Key | Required for | Get it free at |
|---|---|---|
| `GROQ_API_KEY` | Phase 4 — AI report generation | [console.groq.com](https://console.groq.com) |
| `NEWSAPI_KEY` | Phase 1 — NewsAPI headlines | [newsapi.org](https://newsapi.org) |

Both keys are free with no credit card required. The pipeline runs Phases 1–3 with only `NEWSAPI_KEY`; Phase 4 additionally requires `GROQ_API_KEY`. If either key is missing the affected step is skipped gracefully with a logged warning.

### 3. Run the pipeline

```bash
# Live data from Yahoo Finance + NewsAPI:
python main.py

# Synthetic demo data (no internet required):
python main.py --demo
```

All outputs are written automatically. Each run creates its own timestamped sub-folder so previous runs are never overwritten.

---

## Data Sources

The pipeline collects data from **two independent source types** to satisfy the project requirement for diverse data collection.

| # | Type | Provider | Library / Method | What Is Collected |
|---|---|---|---|---|
| 1 | Stock OHLCV | Yahoo Finance | `yfinance` REST wrapper | Daily adjusted prices & volume for AAPL, MSFT, NVDA, GOOGL |
| 1 | Macro Indicators | Yahoo Finance | `yfinance` REST wrapper | Gold (GC=F), WTI Oil (CL=F), USD/EUR (EURUSD=X) closing prices |
| 1 | Company Profiles | Yahoo Finance | `yfinance` REST wrapper | Sector, P/E ratios, market cap, beta, analyst rating & price target |
| **2** | **News Headlines** | **NewsAPI** | **`requests` HTTP client** | **Up to 10 recent articles per ticker — title, source, date, description** |

Source 1 (Yahoo Finance via `yfinance`) and Source 2 (NewsAPI via direct `requests` HTTP calls) use entirely different APIs, authentication methods, and data formats. Their integration is handled in separate modules: `collection.py` and `news_collection.py`.

---

## Pipeline Phases

### Phase 1 — Data Collection

Two modules run in sequence during Phase 1.

**`modules/collection.py` — Yahoo Finance**

- Fetches 1 year of daily OHLCV data per ticker via `yfinance` with `auto_adjust=True` (adjusts for splits and dividends automatically)
- Retrieves commodity and forex macro closing prices
- Fetches company fundamentals: sector, industry, market cap, P/E ratios, dividend yield, beta, analyst rating, and price target
- All raw data saved to `data/raw/` as CSVs

Reliability features built into every fetch function:
- Exponential backoff retry decorator (max 3 attempts; waits 1s, 2s, 4s between attempts)
- Per-ticker 500ms rate-limit delay to avoid Yahoo Finance throttling
- DataFrame validation after every fetch (checks for None, empty, minimum row count, required columns)
- Graceful skip on failure — a single bad ticker never crashes the pipeline
- Timezone stripping to prevent index merge errors downstream

**`modules/news_collection.py` — NewsAPI**

- Uses Python `requests` to call the NewsAPI `/v2/everything` endpoint directly (no yfinance dependency)
- Fetches up to 10 recent English-language articles per ticker query over the last 7 days
- Returns a structured DataFrame per ticker: title, source, published date, description, URL
- Requires `NEWSAPI_KEY` in `.env`; skips gracefully with a warning if the key is absent
- Free tier: 100 requests/day, sufficient for 4 tickers with margin

### Phase 2 — Cleaning & Feature Engineering (`modules/cleaning.py`)

Raw financial data is cleaned in a documented, logged pipeline:

- **Missing values** — forward-fill → back-fill → drop fully-empty rows
- **Duplicates** — detected, logged, and removed (keeps last occurrence)
- **Type normalisation** — datetime index enforcement, numeric coercion
- **Outlier detection** — z-score flagging (`|z| > 3.0`) on daily returns; flagged rows are *kept* and marked in a `Daily_Return_Outlier` boolean column. Outliers are not removed because large single-day moves may be legitimate events (earnings surprises, macro shocks). The flag allows downstream modules to identify and explain them without discarding the data.

Engineered features added to each ticker's DataFrame:

| Column | Description |
|---|---|
| `Daily_Return` | Percentage close-to-close change |
| `MA_7` | 7-day rolling mean of close price |
| `MA_30` | 30-day rolling mean of close price |
| `BB_Upper` / `BB_Middle` / `BB_Lower` | Bollinger Bands (20-day window, ±2σ) |
| `Volatility_30` | Annualised 30-day rolling volatility (×√252) |
| `Cumulative_Return` | Buy-and-hold cumulative return from day 0 |

### Phase 3 — Visualisation (`modules/visualization.py`)

Five charts are generated per run, saved to `outputs/charts/<run_id>/`. Each run is isolated — nothing is overwritten.

| # | Chart | Filename |
|---|---|---|
| 1 | Price trend line with MA7/MA30 overlay and volume subplot | `chart1_price_volume.png` |
| 2 | Daily return correlation heatmap across all assets | `chart2_correlation_heatmap.png` |
| 3 | Return distribution — histogram + KDE per ticker | `chart3_return_distribution.png` |
| 4 | Rolling statistics and Bollinger Bands | `chart4_rolling_stats.png` |
| 5 | Cumulative returns comparison — all assets on one axis *(bonus)* | `chart5_cumulative_returns.png` |

### Phase 4 — AI Analysis (`modules/ai_analysis.py` + `modules/report_docx.py`)

Uses the Groq API (`llama-3.3-70b-versatile`) to generate a structured seven-section investment report. Outputs are saved to `outputs/reports/<run_id>/`.

**Context sent to the model:**

All statistics are pre-computed from actual data and passed to the model as structured tables. The model receives no raw price data — only derived metrics — which prevents it from inventing figures.

- Company profiles (sector, market cap, P/E, beta, analyst rating and target)
- Price and return statistics (52-week range, period return, volatility, outlier count)
- Distribution metrics (mean, std, skew, kurtosis, Sharpe ratio)
- Pairwise return correlations with plain-English strength labels
- Macro indicator summary (Gold, Oil, USD/EUR)
- Recent news headlines from both yfinance and NewsAPI with publisher and summary

**Hallucination prevention:** The system prompt explicitly instructs the model to cite a specific numeric value from the provided data for every factual claim it makes, and not to draw conclusions from information not present in the context tables.

**Seven report sections generated:**

1. Company Overview — business model, segments, market position
2. Trend & Price Analysis — MA signals, best and worst single-day moves
3. Return Distribution & Risk-Adjusted Performance — Sharpe ratio, skew, kurtosis
4. Risk Commentary — volatility ranking, rolling vs annualised vol, macro context
5. News Sentiment & Narrative — per-ticker sentiment, headline impact, contradictions
6. Cross-Asset Comparison — P/E, P/B, beta, analyst targets vs current price
7. Investment Perspective — most attractive and most risky asset with supporting metrics

**Two output files per run:**

- `ai_analysis_<run_id>.md` — raw Markdown report
- `FinAgent_Report_<run_id>.docx` — formatted Word document with cover page, statistics table, styled headings, bullet points, and page numbers

---

## Demo Mode

Running with `--demo` generates synthetic market data using Geometric Brownian Motion. No internet connection is required for Phases 1–3; only Phase 4 needs a Groq key.

```bash
python main.py --demo
```

Synthetic assets have distinct statistical personalities (NVDA: high volatility, high drift; MSFT: low volatility, moderate drift) so charts and the AI analysis produce meaningful, differentiated output rather than flat lines.

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `STOCK_TICKERS` | `["AAPL","MSFT","NVDA","GOOGL"]` | Assets to analyse |
| `BENCHMARK_TICKER` | `"^GSPC"` | S&P 500 benchmark reference |
| `DATA_PERIOD` | `"1y"` | Historical window fed to yfinance |
| `DATA_INTERVAL` | `"1d"` | Bar size (daily) |
| `GROQ_API_KEY` | *(from .env)* | Groq API key for Phase 4 |
| `GROQ_MODEL` | `"llama-3.3-70b-versatile"` | Groq model for analysis |
| `AI_MAX_TOKENS` | `3500` | Max output tokens per Groq call |
| `NEWSAPI_KEY` | *(from .env)* | NewsAPI key for Phase 1 news |
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
- `.env` is listed in `.gitignore` and is never committed to the repository
- `.env.example` is provided as a safe template — copy it to `.env` and fill in real keys
- If `NEWSAPI_KEY` is missing, Phase 1 news collection falls back to yfinance headlines only and logs a warning
- If `GROQ_API_KEY` is missing, Phase 4 is skipped entirely with a clear console message

---

## Requirements

- Python 3.10+
- Internet connection (bypassed in `--demo` mode for Phases 1–3)
- `NEWSAPI_KEY` — free at [newsapi.org](https://newsapi.org), no credit card required
- `GROQ_API_KEY` — free at [console.groq.com](https://console.groq.com), no credit card required (Phase 4 only)

---

## Dependencies

```
yfinance          stock prices, macro indicators, company profiles
requests          NewsAPI HTTP calls (second independent data source)
pandas / numpy    data processing and feature engineering
matplotlib        chart rendering (headless Agg backend)
seaborn           heatmap and distribution styling
scipy             KDE for return distribution charts
groq              Groq AI API client
python-docx       Word document generation
python-dotenv     .env file loading
```

---

## Evaluator Q&A

**Q: You use two data sources — how are they genuinely different?**
Yahoo Finance data is retrieved via the `yfinance` Python wrapper, which handles authentication and parsing internally. NewsAPI data is fetched using direct `requests` HTTP calls to a REST endpoint with API key authentication, returning JSON that we parse and normalise ourselves. They use different APIs, different authentication flows, different data formats, and are handled in entirely separate modules (`collection.py` vs `news_collection.py`).

**Q: How does your pipeline handle API rate limits?**
Every fetch function in `collection.py` includes a 500ms `time.sleep()` between individual ticker requests. All fetch functions are decorated with `@with_retry`, which implements exponential backoff: if a request fails, it waits 1s before the second attempt, 2s before the third, then logs an error and returns `None` rather than crashing. The NewsAPI free tier (100 req/day) is well within the limit for 4 tickers.

**Q: How does your pipeline handle stock splits and dividends?**
`yfinance` is called with `auto_adjust=True`, which back-adjusts all historical prices for splits and dividends automatically. The cleaning module additionally flags large single-day moves (`|z| > 3`) as outliers in a dedicated column, allowing the AI analysis module to identify and comment on them without treating them as data errors.

**Q: What is the LLM prompt structure? How did you prevent hallucinations?**
All statistics are pre-computed from the actual cleaned data (returns, volatility, Sharpe ratio, correlations, MA positions, outlier counts) and passed to the model as structured context tables. The system prompt explicitly requires the model to cite a specific number from the provided data for every factual claim. The model is instructed not to draw conclusions from information absent in its context. Using a lower temperature setting reduces the probability of the model generating plausible-sounding but unsupported figures.

**Q: Why Groq instead of OpenAI or Anthropic?**
Groq provides a free tier with no credit card, 14,400 requests per day, and runs `llama-3.3-70b-versatile` — a capable open-weight model that performs well on structured analytical tasks. This makes the project fully reproducible by any evaluator without billing setup. The choice is a deliberate trade-off: reproducibility and zero cost over marginal quality improvements from GPT-4 or Claude.

**Q: Why are outputs saved per-run instead of overwriting?**
Each `python main.py` invocation generates a unique `run_id` based on the current timestamp, used as a sub-folder for both charts and reports. This preserves historical runs for comparison, allows debugging of specific runs via their log file, and prevents accidental data loss during iterative development.

**Q: How would you scale this to 500 assets?**
The current implementation fetches tickers sequentially, which would take several minutes at 500ms delay per ticker. Scaling would require: concurrent fetching with `asyncio` and `httpx` (replacing sequential loops with a bounded semaphore to respect rate limits), a time-series database such as TimescaleDB or InfluxDB for storage (replacing per-run CSVs), batched Groq calls to process assets in groups of 10–20 rather than all at once, and a caching layer keyed by ticker and date to avoid re-fetching data that hasn't changed.

**Q: What is the biggest limitation of the current implementation?**
The NewsAPI free tier restricts article history to the last 30 days and returns descriptions rather than full article text, which limits the depth of sentiment analysis the AI can perform. A production system would integrate a paid news provider with full article access and a dedicated NLP sentiment model rather than relying on the LLM to infer sentiment from brief summaries.
