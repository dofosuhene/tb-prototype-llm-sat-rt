"""TaskBuddy-Prototyp: Freitext -> LLM -> Datenbank -> CP-SAT -> WebSocket -> Browser.

Start: uvicorn app.main:asgi --reload   (dann http://localhost:8000 und /docs)
"asgi" enthaelt die FastAPI-App und zusaetzlich Socket.IO unter /socket.io.
"""
import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import socketio
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import planer
from .config import LERNMINUTEN, MAX_TEXTLAENGE, fach_normalisieren
from .datum import aufloesen
from .db import Base, Eintrag, Lernblock, SessionLocal, engine
from .echtzeit import ConnectionManager
from .llm import Extraktor, extraktor_waehlen


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="TaskBuddy Prototyp", lifespan=lifespan)
manager = ConnectionManager()
_extraktor: Extraktor | None = None
_letzter_plan = {"status": "leer", "max_tageslast_min": None, "zu_knapp": []}


# ---------- Abhaengigkeiten (in Tests austauschbar) ----------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_jetzt() -> datetime:
    return datetime.now()


def get_extraktor() -> Extraktor:
    global _extraktor
    if _extraktor is None:
        _extraktor = extraktor_waehlen()
    return _extraktor


# ---------- Hilfsfunktionen ----------

def readiness(e: Eintrag) -> dict:
    """Readiness = erledigte Lernminuten / geplanter Lernaufwand (0 bis 1)."""
    erledigt = sum(b.minuten for b in e.bloecke if b.erledigt)
    return {"erledigt_min": erledigt, "lernminuten": e.lernminuten,
            "score": round(min(1.0, erledigt / e.lernminuten), 2) if e.lernminuten else 1.0}


def zustand(db: Session) -> dict:
    eintraege = db.scalars(select(Eintrag).order_by(Eintrag.termin)).all()
    bloecke = db.scalars(select(Lernblock).order_by(Lernblock.start)).all()
    return {
        "eintraege": [{"id": e.id, "typ": e.typ, "fach": e.fach, "titel": e.titel,
                       "termin": e.termin.isoformat(), **readiness(e)} for e in eintraege],
        "bloecke": [{"id": b.id, "eintrag_id": b.eintrag_id, "fach": b.eintrag.fach, "titel": b.eintrag.titel,
                     "start": b.start.isoformat(), "ende": b.ende.isoformat(), "erledigt": b.erledigt}
                    for b in bloecke],
        "plan": _letzter_plan,
    }


async def neu_planen(db: Session, jetzt: datetime) -> dict:
    """Offene Lernzeit aller kuenftigen Eintraege neu verteilen. Erledigte Bloecke bleiben stehen.
    Ist der neue Plan unloesbar, bleibt der alte Plan bestehen."""
    eintraege = db.scalars(select(Eintrag).where(Eintrag.termin > jetzt)).all()
    aufgaben = [planer.Aufgabe(e.id, e.fach, e.lernminuten - readiness(e)["erledigt_min"], e.termin)
                for e in eintraege]
    # Solver in eigenem Thread, damit der Server waehrenddessen erreichbar bleibt
    ergebnis = await asyncio.to_thread(planer.planen, aufgaben, jetzt)

    if ergebnis.status in ("optimal", "gueltig", "leer"):
        for b in db.scalars(select(Lernblock).where(Lernblock.erledigt.is_(False))).all():
            db.delete(b)
        for b in ergebnis.bloecke:
            db.add(Lernblock(eintrag_id=b.aufgabe_id, start=b.start, ende=b.ende))
        db.commit()

    _letzter_plan.update(status=ergebnis.status, max_tageslast_min=ergebnis.max_tageslast_min,
                         zu_knapp=ergebnis.zu_knapp)
    daten = zustand(db)
    await manager.senden_an_alle({"typ": "update", **daten})
    return daten


# ---------- Endpunkte ----------

class FreitextAnfrage(BaseModel):
    text: str = Field(min_length=2, max_length=MAX_TEXTLAENGE)


RUECKFRAGEN = {
    "fach": "Für welches Fach ist das?",
    "typ": "Ist das eine Aufgabe oder eine Prüfung?",
    "termin": "Bis wann ist das? (z. B. „bis Freitag“ oder „am 14.11.“)",
}


