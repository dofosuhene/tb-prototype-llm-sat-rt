"""Lasttest Sprachmodell-Anbieter: Wie viele Anfragen schafft ein Anbieter, bevor er bremst?

Schickt viele Testnachrichten parallel an EINEN Anbieter und misst je Anfrage:
  - Ergebnis: ok, grenze (HTTP 429), zeitlimit oder fehler
  - Antwortzeit
  - verbrauchte Tokens (prompt + completion), wichtig fuer die Tages- und Minutengrenzen
Danach rechnet das Skript hoch, wie viele Nutzerinnen und Nutzer der Anbieter pro Tag schafft.

Aufruf (im Ordner taskbuddy-prototyp):
  python -m vergleich.last groq --anfragen 60 --parallel 10
  python -m vergleich.last ollama --anfragen 30 --parallel 5 --zeitlimit 60
Optionale Grenzen fuer die Hochrechnung (Werte aus dem eigenen Anbieter-Konto unter "Limits"):
  --tpm 8000 --tpd 200000 --rpm 30 --rpd 1000
Schluessel und Modell wie bei vergleich.llm ueber GROQ_API_KEY/GROQ_MODEL usw.

Hinweis: Bei Cloud-Anbietern verbraucht der Test das Gratis-Kontingent. Kurz halten (60 Anfragen reichen),
sonst ist das Tageslimit fuer den Rest des Tages weg. Nur die Testsaetze verwenden, keine echten Schuelerdaten.
"""
import argparse
import asyncio
import csv
import json
import os
import statistics
import time
from pathlib import Path

import openai
from openai import AsyncOpenAI

from .llm import ANBIETER, ANWEISUNG, SCHEMA, TESTSET

HIER = Path(__file__).parent
KURZ = {"groq": "Groq", "ollama": "Ollama (lokal)", "vllm": "vLLM"}


def client_fuer(name: str, zeitlimit: float):
    key_env, model_env, base = ANBIETER[name]
    key, model = os.environ.get(key_env), os.environ.get(model_env)
    if name.startswith(("Ollama", "vLLM")) and model and not key:
        key = "ollama"
    if os.environ.get("LAST_BASE_URL"):          # nur fuer eigene Tests mit einem Ersatz-Server
        base = os.environ["LAST_BASE_URL"]
    if not key or not model:
        raise SystemExit(f"{key_env} und {model_env} setzen")
    # max_retries=0: die Bibliothek soll bei 429 NICHT still wiederholen, wir wollen die Grenze sehen
    return AsyncOpenAI(api_key=key, base_url=base, max_retries=0, timeout=zeitlimit), model


async def eine_anfrage(client, model, nr, text, sem, start):
    async with sem:
        t_start = time.perf_counter()
        zeile = {"nr": nr, "start_s": round(t_start - start, 2), "ergebnis": "", "zeit_s": 0.0,
                 "prompt_tokens": "", "completion_tokens": "", "retry_after": "", "fehler": ""}
        try:
            r = await client.chat.completions.create(
                model=model, response_format=SCHEMA,
                messages=[{"role": "system", "content": ANWEISUNG}, {"role": "user", "content": text}])
            json.loads(r.choices[0].message.content)
            zeile["ergebnis"] = "ok"
            if r.usage:
                zeile["prompt_tokens"], zeile["completion_tokens"] = r.usage.prompt_tokens, r.usage.completion_tokens
        except openai.RateLimitError as ex:
            zeile["ergebnis"] = "grenze"
            zeile["retry_after"] = ex.response.headers.get("retry-after", "") if ex.response else ""
        except openai.APITimeoutError:
            zeile["ergebnis"] = "zeitlimit"
        except Exception as ex:
            zeile["ergebnis"] = "fehler"
            zeile["fehler"] = f"{type(ex).__name__}: {ex}"[:120]
        zeile["zeit_s"] = round(time.perf_counter() - t_start, 2)
        return zeile


async def lauf(client, model, anfragen, parallel):
    sem = asyncio.Semaphore(parallel)
    start = time.perf_counter()
    texte = [TESTSET[i % len(TESTSET)][0] for i in range(anfragen)]
    zeilen = await asyncio.gather(*(eine_anfrage(client, model, i, t, sem, start) for i, t in enumerate(texte)))
    return zeilen, time.perf_counter() - start


