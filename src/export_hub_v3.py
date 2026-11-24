"""Assemble the Hugging Face files for v3 in hub_v3/data/.

Usage: python3 src/export_hub_v3.py
  personas_100k.parquet    all 100,000 people: structured columns, name and seed columns, conditions, 11 model-written
                           text fields and the work profile (job title, workplace, tasks) for those who work
  task_catalogue.parquet   one row per work task and occupation group (428 groups)
  conditions_100k.parquet  long table of health conditions with source and code
Reads data/full/prose_100k_v3_final.jsonl (texts and work profile, names already swapped) and data/scratch_names/ (v3 structured
data and names).
"""

import json
import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hub_v3" / "data"
NEW = ROOT / "data/scratch_names/new_100k"
STRUCTURED = ("sex", "age", "marital_status", "household_type", "education_level", "occupation", "occupation_code", "industry",
              "employment_status", "country_of_birth", "background", "kommun", "lan", "country")
SEED = ("name_heritage", "parents_country_of_birth", "birth_year", "openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")
TEXT = ("persona", "cultural_background", "professional_persona", "skills_and_expertise", "skills_and_expertise_list",
        "hobbies_and_interests", "hobbies_and_interests_list", "career_goals_and_ambitions", "sports_persona", "arts_persona",
        "travel_persona", "culinary_persona", "healthcare_persona")
INTS = {"age", "birth_year", "openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tasks, rows = {}, []
    for line in open(ROOT / "data/full/task_catalogue_428.jsonl", encoding="utf-8"):
        g = json.loads(line)
        for t in g["tasks"]:
            tasks[t["task_id"]] = t
            rows.append({"occupation_code": g["occupation_code"], "occupation": g["occupation"], "task_id": t["task_id"], "task": t["task"],
                         "computer_based": t["computer_based"], "tools": t["tools"], "output": t["output"]})
    pq.write_table(pa.Table.from_pylist(rows), OUT / "task_catalogue.parquet")

    structured = {r["uuid"]: r for r in pq.read_table(f"{NEW}.parquet").to_pylist()}
    seeds = {r["uuid"]: r for r in pq.read_table(f"{NEW}_seeds.parquet").to_pylist()}
    conditions = {}
    for c in pq.read_table(f"{NEW}_conditions.parquet").to_pylist():
        conditions.setdefault(c["uuid"], []).append(c["condition"])
    task_type = pa.list_(pa.struct([("task_id", pa.string()), ("share_percent", pa.int32()), ("task", pa.string()),
                                    ("computer_based", pa.string()), ("detail", pa.string())]))
    schema = pa.schema(
        [("uuid", pa.string()), ("first_name", pa.string()), ("last_name", pa.string())]
        + [(k, pa.int32() if k in INTS else pa.string()) for k in STRUCTURED + SEED]
        + [("conditions", pa.list_(pa.string()))]
        + [(k, pa.list_(pa.string()) if k.endswith("_list") else pa.string()) for k in TEXT]
        + [("job_title", pa.string()), ("workplace", pa.string()), ("seniority", pa.string()),
           ("work_tools", pa.list_(pa.string())), ("work_tasks", task_type)])
    out, missing = [], 0
    for line in open(ROOT / "data/full/prose_100k_v3_final.jsonl", encoding="utf-8"):
        p = json.loads(line)
        u = p["uuid"]
        row = {"uuid": u, "first_name": seeds[u]["first_name"], "last_name": seeds[u]["last_name"],
               **{k: structured[u][k] for k in STRUCTURED}, **{k: seeds[u][k] for k in SEED},
               "conditions": sorted(set(conditions.get(u, []))), **{k: p[k] for k in TEXT}}
        work = p.get("work")
        if work:
            for t in work["tasks"]:
                if t["task_id"] not in tasks:
                    raise SystemExit(f"unknown task id {t['task_id']} for {u}")
            row.update({"job_title": work["job_title"], "workplace": work["workplace"], "seniority": work["seniority"], "work_tools": work["tools"],
                        "work_tasks": [{**t, "task": tasks[t["task_id"]]["task"], "computer_based": tasks[t["task_id"]]["computer_based"]} for t in work["tasks"]]})
        else:
            row.update({"job_title": None, "workplace": None, "seniority": None, "work_tools": None, "work_tasks": None})
            missing += 1
        out.append(row)
    pq.write_table(pa.Table.from_pylist(out, schema=schema), OUT / "personas_100k.parquet")
    shutil.copy(f"{NEW}_conditions.parquet", OUT / "conditions_100k.parquet")
    print(f"{len(out)} personas ({len(out) - missing} with a work profile), {len(rows)} tasks ->", OUT)


if __name__ == "__main__":
    main()
