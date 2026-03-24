from __future__ import annotations
import numpy as np
import pandas as pd
from .config import DEFAULT_SLIPPAGE_PCT, SLIPPAGE_LOOKBACK, SLIPPAGE_PERCENTILE, DATA_DIR
from .utils import read_csv_if_exists
from .exchange_factory import get_exchange

def _estimate_orderbook_slippage_single(exchange_id: str, symbol: str, usd_size: float, side: str) -> float:
    try:
        exchange = get_exchange(exchange_id)
        book = exchange.fetch_order_book(symbol, limit=50)
        levels = book["asks"] if side == "buy" else book["bids"]
        if not levels:
            return DEFAULT_SLIPPAGE_PCT
        best_price = float(levels[0][0])
        remaining_usd = usd_size
        filled_notional = 0.0
        filled_qty = 0.0
        for price, qty in levels:
            price = float(price); qty = float(qty)
            level_usd = price * qty
            take_usd = min(level_usd, remaining_usd)
            take_qty = take_usd / price
            filled_notional += take_qty * price
            filled_qty += take_qty
            remaining_usd -= take_usd
            if remaining_usd <= 1e-9:
                break
        if filled_qty <= 0:
            return DEFAULT_SLIPPAGE_PCT
        avg_price = filled_notional / filled_qty
        slip = abs(avg_price - best_price) / best_price * 100.0
        return float(slip)
    except Exception:
        return DEFAULT_SLIPPAGE_PCT

def get_logged_slippage_df(data_dir: str = DATA_DIR) -> pd.DataFrame:
    return read_csv_if_exists(f"{data_dir}/slippage_log.csv")

def get_calibrated_slippage_pct(exchange_id: str, symbol: str, usd_size: float, data_dir: str = DATA_DIR) -> float:
    df = get_logged_slippage_df(data_dir)
    if df.empty or "slippage_pct" not in df.columns:
        return DEFAULT_SLIPPAGE_PCT
    filt = df[(df["exchange"] == exchange_id) & (df["symbol"] == symbol)].copy()
    if filt.empty:
        filt = df[df["exchange"] == exchange_id].copy()
    if filt.empty:
        return DEFAULT_SLIPPAGE_PCT
    filt = filt.tail(SLIPPAGE_LOOKBACK)
    vals = pd.to_numeric(filt["slippage_pct"], errors="coerce").dropna().values
    if len(vals) == 0:
        return DEFAULT_SLIPPAGE_PCT
    return float(np.percentile(vals, SLIPPAGE_PERCENTILE))

def estimate_route_slippage_pct(opportunity: dict, usd_size: float, data_dir: str = DATA_DIR) -> dict:
    leg_mode = opportunity.get("leg_mode", "perp_perp")
    if leg_mode == "spot_perp":
        entry_exchange = opportunity["entry_exchange"]
        hedge_exchange = opportunity["hedge_exchange"]
        slip_orderbook_1 = _estimate_orderbook_slippage_single(entry_exchange, opportunity["symbol"], usd_size, "buy")
        slip_orderbook_2 = _estimate_orderbook_slippage_single(hedge_exchange, opportunity["symbol"], usd_size, "sell")
        slip_cal_1 = get_calibrated_slippage_pct(entry_exchange, opportunity["symbol"], usd_size, data_dir)
        slip_cal_2 = get_calibrated_slippage_pct(hedge_exchange, opportunity["symbol"], usd_size, data_dir)
    else:
        long_exchange = opportunity["long_exchange"]
        short_exchange = opportunity["short_exchange"]
        slip_orderbook_1 = _estimate_orderbook_slippage_single(long_exchange, opportunity["symbol"], usd_size, "buy")
        slip_orderbook_2 = _estimate_orderbook_slippage_single(short_exchange, opportunity["symbol"], usd_size, "sell")
        slip_cal_1 = get_calibrated_slippage_pct(long_exchange, opportunity["symbol"], usd_size, data_dir)
        slip_cal_2 = get_calibrated_slippage_pct(short_exchange, opportunity["symbol"], usd_size, data_dir)

    slip_orderbook_total = slip_orderbook_1 + slip_orderbook_2
    slip_calibrated_total = slip_cal_1 + slip_cal_2
    slippage_estimated_pct = max(slip_orderbook_total, slip_calibrated_total, DEFAULT_SLIPPAGE_PCT)

    return {
        "slippage_orderbook_pct": slip_orderbook_total,
        "slippage_calibrated_pct": slip_calibrated_total,
        "slippage_estimated_pct": slippage_estimated_pct,
    }

def build_slippage_summary_df(data_dir: str = DATA_DIR) -> pd.DataFrame:
    df = get_logged_slippage_df(data_dir)
    if df.empty:
        return pd.DataFrame()
    g = (
        df.groupby(["exchange", "symbol"], dropna=False)["slippage_pct"]
        .agg(["count", "mean", "median", "max"])
        .reset_index()
        .sort_values(["exchange", "count"], ascending=[True, False])
    )
    return g
