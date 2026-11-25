"""Export des scénarios Gherkin en fichiers Word (.docx), à partir d'un template dans templates/ si présent.

Appelé à chaque merge (ou via `python3 -m ivq docx`). Stdlib uniquement (zipfile + XML) afin de préserver
en-têtes, pieds de page, styles et logos du modèle Word. Le Gherkin remplace {{GHERKIN}} / {{TESTS}},
sinon il est inséré avant la fin du corps du document.
"""
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from .gherkin import feature_contents
from .model import ROOT, load_json

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PLACEHOLDERS = ("{{GHERKIN}}", "{{TESTS}}")

CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

DOC_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
"""


def find_template(templates_dir=None):
    """Premier modèle .docx de templates/ (hors fichiers temporaires ~$), ou None."""
    d = Path(templates_dir) if templates_dir else ROOT / "templates"
    if not d.is_dir():
        return None
    for p in sorted(d.glob("*.docx")):
        if not p.name.startswith("~$") and p.is_file():
            return p
    return None


def _run(text, *, bold=False, italic=False, color=None, size_pt=10, font="Calibri"):
    rpr = [f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}"/>', f'<w:sz w:val="{int(size_pt * 2)}"/>']
    if bold:
        rpr.append("<w:b/>")
    if italic:
        rpr.append("<w:i/>")
    if color:
        rpr.append(f'<w:color w:val="{color}"/>')
    return f'<w:r><w:rPr>{"".join(rpr)}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _para(runs_xml, *, before=0, after=60, left=0, keep_next=False):
    ppr = [f'<w:spacing w:before="{before}" w:after="{after}"/>']
    if left:
        ppr.append(f'<w:ind w:left="{left}"/>')
    if keep_next:
        ppr.append("<w:keepNext/>")
    return f'<w:p><w:pPr>{"".join(ppr)}</w:pPr>{runs_xml}</w:p>'


def gherkin_to_ooxml(gherkin_text):
    """Convertit un texte Gherkin en paragraphes WordprocessingML mis en forme."""
    parts = []
    for raw in gherkin_text.splitlines():
        line = raw.strip()
        if not line:
            parts.append(_para("", before=0, after=80))
        elif line.startswith("Feature:"):
            parts.append(_para(_run(line, bold=True, color="1E3A5F", size_pt=14), before=240, after=120, keep_next=True))
        elif line.startswith("Scenario:"):
            parts.append(_para(_run(line, bold=True, color="0284C7", size_pt=11.5), before=180, after=60, keep_next=True))
        elif line.startswith("#"):
            parts.append(_para(_run(line, italic=True, color="64748B", size_pt=9.5), before=20, after=60, left=240))
        elif (m := re.match(r"^(Given|When|Then|And|But)\b(.*)$", line)):
            runs = _run(m.group(1), bold=True, color="0D9488") + _run(m.group(2), color="1E293B")
            parts.append(_para(runs, before=20, after=40, left=420))
        else:
            parts.append(_para(_run(line, color="1E293B"), before=20, after=40, left=240))
    return "\n".join(parts) or _para("")


def _inject_into_document_xml(doc_xml, body_xml):
    """Remplace le paragraphe contenant {{GHERKIN}} / {{TESTS}}, sinon insère avant le dernier <w:sectPr> du body."""
    replaced = False

    def _repl(match):
        nonlocal replaced
        if replaced:
            return match.group(0)
        txt = "".join(re.findall(r"<w:t\b[^>]*>(.*?)</w:t>", match.group(0), flags=re.S))
        if any(ph in txt for ph in PLACEHOLDERS):
            replaced = True
            return body_xml
        return match.group(0)

    pat = r"<w:p(?:\s[^>]*)?>(?:(?!<w:p(?:\s|>)).)*?</w:p>"
    new_xml = re.sub(pat, _repl, doc_xml, flags=re.S)
    if replaced:
        return new_xml
    matches = list(re.finditer(r"<w:sectPr\b[^>]*>.*?</w:sectPr>\s*</w:body>", doc_xml, flags=re.S))
    if matches:
        pos = matches[-1].start()
        return doc_xml[:pos] + body_xml + "\n" + doc_xml[pos:]
    return doc_xml.replace("</w:body>", body_xml + "\n</w:body>", 1)


def write_docx(out_path, gherkin_text, template_path=None):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body_xml = gherkin_to_ooxml(gherkin_text)

    if template_path and Path(template_path).is_file():
        with zipfile.ZipFile(template_path, "r") as zin, zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "word/document.xml":
                    data = _inject_into_document_xml(data.decode("utf-8"), body_xml).encode("utf-8")
                zout.writestr(item, data)
    else:
        doc_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<w:document xmlns:w="{W_NS}"><w:body>\n{body_xml}\n'
            '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>'
            "</w:body></w:document>\n"
        )
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
            zout.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
            zout.writestr("_rels/.rels", RELS_XML)
            zout.writestr("word/_rels/document.xml.rels", DOC_RELS_XML)
            zout.writestr("word/document.xml", doc_xml)
    return out_path


def build(ws, stories, tests, template=None, single=False):
    """Un .docx par US (workspace/tests_<ID-US>.docx), ou un seul tests_all.docx si single=True."""
    ws = Path(ws)
    tpl = Path(template) if template else find_template()
    blocks = feature_contents(stories, tests)
    if not blocks:
        return []
    if single:
        merged = "\n\n".join(content.rstrip() for _, content in blocks) + "\n"
        return [str(write_docx(ws / "tests_all.docx", merged, tpl))]
    return [str(write_docx(ws / f"tests_{sid}.docx", content, tpl)) for sid, content in blocks]


def export(ws=None, template=None, single=False):
    ws = Path(ws) if ws else ROOT / "workspace"
    return build(ws, load_json(ws / "stories.json", []), load_json(ws / "tests.json", []), template=template, single=single)
