"""Journal d'audit append-only (JSONL) avec chaînage de hash."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def log(workspace, action, actor, **details):
    p = Path(workspace) / "journal.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    prev = ""
    if p.exists():
        lines = p.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            prev = json.loads(lines[-1])["hash"]
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "action": action, "actor": actor, **details, "prev": prev}
    entry["hash"] = hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def verify(workspace):
    p = Path(workspace) / "journal.jsonl"
    prev = ""
    if not p.exists():
        return True, 0
    n = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        h = e.pop("hash")
        if e["prev"] != prev or hashlib.sha256(json.dumps(e, sort_keys=True, ensure_ascii=False).encode()).hexdigest() != h:
            return False, n
        prev = h
        n += 1
    return True, n