def hochrechnung(tokens_pro_anfrage, args):
    """Wie viele Anfragen pro Minute und Tag erlauben die Grenzen, und wie viele Nutzer sind das?"""
    pro_min = [g for g in (args.rpm, args.tpm / tokens_pro_anfrage if args.tpm else None) if g]
    pro_tag = [g for g in (args.rpd, args.tpd / tokens_pro_anfrage if args.tpd else None) if g]
    if not pro_tag and not pro_min:
        return
    print("\nHochrechnung aus den angegebenen Grenzen:")
    if pro_min:
        print(f"  hoechstens {min(pro_min):.0f} Anfragen pro Minute")
    if pro_tag:
        tag = min(pro_tag)
        print(f"  hoechstens {tag:.0f} Anfragen pro Tag, also ca. {tag / args.nachrichten:.0f} Nutzer "
              f"bei {args.nachrichten} Nachrichten pro Person und Tag")
        for nutzer in (50, 500, 1000):
            bedarf = nutzer * args.nachrichten
            print(f"  {nutzer:>5} Nutzer brauchen {bedarf:>5} Anfragen pro Tag: "
                  f"{'reicht' if bedarf <= tag else f'reicht NICHT ({bedarf / tag:.1f}-fach zu viel)'}")


def main():
    p = argparse.ArgumentParser(description="Lasttest fuer einen Sprachmodell-Anbieter")
    p.add_argument("anbieter", choices=list(KURZ))
    p.add_argument("--anfragen", type=int, default=60)
    p.add_argument("--parallel", type=int, default=10, help="gleichzeitige Anfragen")
    p.add_argument("--zeitlimit", type=float, default=30.0, help="Sekunden pro Anfrage")
    p.add_argument("--nachrichten", type=int, default=5, help="Nachrichten pro Person und Tag")
    for g in ("rpm", "rpd", "tpm", "tpd"):
        p.add_argument(f"--{g}", type=float, default=None)
    args = p.parse_args()

    name = KURZ[args.anbieter]
    client, model = client_fuer(name, args.zeitlimit)
    print(f"{name} ({model}): {args.anfragen} Anfragen, {args.parallel} gleichzeitig ...")
    zeilen, dauer = asyncio.run(lauf(client, model, args.anfragen, args.parallel))

    datei = HIER / f"ergebnisse_last_{args.anbieter}.csv"
    with open(datei, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)

    zaehl = {e: sum(1 for z in zeilen if z["ergebnis"] == e) for e in ("ok", "grenze", "zeitlimit", "fehler")}
    ok = [z for z in zeilen if z["ergebnis"] == "ok"]
    print(f"\nDauer {dauer:.1f} s, Durchsatz {len(ok) / dauer * 60:.0f} erfolgreiche Anfragen pro Minute")
    print("Ergebnisse: " + ", ".join(f"{k} {v}" for k, v in zaehl.items()))
    erste_grenze = next((z for z in zeilen if z["ergebnis"] == "grenze"), None)
    if erste_grenze:
        print(f"Erste Grenze nach {erste_grenze['start_s']} s (Anfrage {erste_grenze['nr']}), "
              f"retry-after: {erste_grenze['retry_after'] or 'nicht angegeben'}")
    if ok:
        zeiten = sorted(z["zeit_s"] for z in ok)
        print(f"Antwortzeit: Median {statistics.median(zeiten):.2f} s, "
              f"95 % unter {zeiten[int(0.95 * (len(zeiten) - 1))]:.2f} s")
        mit_tokens = [z for z in ok if z["prompt_tokens"] != ""]
        if mit_tokens:
            tok = statistics.mean(z["prompt_tokens"] + z["completion_tokens"] for z in mit_tokens)
            print(f"Tokens pro Anfrage: im Mittel {tok:.0f}")
            hochrechnung(tok, args)
    for z in zeilen:
        if z["fehler"]:
            print("Beispiel-Fehler:", z["fehler"])
            break
    print(f"\nEinzelwerte: {datei}")


if __name__ == "__main__":
    main()
