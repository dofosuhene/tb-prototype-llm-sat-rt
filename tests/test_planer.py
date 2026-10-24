from datetime import datetime, timedelta

from app.planer import Aufgabe, lernfenster, planen

JETZT = datetime(2026, 10, 12, 14, 0)  # Montag


def keine_ueberschneidung(bloecke):
    s = sorted(bloecke, key=lambda b: b.start)
    return all(a.ende <= b.start for a, b in zip(s, s[1:]))


def test_leer():
    assert planen([], JETZT).status == "leer"


def test_bloecke_vor_termin_und_ohne_ueberschneidung():
    aufgaben = [Aufgabe(1, "Mathematik", 180, datetime(2026, 10, 16, 8)),
                Aufgabe(2, "Englisch", 90, datetime(2026, 10, 15, 8))]
    e = planen(aufgaben, JETZT)
    assert e.status == "optimal"
    assert sum((b.ende - b.start).seconds // 60 for b in e.bloecke) == 270
    assert keine_ueberschneidung(e.bloecke)
    for b in e.bloecke:
        termin = next(a.termin for a in aufgaben if a.id == b.aufgabe_id)
        assert b.ende <= termin - timedelta(minutes=60)
        assert b.start >= JETZT


def test_lernbuero_nur_ein_fach_pro_stunde():
    aufgaben = [Aufgabe(1, "Mathematik", 135, datetime(2026, 10, 15, 8)),
                Aufgabe(2, "Englisch", 135, datetime(2026, 10, 15, 8)),
                Aufgabe(3, "SEW", 135, datetime(2026, 10, 15, 8))]
    e = planen(aufgaben, datetime(2026, 10, 12, 8))
    assert e.status in ("optimal", "gueltig")
    fach = {a.id: a.fach for a in aufgaben}
    im_lernbuero = {}
    for b in e.bloecke:
        if b.start.weekday() < 4 and b.start.hour < 15:
            im_lernbuero.setdefault(b.start.date(), set()).add(fach[b.aufgabe_id])
    assert im_lernbuero
    assert all(len(f) == 1 for f in im_lernbuero.values())


def test_lernbuero_nicht_fuer_fremdes_fach():
    e = planen([Aufgabe(1, "Geschichte", 450, datetime(2026, 10, 19, 8))], datetime(2026, 10, 12, 8))
    assert e.bloecke
    assert all(b.start.weekday() >= 4 or b.start.hour >= 15 for b in e.bloecke)


def test_unloesbar_meldet_zu_knappe_aufgabe():
    e = planen([Aufgabe(7, "Deutsch", 600, datetime(2026, 10, 13, 8))], JETZT)
    assert e.status == "unloesbar"
    assert e.zu_knapp == [7]


def test_last_wird_verteilt():
    # 6 Bloecke bis Freitag: gleichmaessig verteilt -> max. 90 min pro Tag statt alles am Montag
    e = planen([Aufgabe(1, "SEW", 270, datetime(2026, 10, 17, 8))], JETZT)
    assert e.max_tageslast_min <= 90


def test_lernfenster_beginnen_nicht_vor_jetzt():
    f = lernfenster(datetime(2026, 10, 12, 16, 7), datetime(2026, 10, 13, 0))
    assert f[0][0] == datetime(2026, 10, 12, 16, 10)
