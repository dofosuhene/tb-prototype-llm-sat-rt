def test_freitext_speichert_und_plant(client):
    r = client.post("/freitext", json={"text": "Mathe-Test am Freitag über Integrale"})
    d = r.json()
    assert r.status_code == 200 and d["status"] == "gespeichert"
    z = client.get("/zustand").json()
    assert z["eintraege"][0]["fach"] == "Mathematik"
    assert z["eintraege"][0]["termin"] == "2026-10-16T08:00:00"
    assert sum(1 for b in z["bloecke"]) == 4          # 180 min Pruefung = 4 Bloecke a 45 min


def test_rueckfrage_bei_fehlendem_fach(client):
    d = client.post("/freitext", json={"text": "Test nächste Woche"}).json()
    assert d["status"] == "rueckfrage" and d["fehlend"] == ["fach"]
    d = client.post("/freitext", json={"text": "Test nächste Woche, Englisch"}).json()
    assert d["status"] == "gespeichert"


def test_irrelevant(client):
    d = client.post("/freitext", json={"text": "Wer kommt heute mit ins Kino?"}).json()
    assert d["status"] == "irrelevant"
    assert client.get("/zustand").json()["eintraege"] == []


def test_zu_langer_text_wird_abgelehnt(client):
    assert client.post("/freitext", json={"text": "x" * 301}).status_code == 422


def test_websocket_bekommt_update(client):
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["eintraege"] == []
        client.post("/freitext", json={"text": "Englisch Essay bis Donnerstag"})
        n = ws.receive_json()
        assert n["typ"] == "update" and n["eintraege"][0]["fach"] == "Englisch"
        assert len(n["bloecke"]) == 2


def test_readiness_nach_erledigtem_block(client):
    client.post("/freitext", json={"text": "SEW Projekt Abgabe am 14.11."})
    z = client.get("/zustand").json()
    client.post(f"/lernbloecke/{z['bloecke'][0]['id']}/erledigt")
    r = client.get("/readiness").json()[0]
    assert r["erledigt_min"] == 45 and r["score"] == 0.5


def test_neuplanung_behaelt_erledigte_bloecke(client):
    client.post("/freitext", json={"text": "SEW Projekt Abgabe am 14.11."})
    erster = client.get("/zustand").json()["bloecke"][0]
    client.post(f"/lernbloecke/{erster['id']}/erledigt")
    client.post("/freitext", json={"text": "Deutsch Schularbeit am 3.12."})
    z = client.get("/zustand").json()
    assert any(b["id"] == erster["id"] and b["erledigt"] for b in z["bloecke"])
    sew = [b for b in z["bloecke"] if b["fach"] == "SEW"]
    assert len(sew) == 2                              # 1 erledigt + 1 offener (90 - 45 = 45 min)


def test_loeschen_plant_neu(client):
    d = client.post("/freitext", json={"text": "ITP Laborprotokoll bis morgen"}).json()
    client.delete(f"/eintraege/{d['eintrag_id']}")
    assert client.get("/zustand").json()["bloecke"] == []
