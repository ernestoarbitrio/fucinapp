import urllib.request
import json

url = "https://raw.githubusercontent.com/matteocontrini/comuni-json/master/comuni.json"
with urllib.request.urlopen(url) as r:
    data = json.loads(r.read())
out = []
for c in data:
    cap = c.get("cap", "")
    if isinstance(cap, list):
        cap = cap[0] if cap else ""
    out.append({"comune": c["nome"], "provincia": c["sigla"], "cap": cap})
with open("anagrafica/static/anagrafica/comuni.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
print(f"Done: {len(out)} comuni")
