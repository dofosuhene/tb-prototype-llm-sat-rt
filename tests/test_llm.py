import asyncio
import json
from types import SimpleNamespace

from app.llm import OpenAiExtraktor


class FakeCompletions:
    def __init__(self, inhalt):
        self.inhalt, self.aufruf = inhalt, None

    async def create(self, **kwargs):
        self.aufruf = kwargs
        nachricht = SimpleNamespace(content=json.dumps(self.inhalt))
        return SimpleNamespace(choices=[SimpleNamespace(message=nachricht)])


def test_openai_extraktor_nutzt_schema_und_prueft_antwort():
    antwort = {"is_relevant": True, "entry_type": "Pruefung", "subject": "Mathe", "title": "Integrale",
               "raw_date_expression": "am Freitag", "missing_fields": []}
    x = OpenAiExtraktor("test-key", "test-modell")
    fake = FakeCompletions(antwort)
    x.client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    e = asyncio.run(x.extrahieren("Mathe-Test am Freitag über Integrale"))
    assert e.entry_type == "Pruefung" and e.raw_date_expression == "am Freitag"
    assert fake.aufruf["response_format"]["json_schema"]["strict"] is True
    assert fake.aufruf["messages"][1]["content"] == "Mathe-Test am Freitag über Integrale"
