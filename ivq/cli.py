"""CLI déterministe utilisé par les agents opencode : python3 -m ivq <commande>."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

from . import audit, coverage, elm, ingest, nextstep, store
from .model import ROOT, load_json, load_model, save_json, validate_story, validate_test

REVIEWERS = ROOT / "config" / "reviewers.json"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_parser():
    ap = argparse.ArgumentParser(prog="ivq")
    ap.add_argument("-w", "--workspace", default=str(ROOT / "workspace"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest", help="CSV/XLSX/JSON -> workspace/stories.json")
    p.add_argument("source")
    p = sub.add_parser("ingest-gitlab")
    p.add_argument("project")
    p.add_argument("--labels")
    p = sub.add_parser("ingest-refs", help="référentiel SSS/SSDD (CSV id;doc;title;url ou JSON)")
    p.add_argument("source")
    sub.add_parser("validate", help="valide stories.json et tests.json")
    p = sub.add_parser("merge", help="intègre des propositions de tests (statut forcé Brouillon)")
    p.add_argument("proposed", nargs="?")
    p.add_argument("--model", help="modèle LLM utilisé (journalisé, écrase generator.model)")
    p.add_argument("--prompt-file", help="prompt de génération, archivé et référencé par son hash")
    p.add_argument("--software-version", help="version logicielle testée (si absente des tests)")
    sub.add_parser("coverage", help="rapport de couverture + anomalies")
    sub.add_parser("trace", help="matrice de traçabilité US -> fonction -> test -> exécution -> anomalie (CSV)")
    p = sub.add_parser("review-export")
    p.add_argument("--out")
    p = sub.add_parser("review-apply")
    p.add_argument("csv")
    p = sub.add_parser("review-set")
    p.add_argument("test_id")
    p.add_argument("status")
    p.add_argument("--by", required=True)
    p.add_argument("--comment", default="")
    p = sub.add_parser("link-defect", help="rattache une anomalie à un test")
    p.add_argument("test_id")
    p.add_argument("url")
    p.add_argument("--by", required=True)
    p = sub.add_parser("datasets")
    p.add_argument("--xlsx", action="store_true")
    p = sub.add_parser("publish")
    p.add_argument("--config", default=str(ROOT / "config" / "elm.json"))
    p.add_argument("--confirm", action="store_true", help="publication réelle (sinon dry-run)")
    p.add_argument("--group-by", choices=list(elm.GROUP_KEYS), help="regroupement des Test Suites")
    p.add_argument("--no-plan", action="store_true")
    p.add_argument("--no-suites", action="store_true")
    p.add_argument("--with-executions", action="store_true", help="crée aussi un Execution Record par test")
    sub.add_parser("status")
    sub.add_parser("next", help="état du pipeline et prochaine action")
    sub.add_parser("audit-verify")
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    ws = Path(a.workspace)
    model = load_model()
    summary = lambda tests: {s: sum(t["status"] == s for t in tests) for s in model["statuses"]}

    if a.cmd in ("ingest", "ingest-gitlab"):
        new = ingest.ingest(a.source) if a.cmd == "ingest" else ingest.from_gitlab(a.project, a.labels)
        bad = {s.get("id", "?"): e for s in new if (e := validate_story(s))}
        cur = {s["id"]: s for s in load_json(ws / "stories.json", [])}
        for s in new:
            if s["id"] not in bad:
                cur[s["id"]] = s
        save_json(ws / "stories.json", list(cur.values()))
        src = a.source if a.cmd == "ingest" else a.project
        audit.log(ws, "ingest", "ingestion", source=src, sha256=_sha(a.source) if a.cmd == "ingest" else None,
                  ok=len(new) - len(bad), incomplete=list(bad))
        print(json.dumps({"ingested": len(new) - len(bad), "incomplete": bad}, ensure_ascii=False, indent=2))
        return 1 if bad else 0

    if a.cmd == "ingest-refs":
        print(f"{store.ingest_refs(ws, a.source)} référence(s) SSS/SSDD")
        return 0

    if a.cmd == "validate":
        stories = load_json(ws / "stories.json", [])
        tests = load_json(ws / "tests.json", [])
        sids = {s["id"] for s in stories}
        errs = {s["id"]: e for s in stories if (e := validate_story(s))}
        errs.update({t.get("id", "?"): e for t in tests if (e := validate_test(t, model, sids))})
        print(json.dumps(errs or "OK", ensure_ascii=False, indent=2))
        return 1 if errs else 0

    if a.cmd == "merge":
        data = load_json(a.proposed or ws / "tests.proposed.json")
        prompt = Path(a.prompt_file).read_text(encoding="utf-8") if a.prompt_file else None
        res = store.merge(ws, data["tests"] if isinstance(data, dict) else data, model, model_name=a.model,
                          prompt=prompt, software_version=a.software_version)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1 if res["rejected"] else 0

    if a.cmd == "coverage":
        refs = load_json(ws / "refs.json", None) if (ws / "refs.json").exists() else None
        rep = coverage.analyse(load_json(ws / "stories.json", []), load_json(ws / "tests.json", []), model, refs)
        save_json(ws / "coverage.json", rep)
        (ws / "coverage.md").write_text(coverage.to_markdown(rep), encoding="utf-8")
        audit.log(ws, "coverage", "couverture", **rep["summary"])
        print(json.dumps(rep["summary"], ensure_ascii=False, indent=2))
        return 0

    if a.cmd == "trace":
        rows = coverage.trace_rows(load_json(ws / "stories.json", []), load_json(ws / "tests.json", []))
        out = ws / "traceability.csv"
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=coverage.TRACE_COLUMNS, delimiter=";")
            w.writeheader()
            w.writerows(rows)
        print(f"{out} ({len(rows)} lignes)")
        return 0

    if a.cmd == "review-export":
        out = a.out or str(ws / "review.csv")
        store.export_review_csv(ws, out)
        print(out)
        return 0
    if a.cmd == "review-apply":
        print(f"{store.apply_review_csv(ws, a.csv, model, store.load_reviewers(REVIEWERS))} décision(s) appliquée(s)")
        return 0
    if a.cmd == "review-set":
        store.review(ws, a.test_id, a.status, a.by, a.comment, model, store.load_reviewers(REVIEWERS))
        return 0
    if a.cmd == "link-defect":
        store.link_defect(ws, a.test_id, a.url, a.by)
        return 0
    if a.cmd == "datasets":
        print(store.export_datasets(ws, a.xlsx))
        return 0

    if a.cmd == "publish":
        rep = elm.publish(ws, load_json(a.config), live=a.confirm, with_suites=not a.no_suites,
                          with_plan=not a.no_plan, with_executions=a.with_executions, group_by=a.group_by)
        print(json.dumps({"live": rep["live"], "published": len(rep["published"]), "plans": len(rep["plans"]),
                          "suites": len(rep["suites"]), "executions": len(rep["executions"]),
                          "skipped": rep["skipped"]}, ensure_ascii=False, indent=2))
        return 0

    if a.cmd == "next":
        print(json.dumps(nextstep.compute(ws), ensure_ascii=False, indent=2))
        return 0

    if a.cmd == "status":
        tests = load_json(ws / "tests.json", [])
        print(json.dumps({"stories": len(load_json(ws / "stories.json", [])), "tests": len(tests),
                          "by_status": summary(tests), "published": sum(bool(t.get("elm")) for t in tests)},
                         ensure_ascii=False, indent=2))
        return 0

    if a.cmd == "audit-verify":
        ok, n = audit.verify(ws)
        print(f"journal {'intègre' if ok else 'ALTÉRÉ'} ({n} entrées vérifiées)")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
