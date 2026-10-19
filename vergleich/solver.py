"""Vergleich Constraint-Solver: dasselbe Wochenplan-Modell mit OR-Tools CP-SAT, Chuffed und Gecode.

Aufruf (im Ordner taskbuddy-prototyp): python -m vergleich.solver [wiederholungen]
Voraussetzung fuer Chuffed und Gecode: MiniZinc-Bundle installiert (minizinc --solvers).
Ergebnis: vergleich/ergebnisse_solver.csv und Median je Szenario auf der Konsole.
"""
import csv
import statistics
import sys
import time
from pathlib import Path

from minizinc import Instance, Model, Solver, Status
from ortools.sat.python import cp_model

from .szenarien import PUFFER, SZENARIEN, TAG, bloecke, fenster_basis

ZEITLIMIT_S = 30
HIER = Path(__file__).parent


def daten(aufgaben):
    w = fenster_basis()
    b = bloecke(aufgaben)
    return w, b


def cpsat(aufgaben, worker):
    w, b = daten(aufgaben)
    m = cp_model.CpModel()
    horizon = 7 * TAG
    starts, intervals, day_terms = [], [], {d: [] for d in range(7)}
    for bi, (task, fach, dauer, dl) in enumerate(b):
        s = m.NewIntVar(0, horizon, f"s{bi}")
        lits = []
        for wi, (tag, ws, we, wf) in enumerate(w):
            if wf not in (0, fach):
                continue
            ende = min(we, dl - PUFFER)
            if ende - ws < dauer:
                continue
            p = m.NewBoolVar(f"p{bi}_{wi}")
            m.Add(s >= ws).OnlyEnforceIf(p)
            m.Add(s + dauer <= ende).OnlyEnforceIf(p)
            lits.append(p)
            day_terms[tag].append(dauer * p)
        if not lits:
            m.AddBoolOr([])  # kein Fenster moeglich -> unloesbar
        else:
            m.AddExactlyOne(lits)
        starts.append(s)
        intervals.append(m.NewIntervalVar(s, dauer, s + dauer, f"i{bi}"))
    m.AddNoOverlap(intervals)
    for bi in range(len(b) - 1):
        if b[bi][0] == b[bi + 1][0]:
            m.Add(starts[bi] <= starts[bi + 1])
    loads = []
    for d in range(7):
        l = m.NewIntVar(0, horizon, f"load{d}")
        m.Add(l == sum(day_terms[d]))
        loads.append(l)
    mx = m.NewIntVar(0, horizon, "max")
    m.AddMaxEquality(mx, loads)
    m.Minimize(mx)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = ZEITLIMIT_S
    solver.parameters.num_workers = worker
    t0 = time.perf_counter()
    st = solver.Solve(m)
    dt = time.perf_counter() - t0
    status = {cp_model.OPTIMAL: "optimal", cp_model.FEASIBLE: "gueltig",
              cp_model.INFEASIBLE: "unloesbar", cp_model.UNKNOWN: "unbekannt"}.get(st, str(st))
    obj = solver.ObjectiveValue() if st in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None
    return status, obj, dt, len(b)


def mzn(aufgaben, solver_name):
    w, b = daten(aufgaben)
    model = Model(str(HIER / "wochenplan.mzn"))
    inst = Instance(Solver.lookup(solver_name), model)
    inst["nW"] = len(w)
    inst["wday"] = [x[0] for x in w]
    inst["wstart"] = [x[1] for x in w]
    inst["wend"] = [x[2] for x in w]
    inst["wfach"] = [x[3] for x in w]
    inst["nB"] = len(b)
    inst["btask"] = [x[0] for x in b]
    inst["bfach"] = [x[1] for x in b]
    inst["bdur"] = [x[2] for x in b]
    inst["bdl"] = [x[3] for x in b]
    inst["puffer"] = PUFFER
    inst["horizon"] = 7 * TAG
    from datetime import timedelta
    t0 = time.perf_counter()
    res = inst.solve(timeout=timedelta(seconds=ZEITLIMIT_S))
    dt = time.perf_counter() - t0
    status = {Status.OPTIMAL_SOLUTION: "optimal", Status.SATISFIED: "gueltig",
              Status.UNSATISFIABLE: "unloesbar", Status.UNKNOWN: "unbekannt"}.get(res.status, str(res.status))
    obj = res.objective if res.status in (Status.OPTIMAL_SOLUTION, Status.SATISFIED) else None
    return status, obj, dt, len(b)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    laeufe = [
        ("OR-Tools CP-SAT (1 Thread)", lambda a: cpsat(a, 1)),
        ("OR-Tools CP-SAT (2 Threads)", lambda a: cpsat(a, 2)),
        ("Chuffed (MiniZinc)", lambda a: mzn(a, "chuffed")),
        ("Gecode (MiniZinc)", lambda a: mzn(a, "gecode")),
    ]
    rows = []
    for sz, aufgaben in SZENARIEN.items():
        for name, f in laeufe:
            for i in range(n):
                status, obj, dt, nb = f(aufgaben)
                # Zielwert in Minuten (Schritte * 15)
                rows.append([sz, name, i + 1, nb, status, "" if obj is None else int(obj) * 15, f"{dt:.3f}"])
                print(rows[-1], flush=True)
    with open(HIER / "ergebnisse_solver.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["szenario", "solver", "lauf", "bloecke", "status", "max_tageslast_min", "zeit_s"])
        wr.writerows(rows)
    print("\nMedian je Szenario und Solver:")
    for sz in SZENARIEN:
        for name, _ in laeufe:
            r = [x for x in rows if x[0] == sz and x[1] == name]
            zeiten = [float(x[6]) for x in r]
            stati = sorted(set(x[4] for x in r))
            objs = sorted(set(str(x[5]) for x in r))
            print(f"{sz:13} {name:28} Bloecke={r[0][3]:3} Status={'/'.join(stati):10} "
                  f"MaxTageslast={'/'.join(objs):8} Median={statistics.median(zeiten):.3f}s "
                  f"(min {min(zeiten):.3f}, max {max(zeiten):.3f})")


if __name__ == "__main__":
    main()
