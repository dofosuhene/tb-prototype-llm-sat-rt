"""Vorstudie Solver: gemeinsame Szenariodaten fuer CP-SAT (Python) und MiniZinc (Gecode, Chuffed).

Zeitraster: 15 Minuten. Zeitpunkt t = Anzahl 15-Minuten-Schritte ab Montag 00:00.
Ein Lernblock darf nur in einem erlaubten Zeitfenster liegen:
  - freie Zeit (nach dem Unterricht, Wochenende) fuer alle Faecher
  - Lernbuero-Fenster nur fuer Bloecke des passenden Fachs
Unterricht ist dadurch automatisch ausgeschlossen (liegt in keinem Fenster).
"""
SLOT = 15
TAG = 24 * 60 // SLOT  # 96 Schritte pro Tag


def t(tag, hh, mm=0):
    """tag 0=Mo ... 6=So"""
    return tag * TAG + (hh * 60 + mm) // SLOT


FAECHER = ["Mathematik", "Englisch", "Deutsch", "SEW", "ITP"]
F = {f: i + 1 for i, f in enumerate(FAECHER)}  # 0 = freie Zeit (alle Faecher)


def fenster_basis():
    w = []  # (tag, start, ende, fach) fach=0 -> frei
    # Unterricht Mo-Fr bis 15:30 (Fr bis 13:00), danach freie Lernzeit bis 20:00
    for tag in range(5):
        ende_unterricht = t(tag, 13) if tag == 4 else t(tag, 15, 30)
        w.append((tag, ende_unterricht, t(tag, 20), 0))
    # Fachgebundene Lernbuero-Stunden waehrend der Schulzeit
    w.append((0, t(0, 11, 30), t(0, 13, 10), F["Mathematik"]))   # Mo
    w.append((2, t(2, 11, 30), t(2, 13, 10), F["Englisch"]))     # Mi
    w.append((3, t(3, 9, 50), t(3, 11, 30), F["SEW"]))           # Do
    # Wochenende
    for tag in (5, 6):
        w.append((tag, t(tag, 9), t(tag, 12), 0))
        w.append((tag, t(tag, 14), t(tag, 18), 0))
    return w


def bloecke(aufgaben, blocklaenge_min=45):
    """aufgaben: (name, fach, minuten, deadline_t) -> Liste von Bloecken (aufgabe_idx, fach, dauer, deadline)"""
    b = []
    d = blocklaenge_min // SLOT
    for i, (_, fach, minuten, deadline) in enumerate(aufgaben):
        for _ in range(-(-minuten // blocklaenge_min)):
            b.append((i, F[fach], d, deadline))
    return b


PUFFER = 60 // SLOT  # Lernbloecke enden mindestens 60 min vor der Deadline

# A1: normale Woche mit Lernbuero
A_AUFGABEN = [
    ("Mathe-HUE Integrale", "Mathematik", 90, t(2, 8)),        # bis Mi 8:00
    ("Englisch Essay", "Englisch", 135, t(3, 8)),              # bis Do 8:00
    ("SEW Programmieraufgabe", "SEW", 180, t(4, 8)),           # bis Fr 8:00
    ("Deutsch Erörterung", "Deutsch", 90, t(4, 8)),            # bis Fr 8:00
    ("ITP Laborprotokoll", "ITP", 90, t(6, 20)),               # bis So 20:00
    ("Mathe-HUE Wahrscheinlichkeit", "Mathematik", 45, t(6, 20)),
]

# A2: zwei Schularbeiten in einer Woche (Mathe Do, Englisch Fr) + laufende HUE
B_AUFGABEN = [
    ("Vorbereitung SA Mathematik", "Mathematik", 360, t(3, 8)),   # SA Do 8:00
    ("Vorbereitung SA Englisch", "Englisch", 270, t(4, 8)),       # SA Fr 8:00
    ("SEW Programmieraufgabe", "SEW", 135, t(4, 8)),
    ("Deutsch Lektüre", "Deutsch", 90, t(6, 20)),
    ("ITP Laborprotokoll", "ITP", 90, t(6, 20)),
]

# A3: wie A2, aber ueberladen (deutlich mehr Lernzeit als verfuegbar) -> unloesbar
B2_AUFGABEN = B_AUFGABEN + [
    ("Zusatz: Referat Deutsch", "Deutsch", 600, t(1, 8)),   # bis Di 8:00, 10 h -> passt nicht
]

# Testszenario A der Machbarkeitsstudie: A1 normale Woche, A2 Pruefungswoche, A3 ueberladene Woche
SZENARIEN = {
    "A1": A_AUFGABEN,
    "A2": B_AUFGABEN,
    "A3": B2_AUFGABEN,
}
