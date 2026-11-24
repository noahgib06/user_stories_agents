"""Agent Adaptateur ELM : publication OSLC QM (Test Plan, Test Script, Test Case, Test Suite, Execution Record).

Par défaut : dry-run (génère les payloads RDF/XML dans workspace/elm_out, aucun appel réseau). La publication réelle
exige --confirm, ELM_ENV=recette, un projet autorisé, une URL non-production et des tests au statut Validé.
Création (POST) ou mise à jour (PUT + If-Match/ETag) : un conflit ELM (412) n'écrase jamais l'artefact distant.
Authentification : Basic + repli sur le formulaire JAS (j_security_check). Les URL des fabriques et les prédicats sont
à valider sur votre serveur QM (voir README).
"""
import base64
import http.cookiejar
import json
import os
import urllib.error
import urllib.parse
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
DEFAULT_PREDICATES = {"story": "oslc_qm:validatesRequirement", "sss": "oslc_qm:validatesRequirement",
                      "ssdd": "oslc_qm:validatesRequirement", "macro": "oslc_qm:validatesRequirement"}
GROUP_KEYS = {"function": "service_function", "sprint": "sprint", "campaign": "campaign", "module": "module"}


class ElmError(SystemExit):
    pass


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


def case_payload(t, links, script_url=None):
    """links : liste de (prédicat, url) vers US / SSS / SSDD / macro-US."""
    p = (_lit("dcterms:title", t["title"]) + _lit("dcterms:identifier", t["id"]) +
         _lit("dcterms:description", t.get("description", "")) +
         _lit("ivq:priority", t["priority"]) + _lit("ivq:type", t["type"]) + _lit("ivq:category", t["category"]) +
         _lit("ivq:owner", t.get("owner", "")) + "".join(_res(pred, url) for pred, url in links) + _trace(t))
    p += "".join(_res("oslc_qm:relatedChangeRequest", d) for d in t.get("defects") or [])
    if script_url:
        p += _res("oslc_qm:usesTestScript", script_url)
    return _rdf("TestCase", p)


def suite_payload(name, case_urls):
    return _rdf("TestSuite", _lit("dcterms:title", name) + "".join(_res("oslc_qm:usesTestCase", u) for u in case_urls))


def plan_payload(name, case_urls):
    return _rdf("TestPlan", _lit("dcterms:title", name) + "".join(_res("oslc_qm:usesTestCase", u) for u in case_urls))


def execution_payload(t, case_url, plan_url=None):
    p = (_lit("dcterms:title", f"Exécution {t['id']} v{t['version']}") + _res("oslc_qm:runsTestCase", case_url) +
         _lit("ivq:softwareVersion", t.get("software_version", "")))
    if plan_url:
        p += _res("oslc_qm:reportsOnTestPlan", plan_url)
    return _rdf("TestExecutionRecord", p)


def check_guards(cfg, live, need=()):
    errs = []
    base = urllib.parse.urlparse(cfg.get("base_url", ""))
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
        if base.scheme != "https" and base.hostname not in ("localhost", "127.0.0.1"):
            errs.append("HTTPS requis")
        factories = cfg.get("creation_factories", {})
        for k in need:
            if not factories.get(k):
                errs.append(f"creation_factories.{k} manquant")
            elif urllib.parse.urlparse(factories[k]).netloc != base.netloc:
                errs.append(f"creation_factories.{k} n'est pas sur le serveur base_url")
    return errs


