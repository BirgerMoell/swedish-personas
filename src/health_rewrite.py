"""Rewrite only `healthcare_persona` for all personas, with less 'vårdcentral' and more varied care contact.

Why: in the v3 texts 51% of healthcare texts say "vårdcentral", because the model uses it for almost every contact line
(even "ringer 1177 ..." gave 93%). Here every person gets a new sampled contact line from a wider, weighted list, only some of
which name the vårdcentral, and a text that says "vårdcentral" when the line does not is rejected and retried.

Two steps:
  python3 src/health_rewrite.py build  OUT_INPUT.jsonl      (local) joins seeds, v3 names, v3 texts and the new contact line
  python3 src/health_rewrite.py run    INPUT.jsonl OUT.jsonl --url URL [--shard K/N] [--workers 64]   (on the cluster)
Then  python3 src/health_rewrite.py merge  PROSE_FINAL.jsonl REWRITE.jsonl OUT.jsonl  replaces the field in the v3 text file.
"""

import argparse
import json
import random
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prose_generate as pg  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIELD = "healthcare_persona"
CONTEXT = ("cultural_background", "skills_and_expertise", "hobbies_and_interests", "career_goals_and_ambitions")

# (weight, line, who). who: "any", "work" (employed), "cond" (has a listed condition), "pain", "mind", "old" (75+).
ADULT = (
    (12, "har fast läkarkontakt på vårdcentralen", "any"),
    (4, "går på vårdcentralen först när familjen tjatar", "any"),
    (10, "ringer 1177 först och går sedan dit rådet pekar", "any"),
    (12, "går sällan till vården och söker först när det blir besvärligt", "any"),
    (8, "sköter mycket genom appar och videobesök hos en digital vårdgivare", "any"),
    (8, "går till företagshälsovården genom jobbet", "work"),
    (4, "har en privat vårdförsäkring genom arbetsgivaren", "work"),
    (8, "är mest hos tandläkare, optiker eller sjukgymnast", "any"),
    (6, "går på regelbundna kontroller på sjukhusets mottagning", "cond"),
    (10, "tar hjälp av apotekspersonalen och egenvård före läkare", "any"),
    (5, "träffar en distriktssköterska för kontroller och uppföljning", "cond"),
    (6, "går hos fysioterapeut eller kiropraktor för sina besvär", "pain"),
    (4, "följs av en specialistläkare på sjukhuset eller en privat mottagning", "cond"),
    (4, "har kontakt med psykolog eller kurator", "mind"),
    (6, "sköter sig själv med motion och kost och söker nästan aldrig vård", "any"),
    (10, "har hemsjukvård eller hjälp av kommunens äldreomsorg", "old"),
)
CHILD = (
    (5, "går på barnavårdscentralen (BVC) för kontroller och vaccin", "any"),
    (5, "träffar skolsköterskan och skolläkaren i skolan", "any"),
    (3, "är sällan sjuk; föräldrarna ringer 1177 vid behov", "any"),
    (3, "går på tandvården för barn", "any"),
    (2, "har kontakt med vårdcentralen när något händer", "any"),
)
EXTRA_RULE = ("\n- Skriv ordet \"vårdcentral\" i hälsotexten bara om raden \"Kontakt med vården\" nämner den. Annars beskriver du kontakten med "
              "andra ord (läkare, sjuksköterska, mottagning, 1177, appen, apoteket, sjukhuset). Utgå alltid från raden \"Kontakt med vården\".")


def draw_contact(seed):
    rng = random.Random(seed["uuid"] + ":health-v3")
    if seed["age"] < 16:
        options = CHILD
    else:
        conds = " ".join(seed["conditions"]).lower()
        has = {"any": True, "work": seed["employment_status"] in ("anställd", "egenföretagare"), "cond": bool(seed["conditions"]),
               "pain": "värk" in conds or "smärt" in conds, "mind": any(w in conds for w in ("oro", "ångest", "depress")), "old": seed["age"] >= 75}
        options = tuple(o for o in ADULT if has[o[2]])
    return rng.choices([o[1] for o in options], weights=[o[0] for o in options])[0]


