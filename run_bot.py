from __future__ import annotations
import time
from datetime import datetime, timezone

from funding_bot.config import (
    MIN_SPREAD,
    DEFAULT_TAKER_FEE_PCT,
    DEFAULT_SLIPPAGE_PCT,
    MIN_NET_SPREAD_PCT,
    SCAN_INTERVAL_SECONDS,
    DATA_DIR,
    COOLDOWN_SECONDS,
    ONLY_EXECUTABLE,
    DEFAULT_HISTORY_LIMIT,
    SNIPER_ENABLED,
)
from funding_bot.utils import ensure_data_dir, now_iso, load_json, save_json
from funding_bot.scanner import scan_market
from funding_bot.strategy import build_opportunities
from funding_bot.executor import execute_pair_trade, close_position_trade
from funding_bot.telegram import send
from funding_bot.logger import (
    log_scan, log_opportunities, append_trade, append_pnl_snapshot,
    log_portfolio_positions, append_sniper_action, save_state,
    append_latency_metrics, append_slippage_log, append_fee_log,
)
from funding_bot.portfolio_engine import PortfolioEngine
from funding_bot.pnl_tracker import build_live_pnl_snapshot
from funding_bot.funding_sniper import evaluate_sniper_actions
from funding_bot.live_bus import publish_event

def utc_now():
    return datetime.now(timezone.utc)

def parse_iso_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None

def load_live_state():
    state = load_json(f"{DATA_DIR}/live_state.json", default={})
    return state or {}

def save_live_state(state):
    save_json(state, f"{DATA_DIR}/live_state.json")

def cooldown_active(state, cooldown_seconds):
    last_opened_at = parse_iso_dt(state.get("last_opened_at"))
    if last_opened_at is None:
        return False, 0.0
    elapsed = (utc_now() - last_opened_at).total_seconds()
    remaining = cooldown_seconds - elapsed
    return remaining > 0, max(0.0, remaining)

