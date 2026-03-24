from __future__ import annotations
from .config import POSITION_SIZE_USD, DRY_RUN
from .exchange_factory import get_exchange

def get_amount_from_usd(exchange, symbol, usd_size):
    ticker = exchange.fetch_ticker(symbol)
    last = ticker.get("last")
    if not last or last <= 0:
        raise ValueError(f"Prix invalide pour {symbol}")
    amount = usd_size / last
    if hasattr(exchange, "amount_to_precision"):
        try:
            amount = float(exchange.amount_to_precision(symbol, amount))
        except Exception:
            pass
    return amount, float(last)

def execute_pair_trade(best):
    usd_size = best.get("usd_size") or POSITION_SIZE_USD
    symbol = best["symbol"]
    leg_mode = best.get("leg_mode", "perp_perp")

    if leg_mode == "spot_perp":
        entry_exchange = best["entry_exchange"]
        hedge_exchange = best["hedge_exchange"]
        amount1, px1 = get_amount_from_usd(get_exchange(entry_exchange), symbol, usd_size)
        amount2, px2 = get_amount_from_usd(get_exchange(hedge_exchange), symbol, usd_size)
        amount = min(amount1, amount2)
        return {
            "action":"open","leg_mode":"spot_perp","symbol":symbol,
            "entry_exchange":entry_exchange,"hedge_exchange":hedge_exchange,
            "amount":amount,"usd_size":usd_size,"dry_run":DRY_RUN,
            "expected_price_leg1": px1, "expected_price_leg2": px2,
            "executed_price_leg1": px1, "executed_price_leg2": px2,
        }

    long_exchange = best["long_exchange"]
    short_exchange = best["short_exchange"]
    amount1, px1 = get_amount_from_usd(get_exchange(long_exchange), symbol, usd_size)
    amount2, px2 = get_amount_from_usd(get_exchange(short_exchange), symbol, usd_size)
    amount = min(amount1, amount2)
    return {
        "action":"open","leg_mode":"perp_perp","symbol":symbol,
        "long_exchange":long_exchange,"short_exchange":short_exchange,
        "amount":amount,"usd_size":usd_size,"dry_run":DRY_RUN,
        "expected_price_leg1": px1, "expected_price_leg2": px2,
        "executed_price_leg1": px1, "executed_price_leg2": px2,
    }

def close_position_trade(action):
    leg_mode = action.get("leg_mode","perp_perp")
    base = {"action":"close","leg_mode":leg_mode,"symbol":action["symbol"],"amount":action.get("amount"),"dry_run":DRY_RUN}
    if leg_mode == "spot_perp":
        base.update({"entry_exchange":action["entry_exchange"],"hedge_exchange":action["hedge_exchange"]})
    else:
        base.update({"long_exchange":action["long_exchange"],"short_exchange":action["short_exchange"]})
    return base
