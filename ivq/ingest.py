"""Agent Ingestion (partie déterministe) : CSV / Excel / JSON / GitLab -> stories.json."""
import csv
import json
import os
import re
import urllib.request
from pathlib import Path

LIST_FIELDS = ["preconditions", "business_rules", "inputs", "alternatives", "errors", "sss_refs", "ssdd_refs"]
SCALAR_FIELDS = ["sprint", "campaign", "module", "parent", "requirement_url", "software_version"]
ALIASES = {  # en-têtes FR/EN (exports DOORS Next / Excel) -> champs normalisés
    "id": "id", "identifiant": "id", "id exigence": "id", "titre": "title", "title": "title",
    "version": "version", "priorité": "priority", "priorite": "priority", "priority": "priority",
    "fonction de service": "service_function", "service_function": "service_function",
    "acteur": "actor", "actor": "actor", "préconditions": "preconditions", "preconditions": "preconditions",
    "règles métier": "business_rules", "regles metier": "business_rules", "business_rules": "business_rules",
    "données d'entrée": "inputs", "donnees d'entree": "inputs", "inputs": "inputs",
    "résultat attendu": "expected_result", "resultat attendu": "expected_result", "expected_result": "expected_result",
    "cas alternatifs": "alternatives", "alternatives": "alternatives",
    "erreurs": "errors", "errors": "errors",
    "critères d'acceptation": "acceptance_criteria", "criteres d'acceptation": "acceptance_criteria",
    "acceptance_criteria": "acceptance_criteria",
    "type": "kind", "kind": "kind", "parent": "parent", "macro us": "parent", "macro-us": "parent",
    "sprint": "sprint", "campagne": "campaign", "campaign": "campaign", "module": "module",
    "sss": "sss_refs", "sss mk1": "sss_refs", "ssdd": "ssdd_refs", "sss_refs": "sss_refs", "ssdd_refs": "ssdd_refs",
    "url exigence": "requirement_url", "requirement_url": "requirement_url",
    "version logicielle": "software_version", "software_version": "software_version",
}


def _split(v):
    return [x.strip() for x in re.split(r"\s*\|\s*|\n+", v or "") if x.strip()]


def _criteria(story_id, items):
    out = []
    for i, it in enumerate(items, 1):
        m = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*:\s*(.+)$", it)
        # un préfixe "AC1:" est un id ; sinon id généré
        if m and re.match(r"^(AC|CA|CRIT)[A-Za-z0-9_.-]*$", m.group(1), re.I):
            out.append({"id": f"{story_id}-{m.group(1).upper()}", "text": m.group(2).strip()})
        else:
            out.append({"id": f"{story_id}-AC{i}", "text": it})
    return out


def _normalise(row, source_type, ref):
    r = {}
    for k, v in row.items():
        key = ALIASES.get((k or "").strip().lower())
        if key:
            if isinstance(v, float) and v.is_integer():
                v = int(v)
            r[key] = (v or "").strip() if isinstance(v, str) or v is None else str(v)
    s = {"id": r.get("id", ""), "title": r.get("title", ""), "version": r.get("version") or "1",
         "priority": r.get("priority", ""), "service_function": r.get("service_function", ""),
         "actor": r.get("actor", ""), "expected_result": r.get("expected_result", ""),
         "source": {"type": source_type, "ref": ref}}
    for f in LIST_FIELDS:
        s[f] = _split(r.get(f))
    for f in SCALAR_FIELDS:
        if r.get(f):
            s[f] = r[f]
    if r.get("kind", "").lower() in ("macro", "macro-us", "macro us"):
        s["kind"] = "macro"
    s["acceptance_criteria"] = _criteria(s["id"], _split(r.get("acceptance_criteria")))
    return s


def from_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        head = sample.splitlines()[0] if sample else ""
        dialect = csv.excel_tab if "\t" in head else csv.excel
        dialect = type("D", (dialect,), {"delimiter": ";" if head.count(";") >= head.count(",") and ";" in head else dialect.delimiter})
        return [_normalise(r, "csv", str(path)) for r in csv.DictReader(f, dialect=dialect)]


def from_xlsx(path):
    try:
        import openpyxl
    except ImportError:
        raise SystemExit("openpyxl requis pour .xlsx (pip install openpyxl) ou exporter en CSV")
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    head = [str(h or "") for h in rows[0]]
    return [_normalise(dict(zip(head, r)), "xlsx", str(path)) for r in rows[1:] if any(r)]


def from_json(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["stories"] if isinstance(data, dict) else data


def from_gitlab(project, labels=None):
    """Issues GitLab -> brouillons de US. Token via GITLAB_TOKEN, URL via GITLAB_URL."""
    base = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        raise SystemExit("GITLAB_TOKEN non défini")
    proj = urllib.request.quote(project, safe="")
    out, page = [], "1"
    while page:
        q = f"?per_page=100&state=opened&page={page}" + (f"&labels={urllib.request.quote(labels)}" if labels else "")
        req = urllib.request.Request(f"{base}/api/v4/projects/{proj}/issues{q}", headers={"PRIVATE-TOKEN": token})
        with urllib.request.urlopen(req, timeout=30) as resp:
            items, page = json.load(resp), resp.headers.get("X-Next-Page", "")
        for it in items:
            sid = f"GL-{it['iid']}"
            ac = [m.group(1).strip() for m in re.finditer(r"^\s*[-*] \[[ xX]\]\s*(.+)$", it.get("description") or "", re.M)]
            lab = {l.split("::")[0]: l.split("::", 1)[1] for l in it.get("labels", []) if "::" in l}
            s = {"id": sid, "title": it["title"], "version": it["updated_at"][:10], "priority": lab.get("priority", ""),
                 "service_function": lab.get("fonction", ""), "actor": "", "preconditions": [], "business_rules": [],
                 "inputs": [], "expected_result": "", "alternatives": [], "errors": [], "sss_refs": [], "ssdd_refs": [],
                 "acceptance_criteria": _criteria(sid, ac),
                 "source": {"type": "gitlab", "ref": it["web_url"]}, "needs_enrichment": True}
            if lab.get("sprint") or (it.get("milestone") or {}).get("title"):
                s["sprint"] = lab.get("sprint") or it["milestone"]["title"]
            out.append(s)
    return out


def ingest(path):
    ext = Path(path).suffix.lower()
    return {".csv": from_csv, ".xlsx": from_xlsx, ".json": from_json}[ext](path)
