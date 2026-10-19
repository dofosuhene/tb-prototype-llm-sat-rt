"""Einstellungen des Prototyps an einer Stelle. Spaeter kommen diese Werte aus der Datenbank (Onboarding)."""
import os

SLOT_MIN = 15
BLOCK_MIN = 45
PUFFER_MIN = 60
SOLVER_ZEITLIMIT_S = 5.0

LERNMINUTEN = {"Aufgabe": 90, "Pruefung": 180}

FAELLIG_UM = (8, 0)


WOCHENPLAN = {
    0: [("15:30", "20:00", None), ("11:30", "13:10", "Mathematik")],
    1: [("15:30", "20:00", None)],
    2: [("15:30", "20:00", None), ("11:30", "13:10", "Englisch")],
    3: [("15:30", "20:00", None), ("09:50", "11:30", "SEW")],
    4: [("13:00", "20:00", None)],
    5: [("09:00", "12:00", None), ("14:00", "18:00", None)],
    6: [("09:00", "12:00", None), ("14:00", "18:00", None)],
}


FACH_ALIASE = {
    "mathe": "Mathematik", "mathematik": "Mathematik", "am": "Mathematik",
    "englisch": "Englisch", "english": "Englisch", "e": "Englisch",
    "deutsch": "Deutsch", "d": "Deutsch",
    "sew": "SEW", "softwareentwicklung": "SEW",
    "itp": "ITP", "geschichte": "Geschichte", "ggp": "Geschichte",
    "physik": "Physik", "nw": "Physik",
}

MAX_TEXTLAENGE = 300

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL") or None
DATENBANK_URL = os.environ.get("DATENBANK_URL", "sqlite:///./taskbuddy.db")


def fach_normalisieren(fach: str | None) -> str | None:
    if not fach:
        return None
    schluessel = fach.strip().lower().rstrip(".")
    return FACH_ALIASE.get(schluessel, fach.strip())
