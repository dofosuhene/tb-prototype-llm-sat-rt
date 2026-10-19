"""Vergleich Echtzeit-Technologien: WebSocket, Server-Sent Events (SSE) und Socket.IO.

Startet den Prototyp als eigenen Prozess, verbindet je einen Client ueber alle drei Wege
und loest danach N Testnachrichten aus (POST /vergleich/ping). Gemessen wird pro Weg:
  - Verbindungsaufbau bis zur ersten Nachricht
  - Latenz vom Ausloesen bis zum Eintreffen (Median, 95. Perzentil)
  - verlorene Nachrichten

Aufruf (im Ordner taskbuddy-prototyp): python -m vergleich.echtzeit [anzahl]
Ergebnis: vergleich/ergebnisse_echtzeit.csv und eine Zusammenfassung auf der Konsole.
"""
import asyncio
import csv
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx
import socketio
import websockets

PORT = 8765
BASIS = f"http://127.0.0.1:{PORT}"
HIER = Path(__file__).parent


def server_starten() -> subprocess.Popen:
    env = dict(os.environ, DATENBANK_URL="sqlite://")
    env.pop("OPENAI_API_KEY", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:asgi", "--port", str(PORT), "--log-level", "warning"],
        cwd=HIER.parent, env=env)
    for _ in range(100):
        try:
            httpx.get(f"{BASIS}/zustand", timeout=0.5)
            return proc
        except httpx.HTTPError:
            time.sleep(0.1)
    proc.terminate()
    raise RuntimeError("Server startet nicht")


async def messen(anzahl: int):
    ankunft = {w: {} for w in ("WebSocket", "SSE", "Socket.IO")}
    bereit = {w: asyncio.Event() for w in ankunft}
    aufbau = {}

    def empfangen(weg, nachricht):
        if nachricht.get("typ") == "ping":
            ankunft[weg][nachricht["nr"]] = time.perf_counter()
        elif nachricht.get("typ") == "update" and not bereit[weg].is_set():
            bereit[weg].set()

    async def ws_client():
        t0 = time.perf_counter()
        async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
            async for roh in ws:
                if "WebSocket" not in aufbau:
                    aufbau["WebSocket"] = time.perf_counter() - t0
                empfangen("WebSocket", json.loads(roh))

    async def sse_client():
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=None) as c:
            async with c.stream("GET", f"{BASIS}/sse") as r:
                async for zeile in r.aiter_lines():
                    if zeile.startswith("data: "):
                        if "SSE" not in aufbau:
                            aufbau["SSE"] = time.perf_counter() - t0
                        empfangen("SSE", json.loads(zeile[6:]))

    sio = socketio.AsyncClient()

    @sio.on("update")
    async def _upd(daten):
        if "Socket.IO" not in aufbau:
            aufbau["Socket.IO"] = time.perf_counter() - t_sio
        empfangen("Socket.IO", daten)

    @sio.on("ping")
    async def _ping(daten):
        empfangen("Socket.IO", daten)

    tasks = [asyncio.create_task(ws_client()), asyncio.create_task(sse_client())]
    t_sio = time.perf_counter()
    await sio.connect(BASIS, transports=["websocket"])
    await asyncio.wait_for(asyncio.gather(*(e.wait() for e in bereit.values())), timeout=10)

    gesendet = {}
    async with httpx.AsyncClient() as c:
        for nr in range(anzahl):
            gesendet[nr] = time.perf_counter()
            await c.post(f"{BASIS}/vergleich/ping", params={"nr": nr})
            await asyncio.sleep(0.02)
    await asyncio.sleep(1.0)

    await sio.disconnect()
    for t in tasks:
        t.cancel()

    zeilen = []
    for weg, werte in ankunft.items():
        lat = sorted((werte[nr] - gesendet[nr]) * 1000 for nr in werte)
        verloren = anzahl - len(lat)
        median = statistics.median(lat) if lat else float("nan")
        p95 = lat[int(0.95 * (len(lat) - 1))] if lat else float("nan")
        zeilen.append([weg, anzahl, len(lat), verloren, f"{aufbau.get(weg, float('nan')) * 1000:.1f}",
                       f"{median:.2f}", f"{p95:.2f}"])
    return zeilen


def main():
    anzahl = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    proc = server_starten()
    try:
        zeilen = asyncio.run(messen(anzahl))
    finally:
        proc.terminate()
        proc.wait()
    kopf = ["weg", "gesendet", "empfangen", "verloren", "aufbau_ms", "latenz_median_ms", "latenz_p95_ms"]
    with open(HIER / "ergebnisse_echtzeit.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(kopf)
        w.writerows(zeilen)
    print(f"{'Weg':10} {'empf.':>6} {'verl.':>6} {'Aufbau ms':>10} {'Median ms':>10} {'p95 ms':>8}")
    for z in zeilen:
        print(f"{z[0]:10} {z[2]:>6} {z[3]:>6} {z[4]:>10} {z[5]:>10} {z[6]:>8}")


if __name__ == "__main__":
    main()
