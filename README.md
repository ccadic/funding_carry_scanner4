# Funding Carry V4.4.3

Version complète avec :
- calibration automatique du slippage réel
- adaptation dynamique des frais par exchange
- dashboard aussi détaillé que la V4.4.2
- bot live / dry-run
- auto-close
- funding sniper
- websocket live
- scan multi-thread
- backtest multi-mode

## Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Lancer
```bash
python ws_server.py
python run_bot.py
streamlit run funding_carry_app.py
```

## Backtest
```bash
python -m funding_bot.backtest --exchange binance --symbol BTC/USDT:USDT --mode perp_perp --limit 300
```

## Nouvelles données
- `data/slippage_log.csv`
- `data/fee_log.csv`
- coûts dynamiques par route dans le tableau des opportunités
