import os
from datetime import datetime

os.environ["DATENBANK_URL"] = "sqlite://"     # Datenbank nur im Speicher
os.environ.pop("OPENAI_API_KEY", None)        # Tests nie gegen die echte API

import pytest
from fastapi.testclient import TestClient

from app import main
from app.db import Base, engine
from app.llm import RegelExtraktor

JETZT = datetime(2026, 10, 12, 14, 0)          # Montag, 14:00


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    main._letzter_plan.update(status="leer", max_tageslast_min=None, zu_knapp=[])
    main.app.dependency_overrides[main.get_jetzt] = lambda: JETZT
    main.app.dependency_overrides[main.get_extraktor] = lambda: RegelExtraktor()
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
