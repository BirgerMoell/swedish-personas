"""Viewer backend for Swedish Personas v3: FastAPI + DuckDB over the dataset's parquet file.

Loads data/personas_100k.parquet from the Hugging Face dataset (or DATA_PATH for local tests) into memory at startup.
"""

import os
import re
import threading
from pathlib import Path

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

REPO = os.environ.get("DATASET_REPO", "RenaissanceLabsEU/swedish-personas-v3")
HERE = Path(__file__).parent
STATIC = HERE / "static"
SEARCH_COLUMNS = ("first_name", "last_name", "persona", "cultural_background", "professional_persona", "skills_and_expertise",
                  "hobbies_and_interests", "career_goals_and_ambitions", "sports_persona", "arts_persona", "travel_persona",
                  "culinary_persona", "healthcare_persona", "occupation", "industry", "job_title", "workplace", "kommun", "lan")
CARD = ("uuid", "first_name", "last_name", "age", "sex", "kommun", "lan", "occupation", "job_title", "employment_status", "name_heritage", "persona")

app = FastAPI(title="Swedish Personas viewer")
db = duckdb.connect(":memory:")
lock = threading.Lock()
state = {"ready": False, "error": None, "meta": None}


def data_path():
    if os.environ.get("DATA_PATH"):
        return os.environ["DATA_PATH"]
    from huggingface_hub import hf_hub_download
    return hf_hub_download(REPO, "data/personas_100k.parquet", repo_type="dataset")


def load():
    try:
        path = data_path()
        with lock:
            db.execute(f"create table p as select row_number() over () as rid, * from read_parquet('{path}')")
            cols = ", ".join(f"coalesce(cast({c} as varchar), '')" for c in SEARCH_COLUMNS)
            db.execute(f"alter table p add column blob varchar")
            db.execute(f"update p set blob = lower(concat_ws(' ', {cols}))")
            one = lambda q: db.execute(q).fetchall()
            state["meta"] = {
                "total": one("select count(*) from p")[0][0],
                "lan": [r[0] for r in one("select lan from p group by lan order by lan")],
                "kommun": [r[0] for r in one("select kommun from p group by kommun order by kommun")],
                "occupation": [r[0] for r in one("select occupation from p where occupation <> '' group by occupation order by count(*) desc")],
                "heritage": [r[0] for r in one("select name_heritage from p group by name_heritage order by count(*) desc")],
                "employment": [r[0] for r in one("select employment_status from p group by employment_status order by count(*) desc")],
                "conditions": [r[0] for r in one("select c from (select unnest(conditions) c from p) group by c order by count(*) desc limit 60")],
                "work": one("select count(*) from p where job_title is not null")[0][0],
                "groups": one("select count(distinct occupation_code) from p where occupation_code <> ''")[0][0],
                "kommuner": one("select count(distinct kommun) from p")[0][0],
            }
        state["ready"] = True
    except Exception as error:  # surfaced through /api/status
        state["error"] = repr(error)


threading.Thread(target=load, daemon=True).start()


def need_ready():
    if state["error"]:
        raise HTTPException(500, state["error"])
    if not state["ready"]:
        raise HTTPException(503, "loading")


def where(q, sex, age_min, age_max, lan, kommun, occupation, heritage, employment, condition, works):
    clauses, args = [], []
    for token in re.findall(r"\S+", (q or "").lower())[:8]:
        clauses.append("contains(blob, ?)"); args.append(token)
    if sex: clauses.append("sex = ?"); args.append(sex)
    clauses.append("age between ? and ?"); args += [age_min, age_max]
    for col, val in (("lan", lan), ("kommun", kommun), ("occupation", occupation), ("name_heritage", heritage), ("employment_status", employment)):
        if val: clauses.append(f"{col} = ?"); args.append(val)
    if condition: clauses.append("list_contains(conditions, ?)"); args.append(condition)
    if works: clauses.append("job_title is not null")
    return " and ".join(clauses), args


def rows(cursor):
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, r)) for r in cursor.fetchall()]


@app.get("/api/status")
def status():
    return {"ready": state["ready"], "error": state["error"]}


@app.get("/api/meta")
def meta():
    need_ready()
    return state["meta"]


@app.get("/api/search")
def search(q: str = "", sex: str = "", age_min: int = 0, age_max: int = 100, lan: str = "", kommun: str = "", occupation: str = "",
           heritage: str = "", employment: str = "", condition: str = "", works: bool = False, offset: int = 0,
           limit: int = Query(24, le=100), order: str = "random"):
    need_ready()
    w, args = where(q, sex, age_min, age_max, lan, kommun, occupation, heritage, employment, condition, works)
    sort = {"age": "age, rid", "name": "last_name, first_name", "random": "hash(uuid || ?)"}.get(order, "rid")
    extra = [q + lan + kommun + occupation] if order == "random" else []
    with lock:
        total = db.execute(f"select count(*) from p where {w}", args).fetchone()[0]
        cur = db.execute(f"select {', '.join(CARD)} from p where {w} order by {sort} limit ? offset ?", args + extra + [limit, offset])
        return {"total": total, "rows": rows(cur)}


@app.get("/api/persona/{uuid}")
def persona(uuid: str):
    need_ready()
    with lock:
        cur = db.execute("select * exclude (rid, blob) from p where uuid = ?", [uuid])
        found = rows(cur)
    if not found:
        raise HTTPException(404, "no such persona")
    return JSONResponse(found[0])


@app.get("/api/random")
def random_one(q: str = "", sex: str = "", age_min: int = 0, age_max: int = 100, lan: str = "", kommun: str = "", occupation: str = "",
               heritage: str = "", employment: str = "", condition: str = "", works: bool = False):
    need_ready()
    w, args = where(q, sex, age_min, age_max, lan, kommun, occupation, heritage, employment, condition, works)
    with lock:
        r = db.execute(f"select uuid from p where {w} order by random() limit 1", args).fetchone()
    if not r:
        raise HTTPException(404, "no match")
    return {"uuid": r[0]}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=STATIC), name="static")