class Client:
    def __init__(self, cfg):
        self.cfg = cfg
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.user, self.password = os.environ["ELM_USER"], os.environ["ELM_PASSWORD"]
        self.basic = "Basic " + base64.b64encode(f"{self.user}:{self.password}".encode()).decode()

    def _jas_login(self):
        url = self.cfg.get("auth_url") or self.cfg["base_url"].rstrip("/") + "/j_security_check"
        body = urllib.parse.urlencode({"j_username": self.user, "j_password": self.password}).encode()
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with self.opener.open(req, timeout=60) as r:
            if r.headers.get("X-com-ibm-team-repository-web-auth-msg") == "authfailed":
                raise ElmError("authentification ELM refusée (compte technique)")

    def _open(self, method, url, data=None, headers=None, retry=True):
        h = {"OSLC-Core-Version": "2.0", "Accept": "application/rdf+xml", "Authorization": self.basic, **(headers or {})}
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            return self.opener.open(req, timeout=60)
        except urllib.error.HTTPError as e:
            if e.code == 401 and retry and e.headers.get("X-com-ibm-team-repository-web-auth-msg") == "authrequired":
                self._jas_login()
                return self._open(method, url, data, headers, retry=False)
            if e.code == 412:
                raise ElmError(f"conflit: {url} a été modifié dans ELM depuis la dernière lecture; rien n'a été écrasé")
            raise ElmError(f"ELM {method} {url} -> HTTP {e.code}")

    def post(self, factory, payload):
        with self._open("POST", factory, payload.encode("utf-8"), {"Content-Type": "application/rdf+xml"}) as r:
            loc = r.headers.get("Location", "")
        if not loc:
            raise ElmError(f"ELM n'a pas renvoyé de Location pour {factory}")
        return loc

    def put(self, url, payload):
        with self._open("GET", url) as r:
            etag = r.headers.get("ETag")
        if not etag:
            raise ElmError(f"pas d'ETag sur {url} : mise à jour refusée")
        with self._open("PUT", url, payload.encode("utf-8"), {"Content-Type": "application/rdf+xml", "If-Match": etag}):
            pass
        return url


def _req_links(story, refs, cfg):
    preds = {**DEFAULT_PREDICATES, **cfg.get("link_predicates", {})}
    base = cfg.get("requirement_base_url", "")

    def url(rid):
        return (refs.get(rid) or {}).get("url") or base + rid

    links = [(preds["story"], story.get("requirement_url") or base + story["id"])]
    links += [(preds["sss"], url(r)) for r in story.get("sss_refs") or []]
    links += [(preds["ssdd"], url(r)) for r in story.get("ssdd_refs") or []]
    if story.get("parent"):
        links.append((preds["macro"], base + story["parent"]))
    return list(dict.fromkeys(links))


def _fingerprint(t):
    return f"{t['version']}|{','.join(sorted(t.get('defects') or []))}"


def _group_key(t, story, attr):
    v = t.get(attr) if attr == "software_version" else (t.get("service_function") if attr == "service_function" else story.get(attr))
    return v or f"SANS-{attr.upper()}"