@app.post("/freitext")
async def freitext(anfrage: FreitextAnfrage, db: Session = Depends(get_db),
                   jetzt: datetime = Depends(get_jetzt), extraktor: Extraktor = Depends(get_extraktor)):
    try:
        x = await extraktor.extrahieren(anfrage.text)
    except Exception as fehler:
        # Genaue Ursache in die Konsole, z. B. insufficient_quota (kein Guthaben) oder rate_limit_exceeded
        code = getattr(fehler, "code", None)
        print(f"LLM-Fehler: {type(fehler).__name__} code={code}: {fehler}")
        raise HTTPException(502, f"Sprachmodell nicht erreichbar oder Antwort ungültig: {type(fehler).__name__}"
                                 + (f" ({code})" if code else ""))

    if not x.is_relevant:
        return {"status": "irrelevant", "meldung": "Das sieht nicht nach einer Aufgabe oder Prüfung aus."}

    # Fehlende Angaben selbst pruefen, nicht nur dem LLM glauben
    fach = fach_normalisieren(x.subject)
    termin = aufloesen(x.raw_date_expression, jetzt)
    fehlend = [n for n, v in (("typ", x.entry_type), ("fach", fach), ("termin", termin)) if v is None]
    if fehlend:
        return {"status": "rueckfrage", "fehlend": fehlend, "frage": " ".join(RUECKFRAGEN[f] for f in fehlend),
                "erkannt": x.model_dump()}
    if termin <= jetzt:
        return {"status": "rueckfrage", "fehlend": ["termin"], "frage": "Dieser Termin liegt in der Vergangenheit. Bis wann ist das?",
                "erkannt": x.model_dump()}

    e = Eintrag(typ=x.entry_type, fach=fach, titel=(x.title or anfrage.text)[:200], termin=termin,
                lernminuten=LERNMINUTEN[x.entry_type])
    db.add(e)
    db.commit()
    daten = await neu_planen(db, jetzt)
    return {"status": "gespeichert", "eintrag_id": e.id, "plan": daten["plan"], "erkannt": x.model_dump()}


@app.get("/zustand")
def zustand_lesen(db: Session = Depends(get_db)):
    return zustand(db)


@app.post("/plan")
async def plan_neu(db: Session = Depends(get_db), jetzt: datetime = Depends(get_jetzt)):
    return await neu_planen(db, jetzt)


@app.post("/lernbloecke/{block_id}/erledigt")
async def block_erledigt(block_id: int, db: Session = Depends(get_db)):
    b = db.get(Lernblock, block_id)
    if b is None:
        raise HTTPException(404, "Lernblock nicht gefunden")
    b.erledigt = not b.erledigt          # nochmal klicken macht es rueckgaengig
    db.commit()
    daten = zustand(db)
    await manager.senden_an_alle({"typ": "update", **daten})
    return {"id": b.id, "erledigt": b.erledigt}


@app.delete("/eintraege/{eintrag_id}")
async def eintrag_loeschen(eintrag_id: int, db: Session = Depends(get_db), jetzt: datetime = Depends(get_jetzt)):
    e = db.get(Eintrag, eintrag_id)
    if e is None:
        raise HTTPException(404, "Eintrag nicht gefunden")
    db.delete(e)
    db.commit()
    await neu_planen(db, jetzt)
    return {"geloescht": eintrag_id}


@app.get("/readiness")
def readiness_lesen(db: Session = Depends(get_db)):
    return [{"id": e.id, "fach": e.fach, "titel": e.titel, **readiness(e)}
            for e in db.scalars(select(Eintrag).order_by(Eintrag.termin)).all()]


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await manager.verbinden(ws)
    db = SessionLocal()
    try:
        await ws.send_json({"typ": "update", **zustand(db)})
        while True:
            await ws.receive_text()      # Client sendet nichts Wichtiges, wir halten nur die Verbindung
    except WebSocketDisconnect:
        manager.trennen(ws)
    finally:
        db.close()


@app.get("/sse")
async def sse(request: Request):
    """Server-Sent Events: gleiche Nachrichten wie /ws, aber nur vom Server zum Client."""
    q = manager.sse_anmelden()
    db = SessionLocal()
    start = {"typ": "update", **zustand(db)}
    db.close()

    async def strom():
        try:
            yield manager.sse_format(start)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    nachricht = await asyncio.wait_for(q.get(), timeout=15)
                    yield manager.sse_format(nachricht)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            manager.sse_abmelden(q)

    return StreamingResponse(strom(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@manager.sio.event
async def connect(sid, environ):
    db = SessionLocal()
    try:
        await manager.sio.emit("update", {"typ": "update", **zustand(db)}, to=sid)
    finally:
        db.close()


@app.post("/vergleich/ping", tags=["vergleich"])
async def vergleich_ping(nr: int = 0):
    """Schickt eine Testnachricht mit Zeitstempel ueber WebSocket, SSE und Socket.IO.
    Wird von vergleich/echtzeit.py zur Messung der Latenz verwendet."""
    await manager.senden_an_alle({"typ": "ping", "nr": nr, "t": time.perf_counter()})
    return {"gesendet": nr, "websocket": len(manager.websockets),
            "sse": len(manager.sse_queues)}


@app.get("/", include_in_schema=False)
def startseite():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


# FastAPI + Socket.IO in einer ASGI-App (Start mit uvicorn app.main:asgi)
asgi = socketio.ASGIApp(manager.sio, other_asgi_app=app)
