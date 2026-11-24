import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs

from ivq import cli, coverage, elm, ingest, store
from ivq.model import ROOT, load_json, load_model

EX = ROOT / "examples"


class FakeElm(BaseHTTPRequestHandler):
    """Faux serveur QM : session JAS par formulaire, POST de création, GET/PUT avec ETag."""
    store, log, etags, counter = {}, [], {}, [0]
    conflict = False

    def log_message(self, *a):
        pass

    def _auth(self):
        if "JSESSIONID=ok" in (self.headers.get("Cookie") or ""):
            return True
        self.send_response(401)
        self.send_header("X-com-ibm-team-repository-web-auth-msg", "authrequired")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def _body(self):
        return self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()

    def do_POST(self):
        body = self._body()
        if self.path.endswith("/j_security_check"):
            ok = parse_qs(body).get("j_password") == [os.environ["ELM_PASSWORD"]]
            self.log.append("login")
            self.send_response(200)
            if ok:
                self.send_header("Set-Cookie", "JSESSIONID=ok; Path=/")
            self.send_header("Content-Length", "0")
            return self.end_headers()
        if not self._auth():
            return
        kind = self.path.rsplit("/", 1)[1]
        self.counter[0] += 1
        url = f"http://127.0.0.1:{self.server.server_port}/qm/res/{kind}/{self.counter[0]}"
        self.store[url], self.etags[url] = body, 1
        self.log.append(("POST", kind))
        self.send_response(201)
        self.send_header("Location", url)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self._auth():
            return
        url = f"http://127.0.0.1:{self.server.server_port}{self.path}"
        self.send_response(200)
        self.send_header("ETag", f'"{self.etags[url]}"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_PUT(self):
        body = self._body()
        if not self._auth():
            return
        url = f"http://127.0.0.1:{self.server.server_port}{self.path}"
        if self.conflict or self.headers.get("If-Match") != f'"{self.etags[url]}"':
            self.send_response(412)
            self.send_header("Content-Length", "0")
            return self.end_headers()
        self.store[url], self.etags[url] = body, self.etags[url] + 1
        self.log.append(("PUT", url.rsplit("/", 2)[1]))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


def serve(handler):
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.m = load_model()
        for a in (["ingest", str(EX / "stories.csv")], ["ingest-refs", str(EX / "refs.csv")]):
            cli.main(["-w", self.d] + a)
        store.merge(self.d, load_json(EX / "tests.proposed.json")["tests"], self.m, software_version="1.4.0")

    def validate_all(self):
        for t in load_json(Path(self.d) / "tests.json"):
            store.review(self.d, t["id"], "Validé", "po", "", self.m)


class LiveElm(Base):
    def setUp(self):
        super().setUp()
        FakeElm.store, FakeElm.log, FakeElm.etags, FakeElm.counter, FakeElm.conflict = {}, [], {}, [0], False
        self.srv = serve(FakeElm)
        self.addCleanup(self.srv.shutdown)
        base = f"http://127.0.0.1:{self.srv.server_port}/qm"
        self.cfg = {"base_url": base, "project_area": "RECETTE", "allowed_project_areas": ["RECETTE"],
                    "requirement_base_url": "https://elm-recette.example.org/rm/resources/",
                    "creation_factories": {k: f"{base}/factory/{k}" for k in
                                           ("testplan", "testcase", "testscript", "testsuite", "testexecutionrecord")}}
        env = mock.patch.dict(os.environ, {"ELM_ENV": "recette", "ELM_USER": "svc", "ELM_PASSWORD": "pw"})
        env.start()
        self.addCleanup(env.stop)
        self.validate_all()

    def count(self, op, kind=None):
        return sum(1 for e in FakeElm.log if isinstance(e, tuple) and e[0] == op and (kind is None or e[1] == kind))

    def test_full_publication_update_defect_and_conflict(self):
        rep = elm.publish(self.d, self.cfg, live=True, with_executions=True)
        self.assertEqual((len(rep["published"]), len(rep["plans"]), len(rep["suites"]), len(rep["executions"])), (2, 1, 1, 2))
        self.assertEqual(FakeElm.log.count("login"), 1)  # repli JAS une seule fois
        case = next(v for k, v in FakeElm.store.items() if "/testcase/" in k)
        for ref in ("rm/resources/US-101", "rm/resources/SSS-045", "rm/resources/SSDD-210", "rm/resources/MUS-100", "usesTestScript"):
            self.assertIn(ref, case)
        self.assertIn("reportsOnTestPlan", next(v for k, v in FakeElm.store.items() if "/testexecutionrecord/" in k))

        elm.publish(self.d, self.cfg, live=True, with_executions=True)  # idempotent
        self.assertEqual(self.count("PUT"), 0)

        props = load_json(EX / "tests.proposed.json")["tests"]
        props[0]["steps"][0]["expected"] = "Le tableau de bord personnalisé s'affiche"
        store.merge(self.d, props, self.m)
        store.review(self.d, "TC-US-101-NOM-01", "Validé", "po", "", self.m)
        rep = elm.publish(self.d, self.cfg, live=True)
        self.assertEqual((self.count("PUT", "testscript"), self.count("PUT", "testcase"), self.count("POST", "testcase")), (1, 1, 2))
        self.assertEqual(rep["published"][0]["action"], "updated")

        store.link_defect(self.d, "TC-US-101-NOM-01", "https://elm-recette.example.org/ccm/resources/DEF-9", "ivq")
        elm.publish(self.d, self.cfg, live=True)
        self.assertIn("relatedChangeRequest", next(v for k, v in FakeElm.store.items() if "/testcase/1" in k or k.endswith("testcase/2")) +
                      "".join(FakeElm.store.values()))

        store.link_defect(self.d, "TC-US-101-NOM-01", "https://elm-recette.example.org/ccm/resources/DEF-10", "ivq")
        FakeElm.conflict = True
        before = load_json(Path(self.d) / "tests.json")[0]["elm"]["fingerprint"]
        with self.assertRaises(SystemExit):
            elm.publish(self.d, self.cfg, live=True)
        self.assertEqual(load_json(Path(self.d) / "tests.json")[0]["elm"]["fingerprint"], before)

    def test_bad_password_and_foreign_factory(self):
        with mock.patch.dict(os.environ, {"ELM_PASSWORD": "pw"}):
            self.cfg["creation_factories"]["testcase"] = "http://evil.example.org/qm/factory/testcase"
            with self.assertRaises(SystemExit) as c:
                elm.publish(self.d, self.cfg, live=True)
            self.assertIn("base_url", str(c.exception))


class Features(Base):
    def test_macro_rollup_and_unknown_ref(self):
        stories = load_json(Path(self.d) / "stories.json")
        tests = load_json(Path(self.d) / "tests.json")
        rep = coverage.analyse(stories, tests, self.m, refs={})
        macro = next(r for r in rep["criteria"] if r["story"] == "MUS-100")
        self.assertEqual(macro["state"], "non couvert")
        self.assertTrue(any("référence SSS inconnue" in a["detail"] for a in rep["anomalies"]))
        self.assertEqual(rep["summary"]["criteria"], 3)  # le roll-up n'est pas compté

    def test_reviewers_allowlist(self):
        f = Path(self.d) / "rv.json"
        f.write_text(json.dumps({"reviewers": [{"name": "Alice", "role": "IVQ"}]}))
        rv = store.load_reviewers(f)
        with self.assertRaises(SystemExit):
            store.review(self.d, "TC-US-101-NOM-01", "Validé", "Mallory", "", self.m, rv)
        store.review(self.d, "TC-US-101-NOM-01", "Validé", "Alice", "", self.m, rv)
        self.assertEqual(load_json(Path(self.d) / "tests.json")[0]["review"]["role"], "IVQ")

    def test_merge_traces_model_prompt_and_ignores_generator_changes(self):
        props = load_json(EX / "tests.proposed.json")["tests"]
        self.assertEqual(len(store.merge(self.d, props, self.m, model_name="m2")["unchanged"]), 2)
        props[0]["steps"][0]["expected"] = "Le tableau de bord personnalisé s'affiche"
        r = store.merge(self.d, props, self.m, model_name="m2", prompt="prompt X")
        self.assertEqual(r["updated"], ["TC-US-101-NOM-01"])
        t = load_json(Path(self.d) / "tests.json")[0]
        self.assertEqual(t["generator"]["model"], "m2")
        self.assertEqual(len(t["generator"]["prompt_sha256"]), 64)
        self.assertEqual(len(list((Path(self.d) / "prompts").glob("*.txt"))), 1)

    def test_next_step_follows_pipeline(self):
        from ivq import nextstep
        src = Path(tempfile.mkdtemp())
        self.assertEqual(nextstep.compute(self.d, src)["step"], "couverture")
        cli.main(["-w", self.d, "coverage"])
        self.assertEqual(nextstep.compute(self.d, src)["step"], "validation_humaine")
        (src / "nouvelles_us.csv").write_text((EX / "stories.csv").read_text(encoding="utf-8").replace("US-101", "US-102"), encoding="utf-8")
        (src / "spec.docx").write_bytes(b"x")
        r = nextstep.compute(self.d, src)
        self.assertEqual((r["step"], r["who"]), ("ingestion", "agents"))
        self.assertEqual({x["how"] for x in r["todo"][0]["sources"]}, {"ingest", "extract_then_agent"})
        cli.main(["-w", self.d, "ingest", str(src / "nouvelles_us.csv")])
        self.assertIn("US-102", nextstep.compute(self.d, src)["todo"][-1]["stories"])
        self.validate_all()
        self.assertEqual(nextstep.compute(self.d, Path(tempfile.mkdtemp()))["step"], "analyse+generation")

    def test_extract_docx_reqif_and_ambiguity(self):
        import zipfile
        d = Path(tempfile.mkdtemp())
        W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        with zipfile.ZipFile(d / "a.docx", "w") as z:
            z.writestr("word/document.xml", f"<w:document {W}><w:body><w:p><w:r><w:t>US-9 Connexion</w:t></w:r></w:p>"
                       "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>AC1</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>OK</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>")
        self.assertEqual(ingest.extract_text(d / "a.docx"), "US-9 Connexion\nAC1 | OK")
        (d / "b.reqif").write_text('<REQ-IF xmlns="http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"><SPEC-OBJECT IDENTIFIER="R1">'
                                   '<VALUES><ATTRIBUTE-VALUE-STRING THE-VALUE="Exigence un"/></VALUES></SPEC-OBJECT></REQ-IF>', encoding="utf-8")
        self.assertEqual(ingest.extract_text(d / "b.reqif"), "[R1] Exigence un")
        self.assertTrue(coverage._ambiguous("afficher si besoin."))
        self.assertFalse(coverage._ambiguous("fetch des données"))

    def test_review_csv_content_correction_bumps_version(self):
        out = Path(self.d) / "review.csv"
        store.export_review_csv(self.d, out)
        txt = out.read_text(encoding="utf-8-sig").replace(";Brouillon;;", ";Brouillon;Relecteur;", 1)
        first = load_json(Path(self.d) / "tests.json")[0]
        txt = txt.replace(first["title"], first["title"] + " (corrigé)", 1)
        out.write_text(txt, encoding="utf-8")
        store.apply_review_csv(self.d, out, self.m)
        t = next(x for x in load_json(Path(self.d) / "tests.json") if x["id"] == first["id"])
        self.assertEqual((t["version"], t["status"]), (2, "Brouillon"))
        self.assertTrue(t["title"].endswith("(corrigé)"))

    def test_group_by_sprint_dry_run_and_trace(self):
        self.validate_all()
        cfg = load_json(ROOT / "config" / "elm.example.json")
        rep = elm.publish(self.d, cfg, group_by="sprint")
        self.assertEqual([s["key"] for s in rep["suites"]], ["S12"])
        self.assertEqual([p["key"] for p in rep["plans"]], ["Recette R1"])
        cli.main(["-w", self.d, "trace"])
        self.assertIn("SSDD-210", (Path(self.d) / "traceability.csv").read_text(encoding="utf-8-sig"))

    def test_xlsx_ingest_and_datasets(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl absent")
        x = Path(self.d) / "s.xlsx"
        wb = openpyxl.Workbook()
        wb.active.append(["ID exigence", "Titre", "Version", "Priorité", "Fonction de service", "Critères d'acceptation"])
        wb.active.append(["US-7", "T", 3.0, "P2", "FS-X", "AC1: ok | AC2: ko"])
        wb.save(x)
        s = ingest.ingest(x)[0]
        self.assertEqual((s["version"], len(s["acceptance_criteria"])), ("3", 2))
        store.export_datasets(self.d, xlsx=True)
        self.assertTrue((Path(self.d) / "datasets" / "datasets.xlsx").exists())


class GitLabHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        page = parse_qs(self.path.split("?", 1)[1])["page"][0]
        item = {"iid": int(page), "title": f"Issue {page}", "updated_at": "2026-01-02T00:00:00Z", "web_url": "u",
                "labels": ["priority::P2", "sprint::S3"], "description": "- [ ] premier critère\n- [x] second critère"}
        body = json.dumps([item]).encode()
        self.send_response(200)
        self.send_header("X-Next-Page", "2" if page == "1" else "")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class GitLab(unittest.TestCase):
    def test_pagination_and_labels(self):
        srv = serve(GitLabHandler)
        self.addCleanup(srv.shutdown)
        with mock.patch.dict(os.environ, {"GITLAB_URL": f"http://127.0.0.1:{srv.server_port}", "GITLAB_TOKEN": "t"}):
            out = ingest.from_gitlab("grp/proj")
        self.assertEqual([s["id"] for s in out], ["GL-1", "GL-2"])
        self.assertEqual((out[0]["priority"], out[0]["sprint"], len(out[0]["acceptance_criteria"])), ("P2", "S3", 2))


if __name__ == "__main__":
    unittest.main()
