from __future__ import annotations
import requests
from .config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def send(msg: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10,
        )
        return r.ok
    except Exception:
        return False
