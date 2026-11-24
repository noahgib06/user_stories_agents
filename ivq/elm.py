"""Agent Adaptateur ELM : publication OSLC QM (Test Script, Test Case, Test Suite) avec garde-fous.

Par défaut : dry-run (génère les payloads RDF/XML dans workspace/elm_out). La publication réelle exige
--confirm, ELM_ENV=recette, un projet autorisé, une URL non-production et des tests au statut Validé.
Les URL des fabriques de création et les prédicats sont à valider sur votre serveur QM (voir README).
"""
import base64
import os
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

from . import audit
from .model import load_json, save_json

NS = ('xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
      'xmlns:dcterms="http://purl.org/dc/terms/" '
      'xmlns:oslc="http://open-services.net/ns/core#" '
      'xmlns:oslc_qm="http://open-services.net/ns/qm#" '
      'xmlns:ivq="urn:ivq:agents#"')


def _rdf(kind, props):
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<rdf:RDF {NS}>\n  <oslc_qm:{kind}>\n{props}  </oslc_qm:{kind}>\n</rdf:RDF>\n'


def _lit(tag, v):
    return f"    <{tag}>{escape(str(v))}</{tag}>\n"


def _res(tag, url):
    return f'    <{tag} rdf:resource="{escape(url)}"/>\n'


def _trace(t):
    g = t["generator"]
    return (_lit("ivq:sourceStory", f"{t['story_id']} v{t['story_version']}") +
            _lit("ivq:serviceFunction", t.get("service_function", "")) +
            _lit("ivq:softwareVersion", t.get("software_version", "")) +
            _lit("ivq:generator", f"{g.get('agent', '')}/{g.get('model', '')}") +
            _lit("ivq:reviewedBy", (t.get("review") or {}).get("by", "")) +
            _lit("ivq:testVersion", t["version"]))


def script_payload(t):
    body = "\n".join(f"{i}. {s['action']}" + (f" [données: {s['data']}]" if s.get("data") else "") +
                     f"\n   Résultat attendu: {s['expected']}" for i, s in enumerate(t["steps"], 1))
    pre = "\n".join(t.get("preconditions") or [])
    return _rdf("TestScript", _lit("dcterms:title", f"SCRIPT {t['id']}") +
                _lit("dcterms:description", f"Préconditions:\n{pre}\n\n{body}") + _trace(t))


def case_payload(t, req_url, script_url=None):
    p = (_lit("dcterms:title", t["title"]) + _lit("dcterms:identifier", t["id"]) +
         _lit("dcterms:description", t.get("description", "")) +
         _lit("ivq:priority", t["priority"]) + _lit("ivq:type", t["type"]) + _lit("ivq:category", t["category"]) +
         _lit("ivq:owner", t.get("owner", "")) + _res("oslc_qm:validatesRequirement", req_url) + _trace(t))
    if script_url:
        p += _res("oslc_qm:usesTestScript", script_url)
    return _rdf("TestCase", p)


def suite_payload(name, case_urls):
    return _rdf("TestSuite", _lit("dcterms:title", name) + "".join(_res("oslc_qm:usesTestCase", u) for u in case_urls))


def check_guards(cfg, live):
    errs = []
    url = cfg.get("base_url", "").lower()
    if cfg.get("project_area") not in cfg.get("allowed_project_areas", []):
        errs.append("project_area absent de allowed_project_areas")
    if any(x in url for x in cfg.get("forbidden_url_substrings", ["prod"])):
        errs.append("l'URL ELM ressemble à de la production : refusé")
    if live:
        if os.environ.get("ELM_ENV") != "recette":
            errs.append("ELM_ENV=recette requis pour publier")
        if not (os.environ.get("ELM_USER") and os.environ.get("ELM_PASSWORD")):
            errs.append("ELM_USER / ELM_PASSWORD (compte technique) requis")
    return errs


def _post(factory, payload):
    tok = base64.b64encode(f"{os.environ['ELM_USER']}:{os.environ['ELM_PASSWORD']}".encode()).decode()
    req = urllib.request.Request(factory, data=payload.encode("utf-8"), method="POST", headers={
        "Content-Type": "application/rdf+xml", "Accept": "application/rdf+xml",
        "OSLC-Core-Version": "2.0", "Authorization": f"Basic {tok}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.headers.get("Location", "")


def publish(ws, cfg, live=False, with_suites=True):
    ws = Path(ws)
    errs = check_guards(cfg, live)
    if errs:
        raise SystemExit("Publication bloquée:\n- " + "\n- ".join(errs))
    stories = {s["id"]: s for s in load_json(ws / "stories.json")}
    tests = load_json(ws / "tests.json")
    out = ws / "elm_out"
    out.mkdir(exist_ok=True)
    report = {"published": [], "skipped": [], "live": live}
    suites = {}
    for t in tests:
        if t["status"] != "Validé":
            report["skipped"].append({"id": t["id"], "reason": f"statut {t['status']}"})
            continue
        if not (t.get("review") or {}).get("by") or t["review"]["version"] != t["version"]:
            report["skipped"].append({"id": t["id"], "reason": "validation humaine absente pour cette version"})
            continue
        if (t.get("elm") or {}).get("published_version") == t["version"]:
            report["skipped"].append({"id": t["id"], "reason": "déjà publié (même version)"})
            continue
        st = stories[t["story_id"]]
        req_url = st.get("requirement_url") or cfg["requirement_base_url"] + st["id"]
        sp, cp = script_payload(t), case_payload(t, req_url)
        (out / f"{t['id']}.script.rdf").write_text(sp, encoding="utf-8")
        script_url = case_url = None
        if live:
            script_url = _post(cfg["creation_factories"]["testscript"], sp)
            cp = case_payload(t, req_url, script_url)
            case_url = _post(cfg["creation_factories"]["testcase"], cp)
            t["elm"] = {"published_version": t["version"], "testcase": case_url, "testscript": script_url,
                        "project_area": cfg["project_area"]}
            audit.log(ws, "publish", "adaptateur-elm", test=t["id"], version=t["version"],
                      testcase=case_url, project_area=cfg["project_area"], status="publié")
            save_json(ws / "tests.json", tests)  # persiste au fur et à mesure (reprise sur erreur)
        (out / f"{t['id']}.case.rdf").write_text(cp, encoding="utf-8")
        suites.setdefault(t.get("service_function") or "SANS-FONCTION", []).append(case_url or f"urn:dry-run:{t['id']}")
        report["published"].append({"id": t["id"], "version": t["version"], "requirement": req_url, "testcase": case_url})
    if with_suites:
        for fn, urls in suites.items():
            sp = suite_payload(f"Suite - {fn}", urls)
            (out / f"suite-{fn}.rdf".replace(" ", "_")).write_text(sp, encoding="utf-8")
            if live:
                audit.log(ws, "publish-suite", "adaptateur-elm", suite=fn,
                          url=_post(cfg["creation_factories"]["testsuite"], sp))
    if not live:
        audit.log(ws, "publish-dry-run", "adaptateur-elm", count=len(report["published"]))
    save_json(ws / "publish_report.json", report)
    return report
