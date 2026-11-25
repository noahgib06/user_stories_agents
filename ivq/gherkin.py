"""Export des tests en scénarios Gherkin (un .feature par US) dans workspace/features/."""
from pathlib import Path


def _one(line):
    return " ".join(str(line).split())


def feature_contents(stories, tests):
    """Renvoie [(story_id, texte Gherkin)] ; les tests rejetés sont exclus."""
    by_us = {}
    for t in tests:
        if t.get("status") == "Rejeté":
            continue
        by_us.setdefault(t["story_id"], []).append(t)
    titles = {s["id"]: s.get("title", "") for s in stories}
    out = []
    for sid in sorted(by_us):
        lines = [f"Feature: {sid} {titles.get(sid, '')}".rstrip()]
        for t in sorted(by_us[sid], key=lambda x: x["id"]):
            lines += ["", f"Scenario: {t['id']} - {_one(t.get('title', ''))}",
                      f"# Fonction de service : {t.get('service_function', '')} | critères : {', '.join(t.get('criteria_ids', []))}"
                      f" | statut : {t.get('status', 'Brouillon')}"]
            pre = [_one(p) for p in t.get("preconditions", [])]
            for i, p in enumerate(pre):
                lines.append(f"{'Given' if i == 0 else 'And'} {p}")
            for i, s in enumerate(t.get("steps", [])):
                data = f" ({_one(s['data'])})" if s.get("data") else ""
                lines.append(f"{'When' if i == 0 else 'And'} {_one(s.get('action', ''))}{data}")
                if s.get("expected"):
                    lines.append(f"Then {_one(s['expected'])}")
        out.append((sid, "\n".join(lines) + "\n"))
    return out


def build(ws, stories, tests):
    d = Path(ws) / "features"
    blocks = feature_contents(stories, tests)
    if blocks:
        d.mkdir(parents=True, exist_ok=True)
    files = []
    for sid, content in blocks:
        p = d / f"{sid}.feature"
        p.write_text(content, encoding="utf-8")
        files.append(str(p))
    return files
