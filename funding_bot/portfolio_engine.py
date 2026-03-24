from __future__ import annotations
import pandas as pd
from pathlib import Path
from .config import DATA_DIR, POSITION_SIZE_USD, MAX_CONCURRENT_POSITIONS, MAX_ALLOC_PCT_PER_TRADE, MIN_SCORE_TO_ALLOCATE, AUTO_CLOSE_ENABLED, AUTO_CLOSE_MIN_NET_SPREAD_PCT, AUTO_CLOSE_MAX_RANK, AUTO_CLOSE_ON_SIGNAL_DEGRADATION
from .utils import load_json, save_json

class PortfolioEngine:
    def __init__(self, data_dir=DATA_DIR):
        self.data_dir = data_dir
        self.state_path = Path(data_dir) / "portfolio_state.json"
        self.state = load_json(self.state_path, default={"positions":[]}) or {"positions":[]}

    def save(self):
        save_json(self.state, self.state_path)

    def positions_df(self):
        pos = self.state.get("positions",[])
        return pd.DataFrame(pos) if pos else pd.DataFrame()

    def same_position_open(self, best):
        for pos in self.state.get("positions",[]):
            if pos.get("status") != "open" or pos.get("symbol") != best.get("symbol") or pos.get("leg_mode") != best.get("leg_mode"):
                continue
            if best.get("leg_mode") == "spot_perp":
                if pos.get("entry_exchange") == best.get("entry_exchange") and pos.get("hedge_exchange") == best.get("hedge_exchange"):
                    return True
            else:
                if pos.get("long_exchange") == best.get("long_exchange") and pos.get("short_exchange") == best.get("short_exchange"):
                    return True
        return False

    def rank_and_allocate(self, opps_df):
        if opps_df.empty:
            return opps_df.copy()
        df = opps_df.copy()
        df = df[df["score"] >= MIN_SCORE_TO_ALLOCATE].copy()
        if df.empty:
            return df
        ps = df["score"].clip(lower=0)
        df["alloc_pct"] = 0.0 if ps.sum() <= 0 else (ps / ps.sum()) * 100.0
        df["alloc_pct"] = df["alloc_pct"].clip(upper=MAX_ALLOC_PCT_PER_TRADE)
        df["usd_size"] = (df["alloc_pct"] / 100.0) * (POSITION_SIZE_USD * MAX_CONCURRENT_POSITIONS)
        df["sniper_tag"] = df["days_break_even"].apply(lambda x: "sniper_preferred" if pd.notna(x) and x < 2 else "normal")
        df["rank"] = range(1, len(df)+1)
        return df.sort_values(["decision","score"], ascending=[True,False]).reset_index(drop=True)

    def select_open_candidates(self, opps_df):
        if opps_df.empty:
            return opps_df
        current_open = len([p for p in self.state.get("positions",[]) if p.get("status") == "open"])
        remaining_slots = max(0, MAX_CONCURRENT_POSITIONS - current_open)
        return opps_df.head(remaining_slots) if remaining_slots > 0 else opps_df.head(0)

    def open_position(self, best, trade):
        pos = {
            "status":"open","leg_mode":best.get("leg_mode"),"symbol":best["symbol"],
            "long_exchange":best.get("long_exchange"),"short_exchange":best.get("short_exchange"),
            "entry_exchange":best.get("entry_exchange"),"hedge_exchange":best.get("hedge_exchange"),
            "route_label":best.get("route_label"),"amount":trade.get("amount"),"usd_size":trade.get("usd_size"),
            "alloc_pct":best.get("alloc_pct"),"spread_pct_cycle":best.get("spread_pct_cycle"),
            "net_spread_pct":best.get("net_spread_pct"),"rank_at_open":best.get("rank"),
            "sniper_tag":best.get("sniper_tag"),"opened_at":trade.get("logged_at"),
            "fee_total_pct": best.get("fee_total_pct"), "slippage_estimated_pct": best.get("slippage_estimated_pct"),
            "cost_total_pct": best.get("cost_total_pct"),
        }
        self.state.setdefault("positions",[]).append(pos)
        self.save()

    def close_position_from_action(self, action):
        for pos in self.state.get("positions",[]):
            if pos.get("status") != "open" or pos.get("symbol") != action.get("symbol") or pos.get("leg_mode") != action.get("leg_mode"):
                continue
            if pos.get("leg_mode") == "spot_perp":
                if pos.get("entry_exchange") != action.get("entry_exchange") or pos.get("hedge_exchange") != action.get("hedge_exchange"):
                    continue
            else:
                if pos.get("long_exchange") != action.get("long_exchange") or pos.get("short_exchange") != action.get("short_exchange"):
                    continue
            pos["status"] = "closed"
            pos["close_reason"] = action.get("reason","manual")
        self.save()

    def evaluate_close_actions(self, opps_df):
        if not AUTO_CLOSE_ENABLED:
            return []
        positions = self.positions_df()
        if positions.empty:
            return []
        actions = []
        for _, pos in positions.iterrows():
            if pos.get("status") != "open":
                continue
            symbol = pos.get("symbol"); mode = pos.get("leg_mode")
            current_rows = opps_df[(opps_df["symbol"] == symbol) & (opps_df["leg_mode"] == mode)] if not opps_df.empty else pd.DataFrame()
            if current_rows.empty:
                actions.append({**pos.to_dict(), "reason":"signal_disappeared"}); continue
            row = current_rows.iloc[0].to_dict()
            if row.get("net_spread_pct",0) < AUTO_CLOSE_MIN_NET_SPREAD_PCT:
                actions.append({**pos.to_dict(),"net_spread_pct":row.get("net_spread_pct"),"spread_pct_cycle":row.get("spread_pct_cycle"),"reason":"net_spread_below_threshold"}); continue
            if AUTO_CLOSE_ON_SIGNAL_DEGRADATION and row.get("rank",9999) > AUTO_CLOSE_MAX_RANK:
                actions.append({**pos.to_dict(),"net_spread_pct":row.get("net_spread_pct"),"spread_pct_cycle":row.get("spread_pct_cycle"),"reason":"rank_degradation"})
        return actions
