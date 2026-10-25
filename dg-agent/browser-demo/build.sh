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
PY
# Inline data + engine and transpile to ES2018 for older mobile browsers (needs: npm i esbuild@0.24.0)
node build.js && mv dg-compliance-assistant.html dist/
