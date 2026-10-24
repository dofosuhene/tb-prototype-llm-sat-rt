# TaskBuddy – Backend-Prototyp (Machbarkeitsstudie)

Freitext → Sprachmodell (Structured Outputs) → SQLite → CP-SAT → WebSocket / SSE / Socket.IO → Browser.

Der Prototyp dient zwei Zwecken:
1. Durchstich: Eine Nachricht wie „Mathe Test am Freitag“ wird erfasst, eingeplant und live an alle offenen Clients geschickt.
2. Technologievergleich: Die Skripte in `vergleich/` messen Constraint-Solver, Sprachmodell-Anbieter und Echtzeit-Technologien unter gleichen Bedingungen.

## Start
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Sprachmodell (kostenlos, OpenAI-kompatibel), Beispiel Groq:
export OPENAI_BASE_URL=https://api.groq.com/openai/v1
export OPENAI_API_KEY=gsk_...
export OPENAI_MODEL=openai/gpt-oss-20b      # Modellname in der Groq-Doku prüfen
# ohne Schlüssel läuft ein einfacher Regel-Ersatz (nur Demo)

uvicorn app.main:asgi --reload
```
- Testseite: http://localhost:8000 (zwei Tabs öffnen, dann sind die Echtzeit-Updates sichtbar)
- Swagger UI: http://localhost:8000/docs (alle REST-Endpunkte direkt ausprobieren)
- Tests: `python -m pytest`

Wichtig: `app.main:asgi` starten, nicht `app.main:app`, sonst fehlt Socket.IO.

## Aufbau
| Datei | Aufgabe |
|---|---|
| `app/config.py` | Lernfenster, Lernbüro, Blocklänge, Puffer, Lernzeiten, Anbieter-Einstellungen |
| `app/llm.py` | Freitext → `Extraktion` (Sprachmodell oder Regel-Ersatz) |
| `app/datum.py` | „bis Freitag“ → Datum (Code, nicht Sprachmodell) |
| `app/planer.py` | CP-SAT-Modell (aus der Vorstudie) |
| `app/db.py` | `Eintrag`, `Lernblock` |
| `app/echtzeit.py` | Verteiler: jede Änderung geht an WebSocket, SSE und Socket.IO |
| `app/main.py` | Endpunkte |
| `app/static/index.html` | Testseite |

## Endpunkte
| Methode | Pfad | Zweck |
|---|---|---|
| POST | `/freitext` | Nachricht erfassen, Eintrag anlegen oder Rückfrage |
| GET | `/zustand` | Einträge und Lernblöcke |
| POST | `/plan` | Neu planen |
| POST | `/lernbloecke/{id}/erledigt` | Lernblock abhaken |
| DELETE | `/eintraege/{id}` | Eintrag löschen |
| GET | `/readiness` | Vorbereitungsstand je Prüfung |
| WS | `/ws` | Echtzeit über WebSocket |
| GET | `/sse` | Echtzeit über Server-Sent Events |
| – | `/socket.io` | Echtzeit über Socket.IO (Event `update`) |
| POST | `/vergleich/ping?nr=` | Testnachricht an alle drei Echtzeit-Wege (nur für die Messung) |

## Technologievergleich (`vergleich/`)
Alle Skripte im Ordner `taskbuddy-prototyp` starten. Ergebnisse landen als CSV im Ordner `vergleich/`.

| Skript | Vergleicht | Voraussetzung | Ergebnis |
|---|---|---|---|
| `python -m vergleich.solver 5` | OR-Tools CP-SAT, Chuffed, Gecode (3 Szenarien, 5 Wiederholungen, 30 s Limit) | MiniZinc-Bundle installiert (`minizinc --solvers`) | `ergebnisse_solver.csv` |
| `python -m vergleich.llm` | Groq und Ollama lokal mit 20 Testnachrichten | je Anbieter `*_API_KEY` und `*_MODEL` gesetzt | `ergebnisse_llm.csv` |
| `python -m vergleich.last groq --anfragen 60 --parallel 10` | Lasttest eines Anbieters: ab wann greift die Grenze, Tokens pro Anfrage, Hochrechnung für 50, 500 und 1000 Nutzer | wie beim LLM-Vergleich, optional `--tpm --tpd --rpm --rpd` aus dem eigenen Konto | `ergebnisse_last_<anbieter>.csv` |
| `python -m vergleich.echtzeit 200` | WebSocket, SSE, Socket.IO (Verbindungsaufbau, Latenz, Verluste) | keine | `ergebnisse_echtzeit.csv` |

Umgebungsvariablen für den Sprachmodell-Vergleich (nur gesetzte Anbieter werden getestet):
```bash
export GROQ_API_KEY=...     GROQ_MODEL=openai/gpt-oss-20b
export OLLAMA_MODEL=qwen3:8b            # vorher: ollama pull qwen3:8b
```
Modellnamen ändern sich. Vor dem Lauf in der Doku des Anbieters prüfen.

Nur die Testnachrichten aus `vergleich/llm.py` verwenden, keine echten Schülerdaten. API-Schlüssel nie committen.

## Festgelegt (fürs Dev-Log)
- Datum rechnet der Code. Unklarer Termin → Rückfrage.
- „Freitag“ = kommender Freitag. „nächste Woche“ = Montag. Fällig um 8:00.
- Lernzeit fix: Aufgabe 90 min, Prüfung 180 min (adaptiv später, /LF13/).
- Ziel: höchste Tageslast minimal, dann früh lernen. Puffer 60 min vor Termin.
- Neuplanung behält erledigte Blöcke. Unlösbar → alter Plan bleibt.
- Readiness = erledigte ÷ geplante Lernminuten.

## Bewusst nicht enthalten
SSO/Login, finales DB-Schema/Alembic, Exam-Mode, Erinnerungen, echtes Frontend.
