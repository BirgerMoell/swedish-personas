"""Assemble the files for the Hugging Face preview of v2 in hub_v2/data/.

Usage: python3 src/export_hub.py
  personas_100k, seeds_100k, conditions_100k   the structured release (template prose)
  pilot                                        personas with model-written prose and a work profile
  task_catalogue                               one row per work task and occupation group
"""

import json
import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hub_v2" / "data"
STRUCTURED = ("sex", "age", "marital_status", "household_type", "education_level", "occupation", "occupation_code", "industry",
              "employment_status", "country_of_birth", "background", "kommun", "lan", "country")
SEED = ("first_name", "last_name", "name_heritage", "parents_country_of_birth", "birth_year",
        "openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")
TEXT = ("persona", "cultural_background", "professional_persona", "skills_and_expertise", "skills_and_expertise_list",
        "hobbies_and_interests", "hobbies_and_interests_list", "career_goals_and_ambitions", "sports_persona", "arts_persona",
        "travel_persona", "culinary_persona", "healthcare_persona")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = ROOT / "data"
    for suffix in ("", "_seeds", "_conditions"):
        shutil.copy(data / f"swedish_personas_100k{suffix}.parquet", OUT / f"{(suffix or '_personas')[1:]}_100k.parquet")

    catalogue = [json.loads(line) for line in open(data / "pilot/task_catalogue.jsonl", encoding="utf-8")]
    tasks = {}
    rows = []
    for group in catalogue:
        for t in group["tasks"]:
            tasks[t["task_id"]] = t
            rows.append({"occupation_code": group["occupation_code"], "occupation": group["occupation"], "task_id": t["task_id"],
                         "task": t["task"], "computer_based": t["computer_based"], "tools": t["tools"], "output": t["output"]})
    pq.write_table(pa.Table.from_pylist(rows), OUT / "task_catalogue.parquet")

    structured = {r["uuid"]: r for r in pq.read_table(data / "swedish_personas_100k.parquet").to_pylist()}
    seeds = {r["uuid"]: r for r in pq.read_table(data / "swedish_personas_100k_seeds.parquet").to_pylist()}
    conditions = {}
    for c in pq.read_table(data / "swedish_personas_100k_conditions.parquet").to_pylist():
        conditions.setdefault(c["uuid"], []).append(c["condition"])
    task_type = pa.list_(pa.struct([("task_id", pa.string()), ("share_percent", pa.int32()), ("task", pa.string()),
                                    ("computer_based", pa.string()), ("detail", pa.string())]))
    fields = [("uuid", pa.string())] + [(k, pa.int32() if k in ("birth_year", "openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism") else pa.string()) for k in SEED[:2]]
    schema = pa.schema(
        [("uuid", pa.string()), ("first_name", pa.string()), ("last_name", pa.string())]
        + [(k, pa.int32() if k == "age" else pa.string()) for k in STRUCTURED]
        + [("name_heritage", pa.string()), ("parents_country_of_birth", pa.string()), ("birth_year", pa.int32())]
        + [(k, pa.int32()) for k in SEED[5:]]
        + [("conditions", pa.list_(pa.string()))]
        + [(k, pa.list_(pa.string()) if k.endswith("_list") else pa.string()) for k in TEXT]
        + [("job_title", pa.string()), ("workplace", pa.string()), ("seniority", pa.string()),
           ("work_tools", pa.list_(pa.string())), ("work_tasks", task_type)])
    pilot = []
    for line in open(data / "pilot/pilot2_1000.jsonl", encoding="utf-8"):
        p = json.loads(line)
        if "failed" in p:
            continue
        u = p["uuid"]
        row = {"uuid": u, **{k: structured[u][k] for k in STRUCTURED}, **{k: seeds[u][k] for k in SEED},
               "conditions": sorted(set(conditions.get(u, []))), **{k: p[k] for k in TEXT}}
        work = p.get("work")
        row.update({"job_title": work["job_title"], "workplace": work["workplace"], "seniority": work["seniority"], "work_tools": work["tools"],
                    "work_tasks": [{**t, "task": tasks[t["task_id"]]["task"], "computer_based": tasks[t["task_id"]]["computer_based"]} for t in work["tasks"]]}
                   if work else {"job_title": None, "workplace": None, "seniority": None, "work_tools": None, "work_tasks": None})
        pilot.append(row)
    pq.write_table(pa.Table.from_pylist(pilot, schema=schema), OUT / "pilot.parquet")
    for name in ("metrics_v1", "metrics_v2_structured", "metrics_pilot_gemma_1000", "metrics_pilot2_gemma_1000"):
        (ROOT / "hub_v2" / "reports").mkdir(exist_ok=True)
        shutil.copy(ROOT / "reports" / f"{name}.json", ROOT / "hub_v2" / "reports" / f"{name}.json")
    print(f"pilot {len(pilot)} rows, catalogue {len(rows)} tasks ->", OUT)


if __name__ == "__main__":
    main()
