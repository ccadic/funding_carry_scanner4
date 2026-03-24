from __future__ import annotations
import pandas as pd
from .config import TRADING_MODE, SPOT_EXCHANGE, DATA_DIR
from .fee_engine import estimate_route_fee_pct
from .slippage_engine import estimate_route_slippage_pct

def build_opportunities(scan_df, min_spread, taker_fee_pct, slippage_pct, min_net_spread_pct):
    if scan_df.empty:
        return pd.DataFrame()
    rows = []
    for symbol, g in scan_df.groupby("symbol"):
        g = g.dropna(subset=["funding"])
        if g.empty:
            continue

        if TRADING_MODE == "spot_perp":
            perp_rows = g[g["exchange"] != SPOT_EXCHANGE].copy()
            if perp_rows.empty:
                continue
            short_row = perp_rows.loc[perp_rows["funding"].idxmax()]
            spread = float(short_row["funding"])
            if spread < min_spread:
                continue

            base = {
                "symbol": symbol,
                "leg_mode": "spot_perp",
                "entry_exchange": SPOT_EXCHANGE,
                "hedge_exchange": short_row["exchange"],
                "route_label": f"SPOT {SPOT_EXCHANGE} / SHORT {short_row['exchange']}",
                "spread": spread,
                "next_funding_long": None,
                "next_funding_short": short_row.get("next_funding"),
                "positive_ratio": short_row.get("positive_ratio"),
                "volatility_avg": short_row.get("volatility"),
            }
        else:
            if len(g) < 2:
                continue
            max_row = g.loc[g["funding"].idxmax()]
            min_row = g.loc[g["funding"].idxmin()]
            spread = float(max_row["funding"] - min_row["funding"])
            if spread < min_spread:
                continue

            base = {
                "symbol": symbol,
                "leg_mode": "perp_perp",
                "long_exchange": str(min_row["exchange"]),
                "short_exchange": str(max_row["exchange"]),
                "route_label": f"LONG {min_row['exchange']} / SHORT {max_row['exchange']}",
                "spread": spread,
                "next_funding_long": min_row.get("next_funding"),
                "next_funding_short": max_row.get("next_funding"),
                "positive_ratio": pd.Series([min_row.get("positive_ratio"), max_row.get("positive_ratio")]).mean(skipna=True),
                "volatility_avg": pd.Series([min_row.get("volatility"), max_row.get("volatility")]).mean(skipna=True),
            }

        est_edge_pct_per_cycle = spread * 100
        est_edge_pct_daily = est_edge_pct_per_cycle * 3
        est_edge_pct_annual = est_edge_pct_daily * 365

        fee_info = estimate_route_fee_pct(base)
        slip_info = estimate_route_slippage_pct(base, usd_size=100.0, data_dir=DATA_DIR)
        cost_total_pct = fee_info["fee_total_pct"] + slip_info["slippage_estimated_pct"]
        net_spread_pct = est_edge_pct_per_cycle - cost_total_pct
        days_break_even = cost_total_pct / est_edge_pct_daily if est_edge_pct_daily > 0 else None
        decision = "Exploitable" if net_spread_pct >= min_net_spread_pct else "Faible edge"

        rows.append({
            **base,
            "spread_pct_cycle": est_edge_pct_per_cycle,
            "spread_pct_day": est_edge_pct_daily,
            "spread_pct_annual": est_edge_pct_annual,
            "fee_open_pct": fee_info["fee_open_pct"],
            "fee_close_pct": fee_info["fee_close_pct"],
            "fee_total_pct": fee_info["fee_total_pct"],
            "slippage_orderbook_pct": slip_info["slippage_orderbook_pct"],
            "slippage_calibrated_pct": slip_info["slippage_calibrated_pct"],
            "slippage_estimated_pct": slip_info["slippage_estimated_pct"],
            "cost_total_pct": cost_total_pct,
            "net_spread_pct": net_spread_pct,
            "days_break_even": days_break_even,
            "decision": decision,
            "score": net_spread_pct,
        })

    opps = pd.DataFrame(rows)
    return opps.sort_values("score", ascending=False).reset_index(drop=True) if not opps.empty else opps
