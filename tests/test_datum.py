from datetime import datetime

import pytest

from app.datum import aufloesen

JETZT = datetime(2026, 10, 12, 14, 0)  # Montag


@pytest.mark.parametrize("ausdruck, erwartet", [
    ("bis Freitag", datetime(2026, 10, 16, 8)),
    ("am Montag", datetime(2026, 10, 19, 8)),          # heute ist Montag -> naechster Montag
    ("nächsten Dienstag", datetime(2026, 10, 13, 8)),
    ("morgen", datetime(2026, 10, 13, 8)),
    ("übermorgen", datetime(2026, 10, 14, 8)),
    ("am 14.11.", datetime(2026, 11, 14, 8)),
    ("am 3.1.", datetime(2027, 1, 3, 8)),              # schon vorbei -> naechstes Jahr
    ("3.12.2026", datetime(2026, 12, 3, 8)),
    ("in zwei Wochen", datetime(2026, 10, 26, 8)),
    ("in 3 Tagen", datetime(2026, 10, 15, 8)),
    ("nächste Woche", datetime(2026, 10, 19, 8)),
    ("übernächste Woche", datetime(2026, 10, 26, 8)),
])
def test_bekannte_ausdruecke(ausdruck, erwartet):
    assert aufloesen(ausdruck, JETZT) == erwartet


@pytest.mark.parametrize("ausdruck", [None, "", "irgendwann", "bald", "am 31.2."])
def test_unklar_gibt_none(ausdruck):
    assert aufloesen(ausdruck, JETZT) is None
