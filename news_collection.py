"""
news_collection.py — NewsAPI integration (second independent data source)
Satisfies the brief's requirement for ≥2 source types.
"""
import os
import requests
import pandas as pd
from datetime import datetime, timedelta

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")          # free tier: 100 req/day
NEWSAPI_BASE = "https://newsapi.org/v2/everything"

def fetch_newsapi_headlines(
    query: str,
    days_back: int = 7,
    max_articles: int = 10,
    language: str = "en",
) -> pd.DataFrame:
    """
    Fetch recent financial news from NewsAPI (independent of yfinance).

    Args:
        query: Search string, e.g. "Apple stock AAPL"
        days_back: How many days of history to fetch
        max_articles: Maximum articles to return
        language: Article language filter

    Returns:
        DataFrame with columns: title, source, published_at, description, url
    """
    if not NEWSAPI_KEY:
        raise ValueError("NEWSAPI_KEY not set in environment.")

    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    params = {
        "q": query,
        "from": from_date,
        "sortBy": "relevancy",
        "language": language,
        "pageSize": max_articles,
        "apiKey": NEWSAPI_KEY,
    }
    response = requests.get(NEWSAPI_BASE, params=params, timeout=10)
    response.raise_for_status()
    articles = response.json().get("articles", [])

    rows = []
    for a in articles:
        rows.append({
            "title": a.get("title", ""),
            "source": a.get("source", {}).get("name", ""),
            "published_at": a.get("publishedAt", ""),
            "description": a.get("description", ""),
            "url": a.get("url", ""),
        })
    return pd.DataFrame(rows)