def build(out_path):
    import pyarrow.parquet as pq
    names = {r["uuid"]: r for r in pq.read_table(ROOT / "data/scratch_names/new_100k_seeds.parquet", columns=["uuid", "first_name", "last_name"]).to_pylist()}
    texts = {}
    for line in open(ROOT / "data/full/prose_100k_v3_final.jsonl", encoding="utf-8"):
        r = json.loads(line)
        texts[r["uuid"]] = r
    n = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for line in open(ROOT / "data/full/seeds_100k.jsonl", encoding="utf-8"):
            s = json.loads(line)
            t = texts.get(s["uuid"])
            if t is None:
                continue
            s["first_name"], s["last_name"] = names[s["uuid"]]["first_name"], names[s["uuid"]]["last_name"]
            s["health_contact"] = draw_contact(s)
            keep = {k: s[k] for k in ("uuid", "first_name", "last_name", "sex", "age", "birth_year", "kommun", "lan", "country_of_birth", "background",
                                      "parents_country_of_birth", "marital_status", "household_type", "education_level", "employment_status",
                                      "occupation_code", "occupation", "industry", "conditions", "health_contact", "personality")}
            keep["opening"] = s["openings"][FIELD]
            keep["work"] = t.get("work")
            keep["context"] = {k: t[k] for k in CONTEXT}
            out.write(json.dumps(keep, ensure_ascii=False) + "\n")
            n += 1
    print(n, "rows ->", out_path)


def problems_for(result, seed):
    found = pg.prose_problems(result, {FIELD: None}, {**seed, "first_name": seed["first_name"], "last_name": seed["last_name"]})
    value = result.get(FIELD) or ""
    if isinstance(value, str) and seed["first_name"] not in value and seed["last_name"] not in value:
        found.append("name missing")
    if isinstance(value, str) and "vårdcentral" in value.lower() and "vårdcentral" not in seed["health_contact"].lower():
        found.append("says vårdcentral, the contact line does not")
    return found


def rewrite_one(client, seed):
    info = pg.facts(seed, seed.get("work"))
    context = "\n".join(f"{k}: {v}" for k, v in seed["context"].items())
    prompt = (f"Uppgifter om personen:\n{info}\n\nRedan skrivet om personen:\n{context}\n\n"
              f"Skriv följande fält. Det ska stämma med det som redan är skrivet men tillföra nya detaljer och inte upprepa det:\n"
              f"- {FIELD}: {pg.PERSONAS[FIELD]} Inled första meningen {seed['opening']}.")
    base = int(seed["uuid"][:8], 16) + 7
    result, used, again, problems = client.attempt(pg.SYSTEM + EXTRA_RULE, prompt, pg.prose_schema({FIELD: None}), base, lambda r: problems_for(r, seed))
    if problems:
        return {"uuid": seed["uuid"], "failed": problems}
    return {"uuid": seed["uuid"], FIELD: " ".join(result[FIELD].split()), "health_contact": seed["health_contact"],
            "completion_tokens": used, "retries": again}


def run(args):
    seeds = [json.loads(line) for line in open(args.input, encoding="utf-8")]
    if args.shard:
        k, n = map(int, args.shard.split("/"))
        seeds = seeds[k::n]
    seeds = seeds[:args.limit]
    done = set()
    try:
        done = {r["uuid"] for r in map(json.loads, open(args.out, encoding="utf-8")) if "failed" not in r}
    except FileNotFoundError:
        pass
    todo = [s for s in seeds if s["uuid"] not in done]
    client = pg.Client(args.url, args.temperature)
    print(f"model {client.model}: {len(todo)} to write, {len(done)} already done", flush=True)
    lock, count = threading.Lock(), {"ok": 0, "failed": 0, "tokens": 0, "retries": 0}
    with open(args.out, "a", encoding="utf-8") as handle:
        def one(seed):
            try:
                row = rewrite_one(client, seed)
            except Exception as error:
                row = {"uuid": seed["uuid"], "failed": [f"crash: {error!r}"]}
            with lock:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
                count["failed" if "failed" in row else "ok"] += 1
                count["tokens"] += row.get("completion_tokens", 0)
                count["retries"] += row.get("retries", 0)
                if (count["ok"] + count["failed"]) % 500 == 0:
                    print(count, flush=True)
        with ThreadPoolExecutor(args.workers) as pool:
            list(pool.map(one, todo))
    print("finished", count, flush=True)


def merge(args):
    new = {}
    for line in open(args.rewrite, encoding="utf-8"):
        r = json.loads(line)
        if "failed" not in r:
            new[r["uuid"]] = r[FIELD]
    n = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for line in open(args.final, encoding="utf-8"):
            r = json.loads(line)
            if r["uuid"] in new:
                r[FIELD] = new[r["uuid"]]
                n += 1
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(n, "healthcare texts replaced ->", args.out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("out")
    r = sub.add_parser("run"); r.add_argument("input"); r.add_argument("out"); r.add_argument("--url", required=True)
    r.add_argument("--shard"); r.add_argument("--workers", type=int, default=64); r.add_argument("--temperature", type=float, default=0.9); r.add_argument("--limit", type=int)
    m = sub.add_parser("merge"); m.add_argument("final"); m.add_argument("rewrite"); m.add_argument("out")
    a = ap.parse_args()
    {"build": lambda: build(a.out), "run": lambda: run(a), "merge": lambda: merge(a)}[a.cmd]()
