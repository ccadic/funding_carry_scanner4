from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import pandas as pd
import streamlit as st

from funding_bot.config import (
    DEFAULT_HISTORY_LIMIT, MIN_SPREAD, DEFAULT_TAKER_FEE_PCT, DEFAULT_SLIPPAGE_PCT,
    MIN_NET_SPREAD_PCT, DATA_DIR, UI_AUTO_REFRESH_SECONDS
)
from funding_bot.scanner import scan_market
from funding_bot.strategy import build_opportunities
from funding_bot.utils import read_csv_if_exists
from funding_bot.fee_engine import build_fee_table_df
from funding_bot.slippage_engine import build_slippage_summary_df

APP_TITLE = "Funding Carry Scanner V4.4.3"
COOLDOWN_SECONDS_DEFAULT = 3600

def load_live_state():
    path = Path(DATA_DIR) / "live_state.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def parse_iso_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None

def format_dt(value):
    dt = parse_iso_dt(value)
    if dt is None:
        return "—"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def cooldown_remaining_seconds(state, cooldown_seconds=COOLDOWN_SECONDS_DEFAULT):
    last_opened_at = parse_iso_dt(state.get("last_opened_at"))
    if last_opened_at is None:
        return 0.0
    elapsed = (datetime.now(timezone.utc) - last_opened_at).total_seconds()
    return max(0.0, cooldown_seconds - elapsed)

def human_duration(seconds):
    seconds = int(max(0, seconds)); h = seconds // 3600; m = (seconds % 3600) // 60; s = seconds % 60
    if h > 0: return f"{h}h {m}m {s}s"
    if m > 0: return f"{m}m {s}s"
    return f"{s}s"

def render_badge(label, bg_color, text_color="#ffffff"):
    st.markdown(f'''<div style="display:inline-block;padding:0.40rem 0.85rem;border-radius:999px;background-color:{bg_color};color:{text_color};font-weight:700;font-size:0.95rem;margin-bottom:0.5rem;">{label}</div>''', unsafe_allow_html=True)

def df_to_records(df):
    if df is None or df.empty:
        return []
    safe = df.copy()
    for col in safe.columns:
        safe[col] = safe[col].astype(object).where(pd.notnull(safe[col]), None)
    return safe.to_dict(orient="records")

def records_to_df(records):
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)

st.set_page_config(page_title=APP_TITLE, layout="wide")

if "ui_params" not in st.session_state:
    st.session_state.ui_params = {
        "mode_source": "Lire les CSV du bot",
        "history_limit": DEFAULT_HISTORY_LIMIT,
        "min_spread_pct": MIN_SPREAD * 100,
        "taker_fee_pct": DEFAULT_TAKER_FEE_PCT,
        "slippage_pct": DEFAULT_SLIPPAGE_PCT,
        "min_net_spread_pct": MIN_NET_SPREAD_PCT,
        "only_exploitable": False,
        "top_n": 20,
        "cooldown_seconds": COOLDOWN_SECONDS_DEFAULT,
        "auto_refresh_enabled": True,
        "auto_refresh_seconds": UI_AUTO_REFRESH_SECONDS,
    }

if "manual_scan_requested" not in st.session_state:
    st.session_state.manual_scan_requested = False

if "local_scan_cache" not in st.session_state:
    st.session_state.local_scan_cache = {"scan": [], "opps": [], "latency": [], "last_scan_at": None}

st.title(APP_TITLE)
st.caption("V4.4.3 : calibration automatique du slippage + frais dynamiques par exchange, avec UI détaillée.")

