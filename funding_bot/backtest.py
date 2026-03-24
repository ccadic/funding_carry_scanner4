from __future__ import annotations
import argparse, pandas as pd
from .exchange_factory import get_exchange
from .utils import safe_to_csv

def fetch_history_frame(exchange_id, symbol, limit):
    exchange = get_exchange(exchange_id)
    hist = exchange.fetch_funding_rate_history(symbol, limit=limit)
    df = pd.DataFrame(hist)
    if df.empty:
        return df
    df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
    return df.dropna(subset=["fundingRate"]).reset_index(drop=True)

def run_backtest(exchange_id, symbol, mode, limit, fee_total_pct, slippage_pct, min_spread, min_net_spread_pct, auto_close_min_net_spread_pct):
    df = fetch_history_frame(exchange_id, symbol, limit)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    trades = []; equity = 1.0; position_open = False
    for i in range(20, len(df)):
        rate = float(df.iloc[i]["fundingRate"])
        spread_pct_cycle = rate * 100 if mode == "spot_perp" else abs(rate) * 100
        cost_total_pct = fee_total_pct + slippage_pct
        net_spread_pct = spread_pct_cycle - cost_total_pct
        if not position_open and rate >= min_spread and net_spread_pct >= min_net_spread_pct:
            position_open = True
            trades.append({"action":"open","index":i,"symbol":symbol,"mode":mode,"funding_rate":rate,"spread_pct_cycle":spread_pct_cycle,"net_spread_pct":net_spread_pct})
            continue
        if position_open and net_spread_pct <= auto_close_min_net_spread_pct:
            pnl = net_spread_pct / 100.0
            equity *= (1.0 + pnl)
            trades.append({"action":"close","index":i,"symbol":symbol,"mode":mode,"funding_rate":rate,"spread_pct_cycle":spread_pct_cycle,"net_spread_pct":net_spread_pct,"reason":"auto_close_simulated","equity":equity})
            position_open = False
    return pd.DataFrame([{"symbol":symbol,"exchange_id":exchange_id,"mode":mode,"rows":len(df),"trades":len(trades),"ending_equity":equity}]), pd.DataFrame(trades)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--exchange", required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--mode", choices=["perp_perp","spot_perp"], default="perp_perp")
    p.add_argument("--limit", type=int, default=300)
    p.add_argument("--fee-total-pct", type=float, default=0.10)
    p.add_argument("--slippage-pct", type=float, default=0.03)
    p.add_argument("--min-spread", type=float, default=0.0003)
    p.add_argument("--min-net-spread-pct", type=float, default=0.02)
    p.add_argument("--auto-close-min-net-spread-pct", type=float, default=-0.05)
    p.add_argument("--out", default="data/backtest_results.csv")
    p.add_argument("--trades-out", default="data/backtest_trades.csv")
    a = p.parse_args()
    results, trades = run_backtest(a.exchange, a.symbol, a.mode, a.limit, a.fee_total_pct, a.slippage_pct, a.min_spread, a.min_net_spread_pct, a.auto_close_min_net_spread_pct)
    safe_to_csv(results, a.out); safe_to_csv(trades, a.trades_out)
    print("Backtest terminé")
    if not results.empty:
        print(results.to_dict(orient="records")[0])

if __name__ == "__main__":
    main()
