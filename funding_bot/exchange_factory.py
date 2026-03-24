from __future__ import annotations
import ccxt
_cache = {}

def get_exchange(exchange_id: str):
    if exchange_id in _cache:
        return _cache[exchange_id]
    ex = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    _cache[exchange_id] = ex
    return ex