def publish(ws, cfg, live=False, with_suites=True, with_plan=True, with_executions=False, group_by=None):
    ws = Path(ws)
    group_by = group_by or cfg.get("suite_group_by", "function")
    if group_by not in GROUP_KEYS:
        raise SystemExit(f"group_by invalide: {group_by} ({', '.join(GROUP_KEYS)})")
    need = ["testscript", "testcase"] + (["testsuite"] if with_suites else []) + (["testplan"] if with_plan else []) + \
           (["testexecutionrecord"] if with_executions else [])
    errs = check_guards(cfg, live, need)
    if errs:
        raise SystemExit("Publication bloquée:\n- " + "\n- ".join(errs))
    stories = {s["id"]: s for s in load_json(ws / "stories.json")}
    refs = load_json(ws / "refs.json", {})
    tests = load_json(ws / "tests.json")
    out = ws / "elm_out"
    out.mkdir(exist_ok=True)
    fac = cfg.get("creation_factories", {})
    client = Client(cfg) if live else None
    state = load_json(ws / "elm_state.json", {"plans": {}, "suites": {}})
    report = {"live": live, "published": [], "skipped": [], "plans": [], "suites": [], "executions": []}

    def send(kind, existing, payload, name):
        (out / name).write_text(payload, encoding="utf-8")
        if not live:
            return existing or f"urn:dry-run:{name}", "dry-run"
        if existing:
            return client.put(existing, payload), "updated"
        return client.post(fac[kind], payload), "created"

    for t in tests:
        elm = t.get("elm") or {}
        if t["status"] != "Validé":
            report["skipped"].append({"id": t["id"], "reason": f"statut {t['status']}"})
        elif not (t.get("review") or {}).get("by") or t["review"]["version"] != t["version"]:
            report["skipped"].append({"id": t["id"], "reason": "validation humaine absente pour cette version"})
        elif elm.get("fingerprint") == _fingerprint(t):
            report["skipped"].append({"id": t["id"], "reason": "déjà publié (même version)"})
        else:
            story = stories[t["story_id"]]
            links = _req_links(story, refs, cfg)
            script_url, a1 = send("testscript", elm.get("testscript"), script_payload(t), f"{t['id']}.script.rdf")
            case_url, action = send("testcase", elm.get("testcase"), case_payload(t, links, script_url), f"{t['id']}.case.rdf")
            if live:
                t["elm"] = {**elm, "fingerprint": _fingerprint(t), "published_version": t["version"],
                            "testcase": case_url, "testscript": script_url, "project_area": cfg["project_area"]}
                save_json(ws / "tests.json", tests)  # persiste au fur et à mesure (reprise sur erreur)
                audit.log(ws, "publish", "adaptateur-elm", test=t["id"], version=t["version"], testcase=case_url,
                          op=action, project_area=cfg["project_area"], status="publié",
                          links=[u for _, u in links])
            else:
                t.setdefault("_dry", {})["testcase"] = case_url
            report["published"].append({"id": t["id"], "version": t["version"], "action": action,
                                        "links": [u for _, u in links], "testcase": case_url if live else None})

    def case_of(t):
        return (t.get("elm") or {}).get("testcase") or (t.get("_dry") or {}).get("testcase")

    def groups(attr):
        g = {}
        for t in tests:
            if t["status"] != "Rejeté" and case_of(t):
                g.setdefault(_group_key(t, stories.get(t["story_id"], {}), attr), []).append(t)
        return g

    def sync(bucket, kind, label, payload_fn, grp, report_key):
        urls_by_key = {}
        for key, ts in grp.items():
            cases = sorted(case_of(t) for t in ts)
            cur = state[bucket].get(key, {})
            if live and cur.get("cases") == cases:
                urls_by_key[key] = cur["url"]
                continue
            safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
            url, action = send(kind, cur.get("url"), payload_fn(f"{label} - {key}", cases), f"{kind}-{safe}.rdf")
            if live:
                state[bucket][key] = {"url": url, "cases": cases}
                save_json(ws / "elm_state.json", state)
                audit.log(ws, f"publish-{kind}", "adaptateur-elm", key=key, url=url, op=action, cases=len(cases))
            urls_by_key[key] = url
            report[report_key].append({"key": key, "url": url, "action": action, "cases": len(cases)})
        return urls_by_key

    plan_urls = {}
    if with_plan:
        plan_by = cfg.get("plan_by", "campaign")
        grp = {}
        for t in tests:
            if t["status"] != "Rejeté" and case_of(t):
                st = stories.get(t["story_id"], {})
                grp.setdefault(st.get(plan_by) or t.get("software_version") or "DEFAUT", []).append(t)
        plan_urls = sync("plans", "testplan", "Plan de test", plan_payload, grp, "plans")
    if with_suites:
        sync("suites", "testsuite", "Suite", suite_payload, groups(GROUP_KEYS[group_by]), "suites")

    if with_executions:
        plan_of = {t["id"]: plan_urls.get((stories.get(t["story_id"], {}).get(cfg.get("plan_by", "campaign"))
                                           or t.get("software_version") or "DEFAUT")) for t in tests}
        for t in tests:
            if t["status"] == "Rejeté" or not case_of(t) or (t.get("elm") or {}).get("execution_record"):
                continue
            url, action = send("testexecutionrecord", None, execution_payload(t, case_of(t), plan_of[t["id"]]),
                               f"{t['id']}.execution.rdf")
            if live:
                t["elm"]["execution_record"] = url
                save_json(ws / "tests.json", tests)
                audit.log(ws, "publish-execution", "adaptateur-elm", test=t["id"], url=url)
            report["executions"].append({"id": t["id"], "url": url, "action": action})

    if not live:
        audit.log(ws, "publish-dry-run", "adaptateur-elm", count=len(report["published"]))
    save_json(ws / "publish_report.json", report)
    return report