def main():
    ensure_data_dir(DATA_DIR)
    portfolio = PortfolioEngine(DATA_DIR)
    print("Funding Carry V4.4.3 bot lancé")
    publish_event({"type":"bot_started","ts":now_iso(),"message":"bot started"})

    while True:
        started = now_iso()
        state = load_live_state()
        try:
            scan_df, latency_df = scan_market(history_limit=DEFAULT_HISTORY_LIMIT, return_latency=True)
            append_latency_metrics(latency_df, DATA_DIR)
            if scan_df.empty:
                save_state({"status":"scan_vide","last_run":started}, DATA_DIR)
                save_live_state({**state,"status":"scan_vide","last_run":started})
                publish_event({"type":"scan_empty","ts":started})
                time.sleep(SCAN_INTERVAL_SECONDS); continue

            log_scan(scan_df, DATA_DIR)

            opps_df = build_opportunities(
                scan_df=scan_df,
                min_spread=MIN_SPREAD,
                taker_fee_pct=DEFAULT_TAKER_FEE_PCT,
                slippage_pct=DEFAULT_SLIPPAGE_PCT,
                min_net_spread_pct=MIN_NET_SPREAD_PCT,
            )

            if ONLY_EXECUTABLE and not opps_df.empty:
                opps_df = opps_df[opps_df["decision"] == "Exploitable"].copy()

            if not opps_df.empty:
                opps_df = portfolio.rank_and_allocate(opps_df)

            log_opportunities(opps_df, DATA_DIR)

            close_actions = portfolio.evaluate_close_actions(opps_df)
            for action in close_actions:
                trade_close = close_position_trade(action)
                append_trade({
                    **trade_close,
                    "decision":"auto_close",
                    "spread_pct_cycle":action.get("spread_pct_cycle"),
                    "net_spread_pct":action.get("net_spread_pct"),
                    "close_reason":action.get("reason"),
                }, DATA_DIR)
                portfolio.close_position_from_action(action)
                publish_event({"type":"position_closed","ts":now_iso(),"symbol":action.get("symbol"),"reason":action.get("reason")})

            pnl_df = build_live_pnl_snapshot(portfolio.positions_df(), scan_df)
            append_pnl_snapshot(pnl_df, DATA_DIR)

            if SNIPER_ENABLED:
                sniper_actions = evaluate_sniper_actions(portfolio.positions_df(), opps_df)
                for action in sniper_actions:
                    append_sniper_action(action, DATA_DIR)
                    publish_event({"type":"sniper_action","ts":now_iso(), **action})

            if opps_df.empty:
                log_portfolio_positions(portfolio.positions_df(), DATA_DIR)
                save_live_state({**state,"status":"no_exploitable_opportunity","last_run":started})
                save_state({"status":"no_exploitable_opportunity","last_run":started}, DATA_DIR)
                publish_event({"type":"no_opportunity","ts":started})
                time.sleep(SCAN_INTERVAL_SECONDS); continue

            best_candidates = portfolio.select_open_candidates(opps_df)
            opened_any = False

            for _, best_row in best_candidates.iterrows():
                best = best_row.to_dict()

                if portfolio.same_position_open(best):
                    publish_event({"type":"same_trade_skipped","ts":now_iso(),"symbol":best.get("symbol"),"route":best.get("route_label")})
                    continue

                is_cd, remaining = cooldown_active(state, COOLDOWN_SECONDS)
                if is_cd:
                    save_live_state({**state,"status":"cooldown_skipped","last_run":started,"best_symbol":best["symbol"],"best_score":best["score"],"cooldown_remaining_seconds":round(remaining,2)})
                    publish_event({"type":"cooldown_skipped","ts":now_iso(),"symbol":best["symbol"],"remaining":round(remaining,2)})
                    break

                msg = (
                    f"🔥 Funding Carry V4.4.3\n"
                    f"Mode: {best['leg_mode']}\n"
                    f"Symbol: {best['symbol']}\n"
                    f"Spread/cycle: {best['spread_pct_cycle']:.4f}%\n"
                    f"Fee total: {best.get('fee_total_pct', 0):.4f}%\n"
                    f"Slippage estimé: {best.get('slippage_estimated_pct', 0):.4f}%\n"
                    f"Net estimé: {best['net_spread_pct']:.4f}%\n"
                    f"Route: {best.get('route_label', 'n/a')}"
                )
                print("\n" + msg + "\n")
                send(msg)

                trade = execute_pair_trade(best)
                trade.update({
                    "spread_pct_cycle":best["spread_pct_cycle"],
                    "net_spread_pct":best["net_spread_pct"],
                    "decision":best["decision"],
                    "alloc_pct":best.get("alloc_pct"),
                    "sniper_tag":best.get("sniper_tag"),
                    "leg_mode":best.get("leg_mode"),
                    "route_label":best.get("route_label"),
                    "fee_total_pct":best.get("fee_total_pct"),
                    "slippage_estimated_pct":best.get("slippage_estimated_pct"),
                    "cost_total_pct":best.get("cost_total_pct"),
                })
                append_trade(trade, DATA_DIR)

                # log frais dynamiques
                append_fee_log({
                    "symbol": best["symbol"],
                    "leg_mode": best.get("leg_mode"),
                    "route_label": best.get("route_label"),
                    "fee_open_pct": best.get("fee_open_pct"),
                    "fee_close_pct": best.get("fee_close_pct"),
                    "fee_total_pct": best.get("fee_total_pct"),
                }, DATA_DIR)

                # log slippage calibré / observé (ici observé = expected==executed en dry-run)
                exp1 = float(trade.get("expected_price_leg1", 0) or 0)
                exe1 = float(trade.get("executed_price_leg1", exp1) or exp1)
                exp2 = float(trade.get("expected_price_leg2", 0) or 0)
                exe2 = float(trade.get("executed_price_leg2", exp2) or exp2)

                if exp1 > 0:
                    append_slippage_log({
                        "exchange": best.get("entry_exchange") or best.get("long_exchange"),
                        "symbol": best["symbol"],
                        "side": "leg1",
                        "usd_size": trade.get("usd_size"),
                        "expected_price": exp1,
                        "executed_price": exe1,
                        "slippage_pct": abs(exe1-exp1)/exp1*100.0,
                        "mode": best.get("leg_mode"),
                    }, DATA_DIR)
                if exp2 > 0:
                    append_slippage_log({
                        "exchange": best.get("hedge_exchange") or best.get("short_exchange"),
                        "symbol": best["symbol"],
                        "side": "leg2",
                        "usd_size": trade.get("usd_size"),
                        "expected_price": exp2,
                        "executed_price": exe2,
                        "slippage_pct": abs(exe2-exp2)/exp2*100.0,
                        "mode": best.get("leg_mode"),
                    }, DATA_DIR)

                portfolio.open_position(best, trade)
                opened_any = True

                save_live_state({
                    "status":"trade_logged",
                    "last_run":now_iso(),
                    "best_symbol":best["symbol"],
                    "best_score":best["score"],
                    "position_status":"open",
                    "open_symbol":best["symbol"],
                    "last_opened_at":now_iso(),
                    "last_signal_spread_pct_cycle":best["spread_pct_cycle"],
                    "last_signal_net_spread_pct":best["net_spread_pct"],
                    "last_decision":best["decision"],
                    "leg_mode":best.get("leg_mode"),
                    "route_label":best.get("route_label"),
                })
                publish_event({"type":"position_opened","ts":now_iso(),"symbol":best["symbol"],"mode":best.get("leg_mode"),"route":best.get("route_label"),"net_spread_pct":best.get("net_spread_pct")})

            log_portfolio_positions(portfolio.positions_df(), DATA_DIR)
            portfolio_df = portfolio.positions_df()
            save_state({
                "status":"trade_logged" if opened_any else "same_trade_skipped",
                "last_run":started,
                "open_positions":int((portfolio_df["status"]=="open").sum()) if not portfolio_df.empty and "status" in portfolio_df.columns else 0,
                "closed_positions":int((portfolio_df["status"]=="closed").sum()) if not portfolio_df.empty and "status" in portfolio_df.columns else 0,
            }, DATA_DIR)
            publish_event({"type":"cycle_complete","ts":now_iso(),"opened_any":opened_any})
        except KeyboardInterrupt:
            print("Arrêt demandé par l'utilisateur")
            break
        except Exception as exc:
            err = f"Erreur bot: {type(exc).__name__}: {exc}"
            print(err)
            send(f"⚠️ {err}")
            current_state = load_live_state()
            save_live_state({**current_state,"status":"error","last_run":started,"last_error":err})
            publish_event({"type":"error","ts":now_iso(),"error":err})
        time.sleep(SCAN_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
