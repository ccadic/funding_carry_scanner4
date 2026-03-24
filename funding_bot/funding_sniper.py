from __future__ import annotations
from datetime import datetime, timezone
from .config import SNIPER_WINDOW_BEFORE_SECONDS, SNIPER_EXIT_AFTER_SECONDS

def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except Exception:
        return None

def evaluate_sniper_actions(portfolio_df, opps_df):
    actions = []
    now = datetime.now(timezone.utc)
    if portfolio_df is not None and not portfolio_df.empty:
        for _, pos in portfolio_df.iterrows():
            if pos.get("status") != "open":
                continue
            opened_at = _parse_dt(pos.get("opened_at"))
            if opened_at is not None and (now-opened_at).total_seconds() >= SNIPER_EXIT_AFTER_SECONDS and pos.get("sniper_tag") == "sniper_preferred":
                actions.append({"action":"close","symbol":pos.get("symbol"),"leg_mode":pos.get("leg_mode"),"long_exchange":pos.get("long_exchange"),"short_exchange":pos.get("short_exchange"),"entry_exchange":pos.get("entry_exchange"),"hedge_exchange":pos.get("hedge_exchange"),"amount":pos.get("amount"),"reason":"sniper_exit_after_window","spread_pct_cycle":pos.get("spread_pct_cycle"),"net_spread_pct":pos.get("net_spread_pct")})
    if opps_df is None or opps_df.empty:
        return actions
    for _, opp in opps_df.iterrows():
        next_dt = _parse_dt(opp.get("next_funding_short")) or _parse_dt(opp.get("next_funding_long"))
        if next_dt is None:
            continue
        rem = (next_dt - now).total_seconds()
        if 0 <= rem <= SNIPER_WINDOW_BEFORE_SECONDS:
            actions.append({"action":"watch","symbol":opp.get("symbol"),"leg_mode":opp.get("leg_mode"),"long_exchange":opp.get("long_exchange"),"short_exchange":opp.get("short_exchange"),"entry_exchange":opp.get("entry_exchange"),"hedge_exchange":opp.get("hedge_exchange"),"reason":"sniper_window_before_funding","seconds_to_funding":round(rem,2),"spread_pct_cycle":opp.get("spread_pct_cycle"),"net_spread_pct":opp.get("net_spread_pct")})
    return actions
