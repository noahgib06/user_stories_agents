"""Stockage des tests : fusion versionnée, revue humaine, jeux de données."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from . import audit
from .model import load_json, save_json, validate_test

VOLATILE = {"status", "version", "history", "review", "elm"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _content(t):
    return {k: v for k, v in t.items() if k not in VOLATILE}


def merge(ws, proposed, model, actor="orchestrateur"):
    """Intègre les propositions des agents. Un agent ne peut jamais créer un test 'Validé' ni écraser sans historique."""
    ws = Path(ws)
    stories = load_json(ws / "stories.json", [])
    sids = {s["id"] for s in stories}
    tests = {t["id"]: t for t in load_json(ws / "tests.json", [])}
    res = {"added": [], "updated": [], "unchanged": [], "rejected": {}}
    for p in proposed:
        p = dict(p, status="Brouillon", version=1)
        errs = validate_test(p, model, sids)
        if errs:
            res["rejected"][p.get("id", "?")] = errs
            continue
        old = tests.get(p["id"])
        if not old:
            p["history"] = []
            tests[p["id"]] = p
            res["added"].append(p["id"])
        elif _content(old) == _content(p):
            res["unchanged"].append(p["id"])
        else:
            snap = {"version": old["version"], "status": old["status"], "at": _now(), "content": _content(old)}
            p["version"] = old["version"] + 1
            p["history"] = old.get("history", []) + [snap]
            if old.get("elm"):
                p["elm"] = old["elm"]
            tests[p["id"]] = p
            res["updated"].append(p["id"])
    save_json(ws / "tests.json", list(tests.values()))
    audit.log(ws, "merge", actor, **{k: v for k, v in res.items()})
    return res


def review(ws, test_id, status, by, comment="", model=None):
    ws = Path(ws)
    tests = load_json(ws / "tests.json")
    t = next((x for x in tests if x["id"] == test_id), None)
    if not t:
        raise SystemExit(f"test inconnu: {test_id}")
    if status not in model["statuses"]:
        raise SystemExit(f"statut invalide: {status}")
    if not by:
        raise SystemExit("--by (nom du relecteur IVQ/PO) obligatoire")
    if status == "Rejeté" and not comment:
        raise SystemExit("un commentaire est obligatoire pour rejeter")
    prev = t["status"]
    t["status"] = status
    t["review"] = {"by": by, "at": _now(), "comment": comment, "version": t["version"]}
    save_json(ws / "tests.json", tests)
    audit.log(ws, "review", by, test=test_id, version=t["version"], **{"from": prev, "to": status}, comment=comment)


def export_review_csv(ws, path):
    tests = load_json(Path(ws) / "tests.json")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id", "version", "story_id", "type", "priority", "title", "steps", "status", "reviewer", "comment"])
        for t in tests:
            steps = "\n".join(f"{i}. {s['action']} => {s['expected']}" for i, s in enumerate(t["steps"], 1))
            w.writerow([t["id"], t["version"], t["story_id"], t["type"], t["priority"], t["title"], steps,
                        t["status"], "", ""])


def apply_review_csv(ws, path, model):
    """Applique les décisions saisies (colonnes status/reviewer/comment) ; ignore les lignes inchangées."""
    tests = {t["id"]: t for t in load_json(Path(ws) / "tests.json")}
    n = 0
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            t = tests.get(r["id"])
            if not t or not r.get("reviewer"):
                continue
            if r["status"] != t["status"] or r.get("comment"):
                review(ws, r["id"], r["status"], r["reviewer"], r.get("comment", ""), model)
                n += 1
    return n


def export_datasets(ws):
    ws = Path(ws)
    tests = [t for t in load_json(ws / "tests.json") if t.get("data_rows") and t["status"] != "Rejeté"]
    out = ws / "datasets"
    by = {}
    for t in tests:
        by.setdefault(t["story_id"], []).append(t)
    for sid, ts in by.items():
        rows = [dict(test_id=t["id"], **r) for t in ts for r in t["data_rows"]]
        cols = ["test_id"] + sorted({k for r in rows for k in r if k != "test_id"})
        out.mkdir(exist_ok=True)
        with open(out / f"{sid}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, delimiter=";")
            w.writeheader()
            w.writerows(rows)
    return sorted(by)
