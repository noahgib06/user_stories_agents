"""CLI déterministe utilisé par les agents opencode : python3 -m ivq <commande>."""
import argparse
import json
import sys
from pathlib import Path

from . import audit, coverage, elm, ingest, store
from .model import ROOT, load_json, load_model, save_json, validate_story, validate_test


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ivq")
    ap.add_argument("-w", "--workspace", default=str(ROOT / "workspace"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="CSV/XLSX/JSON -> workspace/stories.json")
    p.add_argument("source")
    p = sub.add_parser("ingest-gitlab")
    p.add_argument("project")
    p.add_argument("--labels")
    sub.add_parser("validate", help="valide stories.json et tests.json")
    p = sub.add_parser("merge", help="intègre des propositions de tests (statut forcé Brouillon)")
    p.add_argument("proposed", nargs="?", default=None)
    sub.add_parser("coverage", help="rapport de couverture + anomalies")
    p = sub.add_parser("review-export")
    p.add_argument("--out", default=None)
    p = sub.add_parser("review-apply")
    p.add_argument("csv")
    p = sub.add_parser("review-set")
    p.add_argument("test_id")
    p.add_argument("status")
    p.add_argument("--by", required=True)
    p.add_argument("--comment", default="")
    sub.add_parser("datasets")
    p = sub.add_parser("publish")
    p.add_argument("--config", default=str(ROOT / "config" / "elm.json"))
    p.add_argument("--confirm", action="store_true", help="publication réelle (sinon dry-run)")
    p = sub.add_parser("status")
    sub.add_parser("audit-verify")
    a = ap.parse_args(argv)

    ws = Path(a.workspace)
    model = load_model()

    if a.cmd in ("ingest", "ingest-gitlab"):
        new = ingest.ingest(a.source) if a.cmd == "ingest" else ingest.from_gitlab(a.project, a.labels)
        bad = {s.get("id", "?"): e for s in new if (e := validate_story(s))}
        cur = {s["id"]: s for s in load_json(ws / "stories.json", [])}
        for s in new:
            if s["id"] not in bad:
                cur[s["id"]] = s
        save_json(ws / "stories.json", list(cur.values()))
        audit.log(ws, "ingest", "ingestion", source=a.source if a.cmd == "ingest" else a.project,
                  ok=len(new) - len(bad), incomplete=list(bad))
        print(json.dumps({"ingested": len(new) - len(bad), "incomplete": bad}, ensure_ascii=False, indent=2))
        return 1 if bad else 0

    if a.cmd == "validate":
        stories = load_json(ws / "stories.json", [])
        tests = load_json(ws / "tests.json", [])
        sids = {s["id"] for s in stories}
        errs = {s["id"]: e for s in stories if (e := validate_story(s))}
        errs.update({t.get("id", "?"): e for t in tests if (e := validate_test(t, model, sids))})
        print(json.dumps(errs or "OK", ensure_ascii=False, indent=2))
        return 1 if errs else 0

    if a.cmd == "merge":
        src = Path(a.proposed or ws / "tests.proposed.json")
        data = load_json(src)
        res = store.merge(ws, data["tests"] if isinstance(data, dict) else data, model)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1 if res["rejected"] else 0

    if a.cmd == "coverage":
        rep = coverage.analyse(load_json(ws / "stories.json", []), load_json(ws / "tests.json", []), model)
        save_json(ws / "coverage.json", rep)
        (ws / "coverage.md").write_text(coverage.to_markdown(rep), encoding="utf-8")
        audit.log(ws, "coverage", "couverture", **rep["summary"])
        print(json.dumps(rep["summary"], ensure_ascii=False, indent=2))
        return 0

    if a.cmd == "review-export":
        out = a.out or str(ws / "review.csv")
        store.export_review_csv(ws, out)
        print(out)
        return 0
    if a.cmd == "review-apply":
        print(f"{store.apply_review_csv(ws, a.csv, model)} décision(s) appliquée(s)")
        return 0
    if a.cmd == "review-set":
        store.review(ws, a.test_id, a.status, a.by, a.comment, model)
        return 0
    if a.cmd == "datasets":
        print(store.export_datasets(ws))
        return 0

    if a.cmd == "publish":
        rep = elm.publish(ws, load_json(a.config), live=a.confirm)
        print(json.dumps({"live": rep["live"], "published": len(rep["published"]),
                          "skipped": rep["skipped"]}, ensure_ascii=False, indent=2))
        return 0

    if a.cmd == "status":
        tests = load_json(ws / "tests.json", [])
        print(json.dumps({"stories": len(load_json(ws / "stories.json", [])), "tests": len(tests),
                          "by_status": {s: sum(t["status"] == s for t in tests) for s in model["statuses"]},
                          "published": sum(bool(t.get("elm")) for t in tests)}, ensure_ascii=False, indent=2))
        return 0

    if a.cmd == "audit-verify":
        ok, n = audit.verify(ws)
        print(f"journal {'intègre' if ok else 'ALTÉRÉ'} ({n} entrées vérifiées)")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
