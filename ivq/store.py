"""Stockage des tests : fusion versionnée, revue humaine, jeux de données."""
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import audit
from .model import load_json, save_json, validate_test

VOLATILE = {"status", "version", "history", "review", "elm", "defects"}
IGNORED_FOR_DIFF = VOLATILE | {"generator", "software_version"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _content(t):
    return {k: v for k, v in t.items() if k not in VOLATILE}


def _diffable(t):
    return {k: v for k, v in t.items() if k not in IGNORED_FOR_DIFF}


def merge(ws, proposed, model, actor="orchestrateur", model_name=None, prompt=None, software_version=None):
    """Intègre les propositions des agents. Un agent ne peut jamais créer un test 'Validé' ni écraser sans historique.
    model_name / prompt / software_version alimentent la traçabilité (le prompt est archivé et référencé par son hash)."""
    ws = Path(ws)
    prompt_sha = None
    if prompt:
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        (ws / "prompts").mkdir(parents=True, exist_ok=True)
        (ws / "prompts" / f"{prompt_sha[:16]}.txt").write_text(prompt, encoding="utf-8")
    stories = load_json(ws / "stories.json", [])
    sids = {s["id"] for s in stories}
    tests = {t["id"]: t for t in load_json(ws / "tests.json", [])}
    res = {"added": [], "updated": [], "unchanged": [], "rejected": {}}
    for p in proposed:
        p = dict(p, status="Brouillon", version=1)
        p["generator"] = dict(p.get("generator") or {})
        if model_name:
            p["generator"]["model"] = model_name
        if prompt_sha:
            p["generator"]["prompt_sha256"] = prompt_sha
        if software_version and not p.get("software_version"):
            p["software_version"] = software_version
        errs = validate_test(p, model, sids)
        if errs:
            res["rejected"][p.get("id", "?")] = errs
            continue
        old = tests.get(p["id"])
        if not old:
            p["history"] = []
            tests[p["id"]] = p
            res["added"].append(p["id"])
        elif _diffable(old) == _diffable(p):
            res["unchanged"].append(p["id"])
        else:
            snap = {"version": old["version"], "status": old["status"], "at": _now(), "content": _content(old)}
            p["version"] = old["version"] + 1
            p["history"] = old.get("history", []) + [snap]
            for k in ("elm", "defects"):
                if old.get(k):
                    p[k] = old[k]
            tests[p["id"]] = p
            res["updated"].append(p["id"])
    save_json(ws / "tests.json", list(tests.values()))
    audit.log(ws, "merge", actor, model=model_name, prompt_sha256=prompt_sha,
              software_version=software_version, **{k: v for k, v in res.items()})
    return res


def load_reviewers(path):
    p = Path(path)
    return {r["name"]: r.get("role", "") for r in json.loads(p.read_text(encoding="utf-8"))["reviewers"]} if p.exists() else None


def review(ws, test_id, status, by, comment="", model=None, reviewers=None):
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
    if reviewers is not None and by not in reviewers:
        raise SystemExit(f"relecteur non habilité: {by} (voir config/reviewers.json)")
    prev = t["status"]
    t["status"] = status
    t["review"] = {"by": by, "role": (reviewers or {}).get(by, ""), "at": _now(), "comment": comment,
                   "version": t["version"]}
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


def _parse_steps(text, default):
    """Relit « 1. action => attendu » (une étape par ligne) ; renvoie [(action, attendu)]."""
    out = []
    for line in (text or "").splitlines():
        line = re.sub(r"^\s*\d+\.\s*", "", line).strip()
        if line:
            a, _, e = line.partition("=>")
            out.append((a.strip(), e.strip()))
    return out or [(s["action"], s["expected"]) for s in default]


def apply_review_csv(ws, path, model, reviewers=None):
    """Applique les décisions saisies (colonnes status/reviewer/comment) ; ignore les lignes inchangées."""
    tests = {t["id"]: t for t in load_json(Path(ws) / "tests.json")}
    n = 0
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            t = tests.get(r["id"])
            if not t or not r.get("reviewer"):
                continue
            fix = {}
            if r.get("title", "").strip() and r["title"].strip() != t["title"]:
                fix["title"] = r["title"].strip()
            steps = _parse_steps(r.get("steps", ""), t["steps"])
            if steps != [(s["action"], s["expected"]) for s in t["steps"]]:
                fix["steps"] = [dict(s, action=a, expected=e) for s, (a, e) in zip(t["steps"], steps)] \
                    if len(steps) == len(t["steps"]) else [{"action": a, "data": "", "expected": e} for a, e in steps]
            if fix:
                # correction de contenu : nouvelle version en Brouillon, à revalider par l'humain
                merge(ws, [dict(t, **fix)], model, actor=r["reviewer"])
                n += 1
                continue
            if r["status"] != t["status"] or r.get("comment"):
                review(ws, r["id"], r["status"], r["reviewer"], r.get("comment", ""), model, reviewers)
                n += 1
    return n


def export_datasets(ws, xlsx=False):
    ws = Path(ws)
    tests = [t for t in load_json(ws / "tests.json") if t.get("data_rows") and t["status"] != "Rejeté"]
    out = ws / "datasets"
    by = {}
    for t in tests:
        by.setdefault(t["story_id"], []).append(t)
    book = None
    if xlsx:
        try:
            import openpyxl
        except ImportError:
            raise SystemExit("openpyxl requis pour --xlsx (pip install openpyxl)")
        book = openpyxl.Workbook()
        book.remove(book.active)
    for sid, ts in by.items():
        rows = [dict(test_id=t["id"], **r) for t in ts for r in t["data_rows"]]
        cols = ["test_id"] + sorted({k for r in rows for k in r if k != "test_id"})
        out.mkdir(exist_ok=True)
        with open(out / f"{sid}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, delimiter=";")
            w.writeheader()
            w.writerows(rows)
        if book is not None:
            sheet = book.create_sheet(sid[:31])
            sheet.append(cols)
            for r in rows:
                sheet.append([r.get(c, "") for c in cols])
    if book is not None and by:
        book.save(out / "datasets.xlsx")
    return sorted(by)


def link_defect(ws, test_id, url, by):
    """Rattache une anomalie (URL ELM/GitLab) à un test ; sera reliée au Test Case à la prochaine publication."""
    ws = Path(ws)
    tests = load_json(ws / "tests.json")
    t = next((x for x in tests if x["id"] == test_id), None)
    if not t:
        raise SystemExit(f"test inconnu: {test_id}")
    if url not in t.setdefault("defects", []):
        t["defects"].append(url)
    save_json(ws / "tests.json", tests)
    audit.log(ws, "link-defect", by, test=test_id, defect=url)


def ingest_refs(ws, path):
    """Référentiel SSS / SSDD : colonnes id;doc;title;url (CSV) ou liste JSON. Résolu à la publication."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        rows = json.loads(p.read_text(encoding="utf-8"))
    else:
        with open(p, encoding="utf-8-sig", newline="") as f:
            head = f.readline()
            f.seek(0)
            rows = list(csv.DictReader(f, delimiter=";" if ";" in head else ","))
    refs = load_json(Path(ws) / "refs.json", {})
    for r in rows:
        if not r.get("id"):
            raise SystemExit(f"ligne sans id: {r}")
        refs[r["id"]] = {"doc": r.get("doc", ""), "title": r.get("title", ""), "url": r.get("url", "")}
    save_json(Path(ws) / "refs.json", refs)
    audit.log(ws, "ingest-refs", "ingestion", source=str(path), count=len(rows))
    return len(rows)
