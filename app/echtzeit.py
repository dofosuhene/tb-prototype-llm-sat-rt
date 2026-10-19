"""Echtzeit-Updates ueber drei Wege gleichzeitig, damit sie sich direkt vergleichen lassen.

1. WebSocket (FastAPI/Starlette, RFC 6455)   Endpunkt /ws
2. Server-Sent Events (SSE, HTTP-Stream)     Endpunkt /sse
3. Socket.IO (python-socketio)               Pfad /socket.io, Event "update"

Jede Aenderung geht mit senden_an_alle() an alle drei Wege.
"""
import asyncio
import json

import socketio
from fastapi import WebSocket


class Verteiler:
    def __init__(self):
        self.websockets: list[WebSocket] = []
        self.sse_queues: list[asyncio.Queue] = []
        self.sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

    # ---------- WebSocket ----------
    async def verbinden(self, ws: WebSocket):
        await ws.accept()
        self.websockets.append(ws)

    def trennen(self, ws: WebSocket):
        if ws in self.websockets:
            self.websockets.remove(ws)

    # ---------- SSE ----------
    def sse_anmelden(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.sse_queues.append(q)
        return q

    def sse_abmelden(self, q: asyncio.Queue):
        if q in self.sse_queues:
            self.sse_queues.remove(q)

    @staticmethod
    def sse_format(nachricht: dict) -> str:
        return f"data: {json.dumps(nachricht, ensure_ascii=False)}\n\n"

    # ---------- an alle ----------
    async def senden_an_alle(self, nachricht: dict):
        for ws in list(self.websockets):
            try:
                await ws.send_json(nachricht)
            except Exception:       # Verbindung schon weg
                self.trennen(ws)
        for q in list(self.sse_queues):
            q.put_nowait(nachricht)
        await self.sio.emit(nachricht.get("typ", "update"), nachricht)


# Alter Name, damit bestehender Code weiter funktioniert
ConnectionManager = Verteiler
