from __future__ import annotations
import pandas as pd
from .utils import now_iso

def build_live_pnl_snapshot(portfolio_df, scan_df):
    if portfolio_df.empty:
        return pd.DataFrame([{"timestamp":now_iso(),"open_positions":0,"gross_pnl_estimate_usd":0.0,"net_pnl_estimate_usd":0.0,"funding_capture_estimate_usd":0.0}])
    gross = 0.0
    funding_capture = 0.0
    for _, pos in portfolio_df.iterrows():
        if pos.get("status") != "open":
            continue
        usd_size = float(pos.get("usd_size",0) or 0)
        spread_pct_cycle = float(pos.get("spread_pct_cycle",0) or 0)
        inc = usd_size * (spread_pct_cycle/100.0)
        funding_capture += inc
        gross += inc
    return pd.DataFrame([{"timestamp":now_iso(),"open_positions":int((portfolio_df["status"]=="open").sum()) if "status" in portfolio_df.columns else len(portfolio_df),"gross_pnl_estimate_usd":round(gross,6),"net_pnl_estimate_usd":round(gross,6),"funding_capture_estimate_usd":round(funding_capture,6)}])
