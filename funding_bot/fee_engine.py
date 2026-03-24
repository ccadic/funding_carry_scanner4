from __future__ import annotations
import pandas as pd
from .config import DEFAULT_TAKER_FEE_PCT

FEE_TABLE = {
    "binance": {"spot_taker_pct": 0.10, "perp_taker_pct": 0.04},
    "bybit": {"spot_taker_pct": 0.10, "perp_taker_pct": 0.055},
    "okx": {"spot_taker_pct": 0.10, "perp_taker_pct": 0.05},
}

def _fee(exchange_id: str, market_type: str) -> float:
    exch = exchange_id.lower()
    if exch not in FEE_TABLE:
        return DEFAULT_TAKER_FEE_PCT
    key = "spot_taker_pct" if market_type == "spot" else "perp_taker_pct"
    return float(FEE_TABLE[exch].get(key, DEFAULT_TAKER_FEE_PCT))

def estimate_route_fee_pct(opportunity: dict) -> dict:
    leg_mode = opportunity.get("leg_mode", "perp_perp")
    if leg_mode == "spot_perp":
        entry_exchange = opportunity["entry_exchange"]
        hedge_exchange = opportunity["hedge_exchange"]
        fee_open_pct = _fee(entry_exchange, "spot") + _fee(hedge_exchange, "perp")
        fee_close_pct = _fee(entry_exchange, "spot") + _fee(hedge_exchange, "perp")
    else:
        long_exchange = opportunity["long_exchange"]
        short_exchange = opportunity["short_exchange"]
        fee_open_pct = _fee(long_exchange, "perp") + _fee(short_exchange, "perp")
        fee_close_pct = _fee(long_exchange, "perp") + _fee(short_exchange, "perp")
    fee_total_pct = fee_open_pct + fee_close_pct
    return {
        "fee_open_pct": fee_open_pct,
        "fee_close_pct": fee_close_pct,
        "fee_total_pct": fee_total_pct,
    }

def build_fee_table_df() -> pd.DataFrame:
    rows = []
    for ex, values in FEE_TABLE.items():
        rows.append({
            "exchange": ex,
            "spot_taker_pct": values["spot_taker_pct"],
            "perp_taker_pct": values["perp_taker_pct"],
        })
    return pd.DataFrame(rows)
