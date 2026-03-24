from __future__ import annotations
from pathlib import Path
import pandas as pd
from .utils import ensure_data_dir, safe_to_csv, now_iso, read_csv_if_exists, save_json

def log_scan(scan_df, data_dir="data"):
    ensure_data_dir(data_dir)
    return safe_to_csv(scan_df, Path(data_dir) / "scan_raw.csv")

def log_opportunities(opps_df, data_dir="data"):
    ensure_data_dir(data_dir)
    return safe_to_csv(opps_df, Path(data_dir) / "opportunities.csv")

def append_trade(trade, data_dir="data"):
    ensure_data_dir(data_dir)
    path = Path(data_dir) / "trades.csv"
    row = dict(trade); row["logged_at"] = now_iso()
    current = read_csv_if_exists(path)
    updated = pd.concat([current, pd.DataFrame([row])], ignore_index=True)
    return safe_to_csv(updated, path)

def append_pnl_snapshot(pnl_df, data_dir="data"):
    ensure_data_dir(data_dir)
    path = Path(data_dir) / "pnl_live.csv"
    current = read_csv_if_exists(path)
    updated = pd.concat([current, pnl_df], ignore_index=True) if not pnl_df.empty else current
    return safe_to_csv(updated, path)

def log_portfolio_positions(df, data_dir="data"):
    ensure_data_dir(data_dir)
    return safe_to_csv(df, Path(data_dir) / "portfolio_positions.csv")

def append_sniper_action(action, data_dir="data"):
    ensure_data_dir(data_dir)
    path = Path(data_dir) / "funding_sniper_actions.csv"
    current = read_csv_if_exists(path)
    row = dict(action); row["logged_at"] = now_iso()
    updated = pd.concat([current, pd.DataFrame([row])], ignore_index=True)
    return safe_to_csv(updated, path)

def append_latency_metrics(latency_df, data_dir="data"):
    ensure_data_dir(data_dir)
    path = Path(data_dir) / "latency_metrics.csv"
    current = read_csv_if_exists(path)
    updated = pd.concat([current, latency_df], ignore_index=True) if not latency_df.empty else current
    return safe_to_csv(updated, path)

def append_slippage_log(row, data_dir="data"):
    ensure_data_dir(data_dir)
    path = Path(data_dir) / "slippage_log.csv"
    current = read_csv_if_exists(path)
    payload = dict(row); payload["logged_at"] = now_iso()
    updated = pd.concat([current, pd.DataFrame([payload])], ignore_index=True)
    return safe_to_csv(updated, path)

def append_fee_log(row, data_dir="data"):
    ensure_data_dir(data_dir)
    path = Path(data_dir) / "fee_log.csv"
    current = read_csv_if_exists(path)
    payload = dict(row); payload["logged_at"] = now_iso()
    updated = pd.concat([current, pd.DataFrame([payload])], ignore_index=True)
    return safe_to_csv(updated, path)

def save_state(state, data_dir="data"):
    ensure_data_dir(data_dir)
    return save_json(state, Path(data_dir) / "live_state.json")
