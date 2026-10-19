"""Zeitausdruecke wie "bis Freitag" in ein Datum umrechnen.

Das LLM liefert den Ausdruck nur woertlich. Das Rechnen passiert hier im Code,
damit es nachvollziehbar und testbar ist. Kann ein Ausdruck nicht aufgeloest
werden, kommt None zurueck und die App stellt eine Rueckfrage.

Festgelegte Lesarten (fuer das Dev-Log):
  - "Freitag" / "am Freitag" / "naechsten Freitag" = der kommende Freitag (nie heute)
  - "naechste Woche" ohne Tag = Montag der naechsten Woche (frueh = sicher)
  - Termin an einem Tag = faellig um 8:00 (Schulbeginn)
"""
import re
from datetime import date, datetime, time, timedelta

from .config import FAELLIG_UM

WOCHENTAGE = {"montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
              "freitag": 4, "samstag": 5, "sonntag": 6}
ZAHLWOERTER = {"ein": 1, "einem": 1, "einer": 1, "eine": 1, "zwei": 2, "drei": 3, "vier": 4,
               "fuenf": 5, "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8}

_DATUM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})?")
_IN_N = re.compile(r"\bin\s+(\d+|" + "|".join(ZAHLWOERTER) + r")\s+(tag|tagen|woche|wochen)\b")
_TAG = re.compile(r"\b(" + "|".join(WOCHENTAGE) + r")\b")


def _faellig(tag: date) -> datetime:
    return datetime.combine(tag, time(*FAELLIG_UM))


def aufloesen(ausdruck: str | None, jetzt: datetime) -> datetime | None:
    """Gibt den Faelligkeitszeitpunkt zurueck oder None, wenn der Ausdruck unklar ist."""
    if not ausdruck:
        return None
    a = ausdruck.lower().replace("ä", "ae").replace("ü", "ue").replace("ö", "oe")
    heute = jetzt.date()

    m = _DATUM.search(a)
    if m:
        tag, monat, jahr = int(m.group(1)), int(m.group(2)), m.group(3)
        if jahr:
            j = int(jahr)
            jahr_int = j + 2000 if j < 100 else j
        else:
            jahr_int = heute.year
        try:
            d = date(jahr_int, monat, tag)
        except ValueError:
            return None
        if not jahr and d < heute:  # "14.11." im Dezember meint naechstes Jahr
            d = date(jahr_int + 1, monat, tag)
        return _faellig(d)

    if "uebermorgen" in a:
        return _faellig(heute + timedelta(days=2))
    if "morgen" in a:
        return _faellig(heute + timedelta(days=1))
    if "heute" in a:
        return datetime.combine(heute, time(20, 0))

    m = _IN_N.search(a)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else ZAHLWOERTER[m.group(1)]
        tage = n * 7 if m.group(2).startswith("woche") else n
        return _faellig(heute + timedelta(days=tage))

    m = _TAG.search(a)
    if m:
        ziel = WOCHENTAGE[m.group(1)]
        diff = (ziel - heute.weekday()) % 7 or 7
        return _faellig(heute + timedelta(days=diff))

    if "uebernaechste woche" in a or "uebernaechsten woche" in a:
        return _faellig(heute + timedelta(days=14 - heute.weekday()))
    if "naechste woche" in a or "naechsten woche" in a:
        return _faellig(heute + timedelta(days=7 - heute.weekday()))

    return None
