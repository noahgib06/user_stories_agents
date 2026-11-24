"""Agent Couverture & Qualité (partie déterministe) : traçabilité, trous, doublons, ambiguïtés."""
import re
from difflib import SequenceMatcher

AMBIGUOUS = ["etc", "...", "approprié", "correct", "rapide", "rapidement", "convenable", "si besoin",
             "éventuellement", "le cas échéant", "normalement", "quelques", "fast", "properly"]


def _sig(t):
    return " ".join(f"{s['action']} {s['expected']}" for s in t["steps"]).lower()


def analyse(stories, tests, model):
    active = [t for t in tests if t["status"] != "Rejeté"]
    anomalies, rows = [], []
    by_crit = {}
    for t in active:
        for c in t["criteria_ids"]:
            by_crit.setdefault(c, []).append(t)
    known_crit = {c["id"] for s in stories for c in s["acceptance_criteria"]}
    for s in stories:
        types = {t["type"] for t in active if t["story_id"] == s["id"]}
        for m in model["matrix"]["mandatory_types"]:
            if m not in types:
                anomalies.append({"severity": "majeure", "kind": "matrice", "story": s["id"],
                                  "detail": f"type obligatoire absent: {m}"})
        if s.get("actor") and "securite" not in types:
            anomalies.append({"severity": "mineure", "kind": "matrice", "story": s["id"],
                              "detail": "acteur défini mais aucun test sécurité/permissions"})
        for c in s["acceptance_criteria"]:
            ts = by_crit.get(c["id"], [])
            validated = [t for t in ts if t["status"] == "Validé"]
            state = "couvert" if validated else ("en attente de validation" if ts else "non couvert")
            rows.append({"story": s["id"], "story_version": s["version"], "service_function": s["service_function"],
                         "criterion": c["id"], "state": state, "tests": [t["id"] for t in ts]})
            if not ts:
                anomalies.append({"severity": "majeure", "kind": "trou", "story": s["id"],
                                  "detail": f"critère non couvert: {c['id']}"})
            if any(w in c["text"].lower() for w in AMBIGUOUS):
                anomalies.append({"severity": "mineure", "kind": "ambigu", "story": s["id"],
                                  "detail": f"critère ambigu {c['id']}: à clarifier avec le PO"})
    sv = {s["id"]: s["version"] for s in stories}
    for t in active:
        for c in t["criteria_ids"]:
            if c not in known_crit:
                anomalies.append({"severity": "majeure", "kind": "traçabilité", "test": t["id"],
                                  "detail": f"critère inconnu: {c}"})
        if t["story_id"] in sv and str(t["story_version"]) != str(sv[t["story_id"]]):
            anomalies.append({"severity": "majeure", "kind": "obsolète", "test": t["id"],
                              "detail": f"généré pour v{t['story_version']}, US en v{sv[t['story_id']]}"})
        for st in t["steps"]:
            if any(w in (st["expected"] or "").lower().split() for w in AMBIGUOUS) or len(st["expected"].split()) < 2:
                anomalies.append({"severity": "mineure", "kind": "ambigu", "test": t["id"],
                                  "detail": "résultat attendu vague ou trop court"})
                break
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if a["story_id"] == b["story_id"] and a["type"] == b["type"] and \
               SequenceMatcher(None, _sig(a), _sig(b)).ratio() > 0.85:
                anomalies.append({"severity": "mineure", "kind": "doublon", "test": a["id"],
                                  "detail": f"redondant avec {b['id']}"})
    n = len(rows)
    cov = sum(r["state"] == "couvert" for r in rows)
    pend = sum(r["state"] == "en attente de validation" for r in rows)
    return {"summary": {"criteria": n, "covered_validated": cov, "pending_validation": pend,
                        "uncovered": n - cov - pend, "tests": len(tests),
                        "by_status": {s: sum(t["status"] == s for t in tests) for s in model["statuses"]},
                        "anomalies": len(anomalies)},
            "criteria": rows, "anomalies": anomalies}


def to_markdown(rep):
    s = rep["summary"]
    out = ["# Rapport de couverture", "",
           f"- Critères : {s['criteria']} — couverts (validés) : {s['covered_validated']}, "
           f"en attente : {s['pending_validation']}, non couverts : {s['uncovered']}",
           f"- Tests : {s['tests']} {s['by_status']}", f"- Anomalies : {s['anomalies']}", "",
           "| US | Fonction | Critère | État | Tests |", "|---|---|---|---|---|"]
    out += [f"| {r['story']} v{r['story_version']} | {r['service_function']} | {r['criterion']} | {r['state']} | {', '.join(r['tests'])} |"
            for r in rep["criteria"]]
    out += ["", "## Anomalies", ""] + [f"- [{a['severity']}] {a['kind']} {a.get('story') or a.get('test')}: {a['detail']}"
                                       for a in rep["anomalies"]]
    return "\n".join(out) + "\n"
