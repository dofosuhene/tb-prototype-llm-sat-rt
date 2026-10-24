"""Lernbloecke mit OR-Tools CP-SAT planen (Modell aus der Vorstudie, auf echte Datumswerte erweitert).

Reine Funktion ohne Datenbank: Aufgaben rein, Lernbloecke raus. So laesst sie sich
einzeln testen und spaeter in einem eigenen Thread oder Worker ausfuehren.

Regeln:
  - Bloecke liegen nur in Lernfenstern (freie Zeit oder Lernbuero)
  - in einer Lernbuero-Stunde wird genau ein angebotenes Fach gelernt
  - Bloecke ueberschneiden sich nicht
  - jeder Block endet mindestens PUFFER_MIN vor dem Termin
Ziel: die hoechste Tagesbelastung so klein wie moeglich, danach moeglichst frueh lernen.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ortools.sat.python import cp_model

from .config import BLOCK_MIN, PUFFER_MIN, SLOT_MIN, SOLVER_ZEITLIMIT_S, WOCHENPLAN


@dataclass
class Aufgabe:
    id: int
    fach: str | None
    minuten: int
    termin: datetime


@dataclass
class Block:
    aufgabe_id: int
    start: datetime
    ende: datetime


@dataclass
class Ergebnis:
    status: str
    bloecke: list[Block] = field(default_factory=list)
    max_tageslast_min: int | None = None
    zu_knapp: list[int] = field(default_factory=list)


def _aufrunden(dt: datetime) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    rest = dt.minute % SLOT_MIN
    return dt + timedelta(minutes=SLOT_MIN - rest) if rest else dt


def _uhrzeit(tag: datetime, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return tag.replace(hour=h, minute=m, second=0, microsecond=0)


def lernfenster(von: datetime, bis: datetime) -> list[tuple[datetime, datetime, tuple[str, ...] | None]]:
    """Alle Lernfenster zwischen von und bis, auf das 5-Minuten-Raster gelegt."""
    fenster = []
    von = _aufrunden(von)
    tag = von.replace(hour=0, minute=0, second=0, microsecond=0)
    while tag < bis:
        for s, e, fach in WOCHENPLAN[tag.weekday()]:
            start = max(_aufrunden(_uhrzeit(tag, s)), von)
            ende = _uhrzeit(tag, e)
            ende -= timedelta(minutes=ende.minute % SLOT_MIN)   # abrunden aufs Raster
            ende = min(ende, bis)
            if ende > start:
                fenster.append((start, ende, fach))
        tag += timedelta(days=1)
    return fenster


def _bloecke_teilen(minuten: int) -> list[int]:
    """90 -> [55, 35], 120 -> [55, 55, 10] (Rest auf 5 min aufgerundet)."""
    teile = []
    while minuten > 0:
        dauer = min(BLOCK_MIN, minuten)
        dauer = -(-dauer // SLOT_MIN) * SLOT_MIN
        teile.append(dauer)
        minuten -= dauer
    return teile


def planen(aufgaben: list[Aufgabe], jetzt: datetime, zeitlimit_s: float = SOLVER_ZEITLIMIT_S) -> Ergebnis:
    aufgaben = [a for a in aufgaben if a.minuten > 0]
    if not aufgaben:
        return Ergebnis(status="leer")

    t0 = _aufrunden(jetzt)
    ende_horizont = max(a.termin for a in aufgaben)
    fenster = lernfenster(t0, ende_horizont)

    def slot(dt: datetime) -> int:
        return int((dt - t0).total_seconds() // 60) // SLOT_MIN


    zu_knapp = []
    for a in aufgaben:
        grenze = a.termin - timedelta(minutes=PUFFER_MIN)
        verfuegbar = sum(
            max(0, (min(e, grenze) - s).total_seconds() / 60)
            for s, e, f in fenster if f is None or a.fach in f)
        if verfuegbar < a.minuten:
            zu_knapp.append(a.id)

    m = cp_model.CpModel()
    horizont = slot(ende_horizont) + 1
    anzahl_tage = (ende_horizont.date() - t0.date()).days + 1
    tageslast = [[] for _ in range(anzahl_tage)]
    bloecke, starts, intervalle = [], [], []
    lernbuero_wahl = {}

    for a in aufgaben:
        grenze = slot(a.termin - timedelta(minutes=PUFFER_MIN))
        vorher = None
        for dauer_min in _bloecke_teilen(a.minuten):
            dauer = dauer_min // SLOT_MIN
            s = m.NewIntVar(0, horizont, f"s_{a.id}_{len(bloecke)}")
            wahl = []
            for wi, (fs, fe, ff) in enumerate(fenster):
                if ff is not None and a.fach not in ff:
                    continue
                von, bis = slot(fs), min(slot(fe), grenze)
                if bis - von < dauer:
                    continue
                p = m.NewBoolVar("")
                m.Add(s >= von).OnlyEnforceIf(p)
                m.Add(s + dauer <= bis).OnlyEnforceIf(p)
                if ff is not None:
                    if (wi, a.fach) not in lernbuero_wahl:
                        lernbuero_wahl[(wi, a.fach)] = m.NewBoolVar("")
                    m.AddImplication(p, lernbuero_wahl[(wi, a.fach)])
                wahl.append(p)
                tageslast[(fs.date() - t0.date()).days].append(dauer_min * p)
            if not wahl:
                return Ergebnis(status="unloesbar", zu_knapp=zu_knapp or [a.id])
            m.AddExactlyOne(wahl)
            if vorher is not None:
                m.Add(vorher <= s)
            vorher = s
            starts.append(s)
            intervalle.append(m.NewIntervalVar(s, dauer, s + dauer, ""))
            bloecke.append((a.id, dauer))

    m.AddNoOverlap(intervalle)
    for wi in {wi for wi, _ in lernbuero_wahl}:
        m.AddAtMostOne([v for (w, _), v in lernbuero_wahl.items() if w == wi])
    last = []
    for terme in tageslast:
        v = m.NewIntVar(0, 24 * 60, "")
        m.Add(v == sum(terme))
        last.append(v)
    max_last = m.NewIntVar(0, 24 * 60, "max_last")
    m.AddMaxEquality(max_last, last)
    gewicht = len(starts) * horizont + 1
    m.Minimize(max_last * gewicht + sum(starts))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = zeitlimit_s
    solver.parameters.num_workers = 4
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        status = "unloesbar" if st == cp_model.INFEASIBLE else "unbekannt"
        return Ergebnis(status=status, zu_knapp=zu_knapp)

    ergebnis = []
    for s, (aid, dauer) in zip(starts, bloecke):
        beginn = t0 + timedelta(minutes=solver.Value(s) * SLOT_MIN)
        ergebnis.append(Block(aid, beginn, beginn + timedelta(minutes=dauer * SLOT_MIN)))
    ergebnis.sort(key=lambda b: b.start)
    return Ergebnis(
        status="optimal" if st == cp_model.OPTIMAL else "gueltig",
        bloecke=ergebnis,
        max_tageslast_min=solver.Value(max_last),
    )
