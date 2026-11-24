"""Fetch occupation descriptions, job titles and skills per SSYK 4-digit group.

Usage: python3 src/fetch_jobtech.py
Source: Arbetsförmedlingen JobTech Taxonomy (taxonomy.api.jobtechdev.se), public API.
Writes data/taxonomy/ssyk4.json: {ssyk code: {label, definition, titles, skills}}.
"""

import json
import subprocess
from datetime import date
from pathlib import Path

API = "https://taxonomy.api.jobtechdev.se/v1/taxonomy/graphql"
OUT = Path(__file__).resolve().parents[1] / "data" / "taxonomy"
QUERY = """query { concepts(type: "ssyk-level-4") { preferred_label ssyk_code_2012 definition
  narrower(type: "occupation-name") { preferred_label }
  related(type: "skill") { preferred_label } } }"""


def main():
    raw = subprocess.run(["curl", "-sS", "--fail", "--max-time", "300", "-G", API, "--data-urlencode", "query=" + QUERY],
                         check=True, capture_output=True).stdout
    groups = {}
    for c in json.loads(raw)["data"]["concepts"]:
        definition = (c["definition"] or "").replace("\r", "")
        groups[c["ssyk_code_2012"]] = {
            "label": c["preferred_label"],
            "definition": definition.split("Hit hör inte")[0].strip(),  # drop the list of excluded titles
            "titles": sorted(t["preferred_label"] for t in c["narrower"]),
            "skills": sorted(s["preferred_label"] for s in c["related"]),
        }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ssyk4.json").write_text(json.dumps(dict(sorted(groups.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (OUT / "source.json").write_text(json.dumps({"accessed": date.today().isoformat(), "api": API, "groups": len(groups)}, indent=2) + "\n")
    print(f"{len(groups)} occupation groups -> {OUT / 'ssyk4.json'}")


if __name__ == "__main__":
    main()
