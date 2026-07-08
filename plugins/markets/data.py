# data.py — Market data provider for the markets plugin.
#
# Uses yfinance (free, no API key) as the default backend for US equities.
# Supports crypto via CoinGecko's free API when coverage includes crypto.
# Falls back to Alpha Vantage or Finnhub if the user configures an API key.

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# US Equities (yfinance)
# ---------------------------------------------------------------------------

def _yf_quote(ticker: str) -> Dict[str, Any]:
    import yfinance as yf
    t = yf.Ticker(ticker)
    info = t.fast_info
    price = float(info.get("last_price") or info.get("lastPrice") or 0)
    prev = float(info.get("previous_close") or info.get("previousClose") or 0)
    change = price - prev
    change_pct = (change / prev * 100) if prev else 0
    return {
        "ticker": ticker.upper(),
        "price": round(price, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "volume": int(info.get("last_volume") or 0),
        "market_cap": float(info.get("market_cap") or 0),
    }


def _yf_history(ticker: str, period: str = "1mo", interval: str = "1d") -> List[Dict[str, Any]]:
    import yfinance as yf
    t = yf.Ticker(ticker)
    df = t.history(period=period, interval=interval)
    bars = []
    for ts, row in df.iterrows():
        bars.append({
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
            "volume": int(row["Volume"]),
        })
    return bars


def _yf_news(ticker: str, limit: int = 10) -> List[Dict[str, Any]]:
    import yfinance as yf
    t = yf.Ticker(ticker)
    raw = t.news or []
    items = []
    for item in raw[:limit]:
        content = item.get("content", item)
        items.append({
            "title": content.get("title", ""),
            "publisher": content.get("publisher", {}).get("name", "") if isinstance(content.get("publisher"), dict) else str(content.get("publisher", "")),
            "url": content.get("canonicalUrl", {}).get("url", "") if isinstance(content.get("canonicalUrl"), dict) else content.get("link", ""),
            "published": content.get("pubDate", content.get("providerPublishTime", "")),
            "summary": content.get("summary", "")[:500],
        })
    return items


def _yf_overview() -> Dict[str, Any]:
    indices = {"SPY": "S&P 500", "QQQ": "Nasdaq 100", "DIA": "Dow Jones"}
    result = {}
    for ticker, label in indices.items():
        try:
            q = _yf_quote(ticker)
            q["label"] = label
            result[ticker] = q
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", ticker, e)
            result[ticker] = {"ticker": ticker, "label": label, "error": str(e)}
    return result


# ---------------------------------------------------------------------------
# Crypto (CoinGecko free API)
# ---------------------------------------------------------------------------

_CG_BASE = "https://api.coingecko.com/api/v3"

_CG_ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "DOGE": "dogecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "LINK": "chainlink",
}


def _cg_quote(symbol: str) -> Dict[str, Any]:
    cg_id = _CG_ID_MAP.get(symbol.upper(), symbol.lower())
    url = f"{_CG_BASE}/simple/price?ids={cg_id}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true&include_market_cap=true"
    req = Request(url, headers={"User-Agent": "Zeus/1.0"})
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    if cg_id not in data:
        return {"ticker": symbol.upper(), "error": f"Unknown crypto: {symbol}"}
    d = data[cg_id]
    price = float(d.get("usd", 0))
    change_pct = float(d.get("usd_24h_change", 0))
    return {
        "ticker": symbol.upper(),
        "price": round(price, 2),
        "change": round(price * change_pct / 100, 2) if change_pct else 0,
        "change_pct": round(change_pct, 2),
        "volume": int(d.get("usd_24h_vol", 0)),
        "market_cap": float(d.get("usd_market_cap", 0)),
    }


# ---------------------------------------------------------------------------
# Public API — routes to the right backend based on ticker type
# ---------------------------------------------------------------------------

def is_crypto(ticker: str) -> bool:
    return ticker.upper() in _CG_ID_MAP or ticker.lower() in _CG_ID_MAP.values()


def get_quote(ticker: str, coverage: str = "us-only") -> Dict[str, Any]:
    try:
        if is_crypto(ticker) and coverage != "us-only":
            return _cg_quote(ticker)
        return _yf_quote(ticker)
    except Exception as e:
        logger.warning("Quote failed for %s: %s", ticker, e)
        return {"ticker": ticker.upper(), "error": str(e)}


def get_history(ticker: str, period: str = "1mo", interval: str = "1d", coverage: str = "us-only") -> List[Dict[str, Any]]:
    try:
        return _yf_history(ticker, period, interval)
    except Exception as e:
        logger.warning("History failed for %s: %s", ticker, e)
        return []


def get_news(ticker: str, limit: int = 10, coverage: str = "us-only") -> List[Dict[str, Any]]:
    try:
        return _yf_news(ticker, limit)
    except Exception as e:
        logger.warning("News failed for %s: %s", ticker, e)
        return []


def get_market_overview(coverage: str = "us-only") -> Dict[str, Any]:
    try:
        return _yf_overview()
    except Exception as e:
        logger.warning("Overview failed: %s", e)
        return {"error": str(e)}
