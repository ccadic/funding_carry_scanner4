from __future__ import annotations
import asyncio, json
from pathlib import Path
import pandas as pd
import websockets
from .config import WS_ENABLED, WS_URL, DATA_DIR
from .utils import append_jsonl, safe_to_csv

LIVE_JSONL = Path(DATA_DIR) / "live_feed.jsonl"
LIVE_SNAPSHOT = Path(DATA_DIR) / "live_feed_snapshot.csv"

async def _publish_ws(payload):
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps(payload, ensure_ascii=False))

def publish_event(payload):
    append_jsonl(LIVE_JSONL, payload)
    rows = []
    if LIVE_JSONL.exists():
        with LIVE_JSONL.open("r", encoding="utf-8") as f:
            for line in f.readlines()[-200:]:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    if rows:
        safe_to_csv(pd.DataFrame(rows), LIVE_SNAPSHOT)
    if not WS_ENABLED:
        return
    try:
        asyncio.run(_publish_ws(payload))
    except Exception:
        pass