with st.sidebar:
    st.header("Paramètres")
    with st.form("control_form", clear_on_submit=False):
        mode_source = st.radio("Source des données", ["Lire les CSV du bot", "Scanner localement"], index=0 if st.session_state.ui_params["mode_source"]=="Lire les CSV du bot" else 1)
        history_limit = st.slider("Historique (périodes funding)", 30, 300, int(st.session_state.ui_params["history_limit"]), step=10)
        min_spread_pct = st.number_input("Seuil mini spread (%)", value=float(st.session_state.ui_params["min_spread_pct"]), step=0.001, format="%.4f")
        taker_fee_pct = st.number_input("Frais taker défaut (%)", value=float(st.session_state.ui_params["taker_fee_pct"]), step=0.01, format="%.2f")
        slippage_pct = st.number_input("Slippage défaut (%)", value=float(st.session_state.ui_params["slippage_pct"]), step=0.01, format="%.2f")
        min_net_spread_pct = st.number_input("Net mini par cycle (%)", value=float(st.session_state.ui_params["min_net_spread_pct"]), step=0.001, format="%.4f")
        only_exploitable = st.checkbox("Afficher seulement 'Exploitable'", value=bool(st.session_state.ui_params["only_exploitable"]))
        top_n = st.slider("Top N", 5, 100, int(st.session_state.ui_params["top_n"]))
        cooldown_seconds = st.number_input("Cooldown affiché (secondes)", min_value=60, max_value=86400, value=int(st.session_state.ui_params["cooldown_seconds"]), step=60)
        auto_refresh_enabled = st.checkbox("Auto-refresh zone données", value=bool(st.session_state.ui_params["auto_refresh_enabled"]))
        auto_refresh_seconds = st.number_input("Période auto-refresh (secondes)", min_value=5, max_value=300, value=int(st.session_state.ui_params["auto_refresh_seconds"]), step=1)
        ca, cb = st.columns(2)
        apply_btn = ca.form_submit_button("Appliquer")
        refresh_btn = cb.form_submit_button("Scanner / Rafraîchir")
    if apply_btn or refresh_btn:
        st.session_state.ui_params.update({
            "mode_source": mode_source, "history_limit": history_limit, "min_spread_pct": min_spread_pct,
            "taker_fee_pct": taker_fee_pct, "slippage_pct": slippage_pct,
            "min_net_spread_pct": min_net_spread_pct, "only_exploitable": only_exploitable,
            "top_n": top_n, "cooldown_seconds": cooldown_seconds,
            "auto_refresh_enabled": auto_refresh_enabled, "auto_refresh_seconds": auto_refresh_seconds,
        })
        if refresh_btn:
            st.session_state.manual_scan_requested = True
            st.info("Rafraîchissement demandé")
        else:
            st.success("Paramètres sauvegardés")

def get_display_data():
    params = st.session_state.ui_params
    trades_df = read_csv_if_exists(f"{DATA_DIR}/trades.csv")
    pnl_df = read_csv_if_exists(f"{DATA_DIR}/pnl_live.csv")
    portfolio_df = read_csv_if_exists(f"{DATA_DIR}/portfolio_positions.csv")
    sniper_df = read_csv_if_exists(f"{DATA_DIR}/funding_sniper_actions.csv")
    live_feed_df = read_csv_if_exists(f"{DATA_DIR}/live_feed_snapshot.csv")
    latency_df = read_csv_if_exists(f"{DATA_DIR}/latency_metrics.csv")
    slippage_log_df = read_csv_if_exists(f"{DATA_DIR}/slippage_log.csv")
    fee_log_df = read_csv_if_exists(f"{DATA_DIR}/fee_log.csv")
    slippage_summary_df = build_slippage_summary_df(DATA_DIR)
    fee_table_df = build_fee_table_df()
    state = load_live_state()

    if params["mode_source"] == "Scanner localement":
        if st.session_state.manual_scan_requested or not st.session_state.local_scan_cache["scan"]:
            scan_df, local_latency = scan_market(history_limit=int(params["history_limit"]), return_latency=True)
            opps_df = pd.DataFrame()
            if not scan_df.empty:
                opps_df = build_opportunities(
                    scan_df=scan_df,
                    min_spread=float(params["min_spread_pct"]) / 100,
                    taker_fee_pct=float(params["taker_fee_pct"]),
                    slippage_pct=float(params["slippage_pct"]),
                    min_net_spread_pct=float(params["min_net_spread_pct"]),
                )
            st.session_state.local_scan_cache = {
                "scan": df_to_records(scan_df),
                "opps": df_to_records(opps_df),
                "latency": df_to_records(local_latency),
                "last_scan_at": format_dt(datetime.now(timezone.utc).isoformat()),
            }
            st.session_state.manual_scan_requested = False
        scan_df = records_to_df(st.session_state.local_scan_cache["scan"])
        opps_df = records_to_df(st.session_state.local_scan_cache["opps"])
        latency_df = records_to_df(st.session_state.local_scan_cache["latency"])
        last_scan_at = st.session_state.local_scan_cache["last_scan_at"]
    else:
        scan_df = read_csv_if_exists(f"{DATA_DIR}/scan_raw.csv")
        opps_df = read_csv_if_exists(f"{DATA_DIR}/opportunities.csv")
        last_scan_at = format_dt(state.get("last_run"))

    if params["only_exploitable"] and not opps_df.empty:
        opps_df = opps_df[opps_df["decision"] == "Exploitable"].copy()

    return {
        "state": state, "scan_df": scan_df, "opps_df": opps_df, "trades_df": trades_df,
        "pnl_df": pnl_df, "portfolio_df": portfolio_df, "sniper_df": sniper_df,
        "latency_df": latency_df, "live_feed_df": live_feed_df, "last_scan_at": last_scan_at,
        "slippage_log_df": slippage_log_df, "fee_log_df": fee_log_df,
        "slippage_summary_df": slippage_summary_df, "fee_table_df": fee_table_df,
    }

