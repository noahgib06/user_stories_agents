import json
import tempfile
import unittest
from pathlib import Path

from ivq import cli, coverage, elm, store
from ivq.model import ROOT, load_json, load_model

EX = ROOT / "examples"


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.m = load_model()
        cli.main(["-w", self.d, "ingest", str(EX / "stories.csv")])
        self.props = load_json(EX / "tests.proposed.json")["tests"]

    def test_ingest_criteria_ids(self):
        s = load_json(Path(self.d) / "stories.json")[0]
        self.assertEqual([c["id"] for c in s["acceptance_criteria"]], ["US-101-AC1", "US-101-AC2", "US-101-AC3"])
        self.assertEqual(len(s["inputs"]), 2)

    def test_merge_forces_draft_and_versions(self):
        self.props[0]["status"] = "Validé"
        store.merge(self.d, self.props, self.m)
        t = load_json(Path(self.d) / "tests.json")[0]
        self.assertEqual(t["status"], "Brouillon")
        store.review(self.d, t["id"], "Validé", "po", "", self.m)
        self.props[0]["steps"][0]["expected"] = "Le tableau de bord personnalisé s'affiche"
        r = store.merge(self.d, self.props, self.m)
        t = load_json(Path(self.d) / "tests.json")[0]
        self.assertEqual((r["updated"], t["version"], t["status"], len(t["history"])), (["TC-US-101-NOM-01"], 2, "Brouillon", 1))

    def test_merge_rejects_bad_id(self):
        self.props[0]["id"] = "bad"
        self.assertIn("bad", store.merge(self.d, self.props, self.m)["rejected"])

    def test_coverage_gap_and_pending(self):
        store.merge(self.d, self.props, self.m)
        rep = coverage.analyse(load_json(Path(self.d) / "stories.json"), load_json(Path(self.d) / "tests.json"), self.m)
        self.assertEqual(rep["summary"]["uncovered"], 1)
        self.assertEqual(rep["summary"]["pending_validation"], 2)

    def test_publish_guards_and_dry_run(self):
        store.merge(self.d, self.props, self.m)
        cfg = load_json(ROOT / "config" / "elm.example.json")
        self.assertEqual(elm.publish(self.d, cfg)["published"], [])  # rien de validé
        store.review(self.d, "TC-US-101-NOM-01", "Validé", "po", "", self.m)
        rep = elm.publish(self.d, cfg)
        self.assertEqual([p["id"] for p in rep["published"]], ["TC-US-101-NOM-01"])
        self.assertIn("validatesRequirement", (Path(self.d) / "elm_out" / "TC-US-101-NOM-01.case.rdf").read_text())
        with self.assertRaises(SystemExit):
            elm.publish(self.d, cfg, live=True)  # ELM_ENV absent
        with self.assertRaises(SystemExit):
            elm.publish(self.d, dict(cfg, base_url="https://elm-prod.example.org/qm"))

    def test_audit_chain(self):
        store.merge(self.d, self.props, self.m)
        self.assertEqual(cli.main(["-w", self.d, "audit-verify"]), 0)
        j = Path(self.d) / "journal.jsonl"
        j.write_text(j.read_text().replace("merge", "mergX", 1))
        self.assertEqual(cli.main(["-w", self.d, "audit-verify"]), 1)


if __name__ == "__main__":
    unittest.main()
