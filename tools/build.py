"""Build index.html: inline src/engine.js and the DE/FR table (src/i18n.tsv) into src/ui.html."""
import json
from pathlib import Path
root = Path(__file__).resolve().parent.parent
src = root / "src"
ui = (src / "ui.html").read_text(encoding="utf-8")
engine = (src / "engine.js").read_text(encoding="utf-8")
rows = [l.split("\t") for l in (src / "i18n.tsv").read_text(encoding="utf-8").strip("\n").split("\n")]
assert all(len(r) == 3 for r in rows), "i18n.tsv: every row needs EN, DE and FR separated by tabs"
table = json.dumps({r[0]: [r[1], r[2]] for r in rows}, ensure_ascii=False)
body = ui.replace("/*__ENGINE__*/", engine).replace("/*__L10N__*/{}", table)
page = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '</head>\n<body>\n' + body + '\n</body>\n</html>\n')
(root / "index.html").write_text(page, encoding="utf-8")
print("index.html written,", len(page), "characters")
