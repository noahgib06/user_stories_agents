"""Détecte l'état du pipeline et la prochaine action (utilisé par l'orchestrateur : « fais ton boulot »)."""
import hashlib
import json
from pathlib import Path

from .model import ROOT, load_json

DIRECT = {".csv", ".xlsx", ".json"}
EXTRACT = {".docx", ".reqif"}
IGNORED = {".gitkeep", "readme.md"}


def _ingested_hashes(ws):
    p = Path(ws) / "journal.jsonl"
    if not p.exists():
        return set()
    out = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e.get("action") == "ingest" and e.get("sha256"):
            out.add(e["sha256"])
    return out


def _sources(ws, sources_dir):
    done = _ingested_hashes(ws)
    new = []
    for f in sorted(Path(sources_dir).glob("*")):
        if not f.is_file() or f.name.lower() in IGNORED:
            continue
        if hashlib.sha256(f.read_bytes()).hexdigest() in done:
            continue
        new.append({"file": str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else str(f),
                    "how": "ingest" if f.suffix.lower() in DIRECT else "extract_then_agent" if f.suffix.lower() in EXTRACT else "agent_ingestion"})
    return new


def compute(ws, sources_dir=None):
    ws = Path(ws)
    sources_dir = sources_dir or ROOT / "sources"
    stories = load_json(ws / "stories.json", [])
    tests = load_json(ws / "tests.json", [])
    new_sources = _sources(ws, sources_dir)
    todo = []

    if new_sources:
        todo.append({"step": "ingestion", "who": "agents", "sources": new_sources})
    if not stories and not new_sources:
        return {"step": "attente_sources", "who": "humain",
                "message": "Aucune source : déposer des fichiers dans sources/ (ou indiquer un projet GitLab).", "todo": []}

    by_story = {}
    for t in tests:
        by_story.setdefault(t["story_id"], []).append(t)
    needs_tests = [s["id"] for s in stories if s.get("kind") != "macro"
                   and (s["id"] not in by_story
                        or any(str(t.get("story_version")) != str(s.get("version")) for t in by_story[s["id"]]))]
    if needs_tests:
        todo.append({"step": "analyse+generation", "who": "agents", "stories": needs_tests})

    cov = ws / "coverage.json"
    tj = ws / "tests.json"
    if tests and not needs_tests and (not cov.exists() or (tj.exists() and cov.stat().st_mtime < tj.stat().st_mtime)):
        todo.append({"step": "couverture", "who": "agents"})

    if todo:
        return {"step": todo[0]["step"], "who": "agents", "todo": todo}

    draft = [t["id"] for t in tests if t["status"] == "Brouillon"]
    if draft:
        return {"step": "validation_humaine", "who": "humain", "pending": len(draft),
                "message": "Relire workspace/review.csv puis review-set / review-apply (jamais fait par un agent).", "todo": []}

    ready = [t["id"] for t in tests if t["status"] == "Validé"
             and (t.get("elm") or {}).get("published_version") != t["version"]]
    if ready:
        return {"step": "publication", "who": "agents", "ready": len(ready),
                "message": "Dry-run par défaut ; publish --confirm uniquement sur ordre explicite de l'humain.", "todo": []}
    return {"step": "termine", "who": "-", "message": "Rien à faire : tout est à jour.", "todo": []}