def render_dashboard(data):
    params = st.session_state.ui_params
    state = data["state"]; scan_df = data["scan_df"]; opps_df = data["opps_df"]; trades_df = data["trades_df"]
    pnl_df = data["pnl_df"]; portfolio_df = data["portfolio_df"]; sniper_df = data["sniper_df"]
    latency_df = data["latency_df"]; live_feed_df = data["live_feed_df"]; last_scan_at = data["last_scan_at"]
    slippage_log_df = data["slippage_log_df"]; fee_log_df = data["fee_log_df"]
    slippage_summary_df = data["slippage_summary_df"]; fee_table_df = data["fee_table_df"]

    st.subheader("État live du bot")
    badges = st.columns(6)
    with badges[0]: render_badge("OPEN" if state.get("position_status")=="open" else "NO POSITION", "#16a34a" if state.get("position_status")=="open" else "#6b7280")
    with badges[1]:
        rem = cooldown_remaining_seconds(state, int(params["cooldown_seconds"]))
        render_badge(f"COOLDOWN {human_duration(rem)}" if rem>0 else "READY", "#f59e0b" if rem>0 else "#2563eb", "#111827" if rem>0 else "#ffffff")
    with badges[2]: render_badge("ERROR" if state.get("status")=="error" or state.get("last_error") else "BOT OK", "#dc2626" if state.get("status")=="error" or state.get("last_error") else "#059669")
    with badges[3]: render_badge(state.get("leg_mode","N/A").upper(), "#7c3aed")
    with badges[4]: render_badge(state.get("route_label","ROUTE N/A"), "#374151")
    with badges[5]: render_badge("SYNCED" if not live_feed_df.empty else "FILE MODE", "#0ea5e9")

    m1,m2,m3,m4,m5,m6 = st.columns(6)
    with m1: st.metric("Paires scannées", int(scan_df["symbol"].nunique()) if not scan_df.empty and "symbol" in scan_df.columns else 0)
    with m2: st.metric("Opportunités", int(len(opps_df)))
    with m3: st.metric("Positions ouvertes", int((portfolio_df["status"]=="open").sum()) if not portfolio_df.empty and "status" in portfolio_df.columns else 0)
    with m4:
        latest_pnl = float(pnl_df["net_pnl_estimate_usd"].iloc[-1]) if not pnl_df.empty and "net_pnl_estimate_usd" in pnl_df.columns else 0.0
        st.metric("PnL live estimé (USD)", f"{latest_pnl:.2f}")
    with m5: st.metric("Dernier symbole", state.get("best_symbol","—"))
    with m6:
        avg_latency = float(latency_df["elapsed_ms"].mean()) if not latency_df.empty and "elapsed_ms" in latency_df.columns else 0.0
        st.metric("Latence moyenne scan (ms)", f"{avg_latency:.1f}")

    row_a,row_b = st.columns([2,1])
    with row_a:
        st.subheader("Portefeuille détaillé")
        st.dataframe(portfolio_df if not portfolio_df.empty else pd.DataFrame(), width="stretch")
    with row_b:
        st.subheader("Résumé exécution")
        st.write(f"Statut bot : `{state.get('status','—')}`")
        st.write(f"Dernier run bot : `{format_dt(state.get('last_run'))}`")
        st.write(f"Mode : `{state.get('leg_mode','—')}`")
        st.write(f"Route : `{state.get('route_label','—')}`")
        st.write(f"Dernière décision : `{state.get('last_decision','—')}`")
        st.write(f"Source affichée : `{params['mode_source']}`")
        st.write(f"Dernière mise à jour zone données : `{last_scan_at}`")
        if state.get("last_error"): st.error(state["last_error"])

    st.subheader("Classement détaillé des opportunités")
    if opps_df.empty:
        st.warning("Aucune opportunité disponible.")
    else:
        shown = opps_df.head(int(params["top_n"])).copy()
        display_cols = [c for c in [
            "symbol","leg_mode","route_label","long_exchange","short_exchange","entry_exchange","hedge_exchange",
            "spread_pct_cycle","fee_open_pct","fee_close_pct","fee_total_pct",
            "slippage_orderbook_pct","slippage_calibrated_pct","slippage_estimated_pct",
            "cost_total_pct","net_spread_pct","spread_pct_day","spread_pct_annual",
            "days_break_even","decision","score","alloc_pct","rank","positive_ratio","volatility_avg",
            "next_funding_long","next_funding_short"
        ] if c in shown.columns]
        st.dataframe(shown[display_cols], width="stretch")
        st.download_button("Télécharger le CSV", data=shown.to_csv(index=False).encode("utf-8"), file_name="funding_opportunities_v443.csv", mime="text/csv")
        c1,c2,c3 = st.columns(3)
        with c1:
            if "net_spread_pct" in shown.columns:
                st.markdown("**Top spreads nets**"); st.bar_chart(shown.set_index("symbol")[["net_spread_pct"]])
        with c2:
            if "cost_total_pct" in shown.columns:
                st.markdown("**Coût total estimé**"); st.bar_chart(shown.set_index("symbol")[["cost_total_pct"]])
        with c3:
            if "days_break_even" in shown.columns:
                be = shown[["symbol","days_break_even"]].dropna()
                st.markdown("**Break-even (jours)**")
                if not be.empty: st.bar_chart(be.set_index("symbol"))

    mid1,mid2 = st.columns(2)
    with mid1:
        st.subheader("PnL live")
        if pnl_df.empty: st.caption("Aucune donnée PnL.")
        else:
            st.dataframe(pnl_df.tail(50), width="stretch")
            cols = [x for x in ["net_pnl_estimate_usd","gross_pnl_estimate_usd","funding_capture_estimate_usd"] if x in pnl_df.columns]
            if cols: st.line_chart(pnl_df[cols])
    with mid2:
        st.subheader("Actions funding sniper")
        st.dataframe(sniper_df.tail(100) if not sniper_df.empty else pd.DataFrame(), width="stretch")

    low1,low2 = st.columns(2)
    with low1:
        st.subheader("Tracking latence")
        st.dataframe(latency_df.tail(100) if not latency_df.empty else pd.DataFrame(), width="stretch")
        if not latency_df.empty and "elapsed_ms" in latency_df.columns: st.line_chart(latency_df[["elapsed_ms"]])
    with low2:
        st.subheader("Live feed / sync")
        st.dataframe(live_feed_df.tail(100) if not live_feed_df.empty else pd.DataFrame(), width="stretch")

    st.subheader("Calibration slippage")
    s1,s2 = st.columns(2)
    with s1:
        st.markdown("**Résumé slippage calibré**")
        st.dataframe(slippage_summary_df.head(100) if not slippage_summary_df.empty else pd.DataFrame(), width="stretch")
    with s2:
        st.markdown("**Logs slippage récents**")
        st.dataframe(slippage_log_df.tail(100) if not slippage_log_df.empty else pd.DataFrame(), width="stretch")

    st.subheader("Frais dynamiques par exchange")
    f1,f2 = st.columns(2)
    with f1:
        st.markdown("**Table de frais de référence**")
        st.dataframe(fee_table_df if not fee_table_df.empty else pd.DataFrame(), width="stretch")
    with f2:
        st.markdown("**Logs frais appliqués**")
        st.dataframe(fee_log_df.tail(100) if not fee_log_df.empty else pd.DataFrame(), width="stretch")

    bottom1,bottom2 = st.columns(2)
    with bottom1:
        st.subheader("Vue brute par exchange")
        raw_cols = [c for c in ["exchange","symbol","funding","next_funding","short_ma","long_ma","positive_ratio","volatility","timestamp"] if c in scan_df.columns]
        st.dataframe(scan_df[raw_cols].head(300) if not scan_df.empty else pd.DataFrame(), width="stretch")
    with bottom2:
        st.subheader("Logs trades")
        st.dataframe(trades_df.tail(100) if not trades_df.empty else pd.DataFrame(), width="stretch")

    if not portfolio_df.empty and "leg_mode" in portfolio_df.columns:
        st.subheader("Répartition par mode")
        mode_counts = portfolio_df["leg_mode"].value_counts().rename_axis("leg_mode").to_frame("count")
        st.bar_chart(mode_counts)

    with st.expander("Debug live_state.json"):
        st.json(state if state else {})

if st.session_state.ui_params["auto_refresh_enabled"]:
    @st.fragment(run_every=f"{int(st.session_state.ui_params['auto_refresh_seconds'])}s")
    def render_data_zone():
        render_dashboard(get_display_data())
else:
    @st.fragment
    def render_data_zone():
        render_dashboard(get_display_data())

render_data_zone()
