"""Build the v3 data for the GitHub Pages site: docs/people.json (6,000 map dots) and docs/browse.json (1,000 full personas).

Dot positions, the land outline and the municipality list come from the existing docs/people.json (dots placed inside
their municipality). Each dot gets a v3 persona from the same municipality with the same sex and the closest age, so it keeps
its place and colour. The first 1,000 dots carry the full record in browse.json, in the same order, so a dot can open it.
"""

import json
import random
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
FULL = 1000
KEEP = ("first_name", "last_name", "sex", "age", "marital_status", "household_type", "education_level", "occupation", "occupation_code",
        "industry", "employment_status", "country_of_birth", "background", "kommun", "lan", "name_heritage", "parents_country_of_birth",
        "birth_year", "openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism", "conditions", "persona",
        "cultural_background", "professional_persona", "skills_and_expertise", "skills_and_expertise_list", "hobbies_and_interests",
        "hobbies_and_interests_list", "career_goals_and_ambitions", "sports_persona", "arts_persona", "travel_persona", "culinary_persona",
        "healthcare_persona", "job_title", "workplace", "seniority", "work_tools", "work_tasks")


def main():
    old = json.load(open(ROOT / "docs/people.json", encoding="utf-8"))
    rows = pq.read_table(ROOT / "hub_v3/data/personas_100k.parquet").to_pylist()
    pool = defaultdict(list)
    for r in rows:
        pool[(r["kommun"], r["sex"])].append(r)
    rng = random.Random(11)
    used, picked = set(), []
    for i in range(len(old["x"])):
        kom = old["kommuner"][old["kom"][i]]
        sex = "Man" if old["sex"][i] == 0 else "Kvinna"
        cands = [r for r in pool[(kom, sex)] if r["uuid"] not in used]
        best = min(abs(r["age"] - old["age"][i]) for r in cands)
        r = rng.choice([c for c in cands if abs(c["age"] - old["age"][i]) == best])
        used.add(r["uuid"])
        picked.append(r)
    occupations = sorted({r["occupation"] for r in picked})
    occ_idx = {v: i for i, v in enumerate(occupations)}
    lans = old["lans"]
    out = {k: old[k] for k in ("aspect", "x", "y", "kom", "lans", "kommuner", "land")}
    out.update({
        "age": [r["age"] for r in picked], "sex": [0 if r["sex"] == "Man" else 1 for r in picked],
        "lan": [lans.index(r["lan"]) for r in picked], "cond": [min(3, len(r["conditions"] or [])) for r in picked],
        "occ": [occ_idx[r["occupation"]] for r in picked], "name": [f'{r["first_name"]} {r["last_name"]}' for r in picked],
        "txt": [r["persona"] for r in picked], "health": [r["healthcare_persona"] for r in picked], "occupations": occupations,
        "full": FULL,
    })
    (ROOT / "docs/people.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    browse = [{k: r[k] for k in KEEP} for r in picked[:FULL]]
    (ROOT / "docs/browse.json").write_text(json.dumps(browse, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(len(picked), "dots;", len(browse), "full records")


if __name__ == "__main__":
    main()
