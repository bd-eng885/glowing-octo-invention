#!/bin/sh
# Builds dist/dg-compliance-assistant.html from the seed data, engine and page.
set -e
cd "$(dirname "$0")"
mkdir -p dist
python3 - <<'PY'
import json
seed = "../backend/app/data/seed/"
d = {"un": json.load(open(seed + "un_entries_demo.json")), "imdg": json.load(open(seed + "imdg_segregation_table_demo.json")),
     "iata": json.load(open(seed + "iata_segregation_demo.json")), "sources": json.load(open(seed + "sources.json"))}
for s in d["sources"]:
    s.pop("location", None)
data = "const DATA=" + json.dumps(d, ensure_ascii=False, separators=(",", ":")) + ";\n"
open("data.js", "w").write(data)
page = open("ui.html").read().replace("/*__DATA__*/", data).replace("/*__ENGINE__*/", open("engine.js").read())
open("dist/dg-compliance-assistant.html", "w").write(page)
print("built dist/dg-compliance-assistant.html")
PY
