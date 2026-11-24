"""Agent Couverture & Qualité (partie déterministe) : traçabilité, trous, doublons, ambiguïtés."""
import re
from difflib import SequenceMatcher


def _ambiguous(text):
    return any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text.lower()) for w in AMBIGUOUS)


AMBIGUOUS = ["etc", "...", "approprié", "correct", "rapide", "rapidement", "convenable", "si besoin",
             "éventuellement", "le cas échéant", "normalement", "quelques", "fast", "properly"]


def _sig(t):
    return " ".join(f"{s['action']} {s['expected']}" for s in t["steps"]).lower()


def analyse(stories, tests, model, refs=None):
    active = [t for t in tests if t["status"] != "Rejeté"]
    anomalies, rows = [], []
    by_crit = {}
    for t in active:
        for c in t["criteria_ids"]:
            by_crit.setdefault(c, []).append(t)
    known_crit = {c["id"] for s in stories for c in s["acceptance_criteria"]}
    ids = {s["id"] for s in stories}
    trace = model.get("traceability", {})
    for s in stories:
        macro = s.get("kind") == "macro"
        types = {t["type"] for t in active if t["story_id"] == s["id"]}
        if s.get("parent") and s["parent"] not in ids:
            anomalies.append({"severity": "majeure", "kind": "traçabilité", "story": s["id"],
                              "detail": f"macro-US parente inconnue: {s['parent']}"})
        for kind, key in (("SSS", "sss_refs"), ("SSDD", "ssdd_refs")):
            if not macro and trace.get(f"require_{kind.lower()}") and not s.get(key):
                anomalies.append({"severity": "majeure", "kind": "traçabilité", "story": s["id"],
                                  "detail": f"aucun lien {kind} renseigné"})
            for r in s.get(key) or []:
                if refs is not None and r not in refs:
                    anomalies.append({"severity": "majeure", "kind": "traçabilité", "story": s["id"],
                                      "detail": f"référence {kind} inconnue du référentiel: {r}"})
        for m in ([] if macro else model["matrix"]["mandatory_types"]):
            if m not in types:
                anomalies.append({"severity": "majeure", "kind": "matrice", "story": s["id"],
                                  "detail": f"type obligatoire absent: {m}"})
        if not macro and s.get("actor") and "securite" not in types:
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
            if _ambiguous(c["text"]):
                anomalies.append({"severity": "mineure", "kind": "ambigu", "story": s["id"],
                                  "detail": f"critère ambigu {c['id']}: à clarifier avec le PO"})
    for s in stories:
        if s.get("kind") != "macro":
            continue
        kids = [c["id"] for c in stories if c.get("parent") == s["id"]]
        if not kids:
            anomalies.append({"severity": "majeure", "kind": "traçabilité", "story": s["id"],
                              "detail": "macro-US sans US fille"})
            continue
        states = [r["state"] for r in rows if r["story"] in kids]
        state = ("non couvert" if not states or "non couvert" in states else
                 "en attente de validation" if "en attente de validation" in states else "couvert")
        rows.append({"story": s["id"], "story_version": s["version"], "service_function": "",
                     "criterion": f"(US filles: {', '.join(kids)})", "state": state, "tests": [], "rollup": True})
        if state != "couvert":
            anomalies.append({"severity": "majeure", "kind": "trou", "story": s["id"],
                              "detail": f"macro-US {state} (US filles incomplètes)"})
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
            if _ambiguous(st["expected"] or "") or len(st["expected"].split()) < 2:
                anomalies.append({"severity": "mineure", "kind": "ambigu", "test": t["id"],
                                  "detail": "résultat attendu vague ou trop court"})
                break
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if a["story_id"] == b["story_id"] and a["type"] == b["type"] and \
               SequenceMatcher(None, _sig(a), _sig(b)).ratio() > 0.85:
                anomalies.append({"severity": "mineure", "kind": "doublon", "test": a["id"],
                                  "detail": f"redondant avec {b['id']}"})
    counted = [r for r in rows if not r.get("rollup")]
    n = len(counted)
    cov = sum(r["state"] == "couvert" for r in counted)
    pend = sum(r["state"] == "en attente de validation" for r in counted)
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


TRACE_COLUMNS = ["story", "story_version", "macro_us", "service_function", "sss", "ssdd", "criterion", "test", "test_version",
                 "status", "software_version", "generator", "reviewer", "elm_testcase", "elm_execution_record", "defects"]


def trace_rows(stories, tests):
    """Chaîne US -> fonction de service -> critère -> test -> exécution -> anomalie."""
    by_story = {s["id"]: s for s in stories}
    rows = []
    for t in tests:
        s = by_story.get(t["story_id"], {})
        elm = t.get("elm") or {}
        g = t.get("generator") or {}
        for c in t["criteria_ids"]:
            rows.append({"story": t["story_id"], "story_version": t["story_version"], "macro_us": s.get("parent", ""),
                         "service_function": t.get("service_function", ""), "sss": " | ".join(s.get("sss_refs") or []),
                         "ssdd": " | ".join(s.get("ssdd_refs") or []), "criterion": c, "test": t["id"],
                         "test_version": t["version"], "status": t["status"],
                         "software_version": t.get("software_version", ""),
                         "generator": f"{g.get('agent', '')}/{g.get('model', '')}",
                         "reviewer": (t.get("review") or {}).get("by", ""), "elm_testcase": elm.get("testcase", ""),
                         "elm_execution_record": elm.get("execution_record", ""),
                         "defects": " | ".join(t.get("defects") or [])})
    return rows
