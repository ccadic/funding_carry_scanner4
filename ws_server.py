from __future__ import annotations
import asyncio
from collections import deque
from websockets.server import serve

CLIENTS = set()
RECENT = deque(maxlen=200)

async def handler(websocket):
    CLIENTS.add(websocket)
    try:
        for item in RECENT:
            await websocket.send(item)
        async for message in websocket:
            RECENT.append(message)
            dead = []
            for client in CLIENTS:
                if client == websocket:
                    continue
                try:
                    await client.send(message)
                except Exception:
                    dead.append(client)
            for client in dead:
                CLIENTS.discard(client)
    finally:
        CLIENTS.discard(websocket)

async def main():
    async with serve(handler, "0.0.0.0", 8765):
        print("Websocket server listening on ws://0.0.0.0:8765")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
