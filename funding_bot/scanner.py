from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from .config import EXCHANGES, QUOTE, SYMBOL_LIMIT_PER_EXCHANGE, SCAN_WORKERS
from .exchange_factory import get_exchange
from .utils import now_iso

def _supported_symbol(symbol):
    return f":{QUOTE}" in symbol

def _fetch_history(exchange, symbol, limit):
    try:
        return exchange.fetch_funding_rate_history(symbol, limit=limit)
    except Exception:
        return []

def _next_funding_text(fr):
    for key in ("fundingDatetime", "nextFundingDatetime", "datetime"):
        value = fr.get(key)
        if value:
            return value
    return None

def _scan_symbol(exchange_id, symbol, history_limit):
    exchange = get_exchange(exchange_id)
    started = time.perf_counter()
    try:
        fr = exchange.fetch_funding_rate(symbol)
        funding = fr.get("fundingRate")
        if funding is None:
            return None, {"ts": now_iso(), "exchange": exchange_id, "symbol": symbol, "elapsed_ms": (time.perf_counter()-started)*1000, "status":"no_funding"}
        hist_df = pd.DataFrame(_fetch_history(exchange, symbol, history_limit))
        short_ma = long_ma = positive_ratio = volatility = None
        if not hist_df.empty and "fundingRate" in hist_df.columns:
            rates = pd.to_numeric(hist_df["fundingRate"], errors="coerce").dropna()
            if not rates.empty:
                short_ma = float(rates.tail(min(21, len(rates))).mean())
                long_ma = float(rates.tail(min(90, len(rates))).mean())
                positive_ratio = float((rates > 0).mean())
                volatility = float(rates.std(ddof=0)) if len(rates) > 1 else 0.0
        return {
            "exchange": exchange_id,
            "symbol": symbol,
            "funding": float(funding),
            "next_funding": _next_funding_text(fr),
            "short_ma": short_ma,
            "long_ma": long_ma,
            "positive_ratio": positive_ratio,
            "volatility": volatility,
            "timestamp": fr.get("timestamp"),
        }, {"ts": now_iso(), "exchange": exchange_id, "symbol": symbol, "elapsed_ms": (time.perf_counter()-started)*1000, "status":"ok"}
    except Exception as exc:
        return None, {"ts": now_iso(), "exchange": exchange_id, "symbol": symbol, "elapsed_ms": (time.perf_counter()-started)*1000, "status": f"error:{type(exc).__name__}"}

def scan_market(history_limit=120, return_latency=False):
    tasks = []
    for exchange_id in EXCHANGES:
        exchange = get_exchange(exchange_id)
        try:
            markets = exchange.load_markets()
        except Exception:
            continue
        for symbol in [s for s in markets.keys() if _supported_symbol(s)][:SYMBOL_LIMIT_PER_EXCHANGE]:
            tasks.append((exchange_id, symbol))
    rows, lrows = [], []
    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as ex:
        futs = [ex.submit(_scan_symbol, e, s, history_limit) for e, s in tasks]
        for f in as_completed(futs):
            row, lat = f.result()
            lrows.append(lat)
            if row:
                rows.append(row)
    df = pd.DataFrame(rows)
    lat_df = pd.DataFrame(lrows)
    for col in ["funding", "short_ma", "long_ma", "positive_ratio", "volatility"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return (df, lat_df) if return_latency else df
