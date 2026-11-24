"""Build space/static/map.json: the dot map of the viewer, one dot per persona, linked to v3 uuids.

Positions and the land outline come from docs/people.json (dots placed inside their municipality). Each dot is given a v3
persona from the same municipality with the same sex and the closest age, so the dot keeps its place and its colour.
"""

import json
import random
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = json.load(open(ROOT / "docs/people.json", encoding="utf-8"))
    rows = pq.read_table(ROOT / "hub_v3/data/personas_100k.parquet", columns=["uuid", "kommun", "lan", "sex", "age", "conditions"]).to_pylist()
    pool = defaultdict(list)
    for r in rows:
        pool[(r["kommun"], r["sex"])].append(r)
    rng = random.Random(11)
    used, uuids, ages, sexes, lans, conds = set(), [], [], [], [], []
    lan_names = sorted({r["lan"] for r in rows})
    for i in range(len(p["x"])):
        kom = p["kommuner"][p["kom"][i]]
        sex = "Man" if p["sex"][i] == 0 else "Kvinna"
        cands = [r for r in pool[(kom, sex)] if r["uuid"] not in used]
        best = min(abs(r["age"] - p["age"][i]) for r in cands)
        r = rng.choice([c for c in cands if abs(c["age"] - p["age"][i]) == best])
        used.add(r["uuid"])
        uuids.append(r["uuid"]); ages.append(r["age"]); sexes.append(p["sex"][i]); lans.append(lan_names.index(r["lan"]))
        conds.append(min(3, len(r["conditions"] or [])))
    out = {"aspect": p["aspect"], "x": p["x"], "y": p["y"], "land": p["land"], "uuid": uuids, "age": ages, "sex": sexes, "lan": lans,
           "cond": conds, "lans": lan_names}
    (ROOT / "space/static/map.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(len(uuids), "dots ->", ROOT / "space/static/map.json")


if __name__ == "__main__":
    main()
