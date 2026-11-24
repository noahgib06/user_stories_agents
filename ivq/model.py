"""Modèles de données, validation et E/S JSON (stdlib uniquement)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "config" / "test-model.json"


def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        if default is not None:
            return default
        raise FileNotFoundError(p)
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_model():
    return load_json(MODEL_PATH)


STORY_REQUIRED = ["id", "title", "version", "priority", "service_function", "acceptance_criteria"]


def validate_story(s):
    # un macro-US peut ne porter ni fonction de service ni critères propres (ils viennent de ses US filles)
    required = ["id", "title", "version", "priority"] if s.get("kind") == "macro" else STORY_REQUIRED
    errs = [f"champ manquant: {k}" for k in required if not s.get(k)]
    for i, c in enumerate(s.get("acceptance_criteria") or []):
        if not isinstance(c, dict) or not c.get("id") or not c.get("text"):
            errs.append(f"critère #{i} sans id/text")
    return errs


def validate_test(t, model, story_ids=None):
    errs = []
    for k in ["id", "title", "priority", "type", "category", "story_id", "story_version",
              "criteria_ids", "steps", "status", "version", "generator", "service_function"]:
        if t.get(k) in (None, "", []):
            errs.append(f"champ manquant: {k}")
    if errs:
        return errs
    if not re.match(model["naming"]["test_id_pattern"], t["id"]):
        errs.append(f"id non conforme au nommage: {t['id']}")
    else:
        code = model["naming"]["type_codes"].get(t["type"])
        if code and f"-{code}-" not in t["id"]:
            errs.append(f"code type {code} absent de l'id {t['id']}")
    for field, key in [("priority", "priorities"), ("type", "types"),
                       ("category", "categories"), ("status", "statuses")]:
        if t[field] not in model[key]:
            errs.append(f"{field} invalide: {t[field]}")
    if story_ids is not None and t["story_id"] not in story_ids:
        errs.append(f"story_id inconnue: {t['story_id']}")
    for i, st in enumerate(t["steps"], 1):
        if not st.get("action") or not st.get("expected"):
            errs.append(f"étape {i}: action/expected requis")
    return errs
