"""Variety and conditioning metrics for a persona release.

These follow the external QA report on v1 (November 2026) so that every later
release is measured with the same yardstick:

  openings   distinct sentence openings per text field, with the name masked
  frames     distinct texts after masking every capitalised word and number
  overlap    mean Jaccard overlap of five-word sequences between two random records
  names      size and concentration of the name pool
  assoc      Cramer's V between pairs of structured columns
  comorbid   observed / expected co-occurrence of condition pairs

Usage: python3 src/metrics.py [parquet] [--json out.json]
"""

import argparse
import json
import math
import random
import re
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
TEXT_FIELDS = (
    "cultural_background", "persona", "healthcare_persona", "travel_persona", "arts_persona",
    "career_goals_and_ambitions", "culinary_persona", "sports_persona", "professional_persona",
    "skills_and_expertise", "hobbies_and_interests",
)
CAP = re.compile(r"\b[A-ZÅÄÖÉ][\w\-]*")
NUM = re.compile(r"\d+")
# v1 wrote one of six fixed "tradition" phrases into cultural_background.
V1_TRADITIONS = (
    "allemansrätten och närheten till naturen", "fikakulturen och att ta paus tillsammans", "lagom som ledstjärna",
    "föreningslivet och ideellt engagemang", "midsommar, lucia och andra högtider", "jämlikhet och tillit till grannar",
)
PAIRS = (
    ("diabetes", "högt blodtryck"),
    ("fetma", "högt blodtryck"),
    ("svår oro och ångest", "depression"),
)


def person_name(row):
    """Names are not columns (as in Nemotron); every text starts with the name."""
    if row.get("first_name"):
        return row["first_name"], row["last_name"]
    first = row["hobbies_and_interests"].split(" ", 1)[0]
    rest = row["professional_persona"][len(first) + 1:]
    # the surname runs until the first lower-case token (the verb)
    last = []
    for tok in rest.split(" "):
        if tok[:1].isupper() or tok in ("von", "af", "de", "al", "el", "van", "der", "bin"):
            last.append(tok)
        else:
            break
    return first, " ".join(last)


def mask_name(text, first, last):
    if last:
        text = text.replace(f"{first} {last}", "<name>")
    return text.replace(first, "<name>")


def frame(text):
    return NUM.sub("<n>", CAP.sub("<X>", text))


def cramers_v(pairs):
    pairs = list(pairs)
    n = len(pairs)
    joint = Counter(pairs)
    a = Counter(x for x, _ in pairs)
    b = Counter(y for _, y in pairs)
    if n == 0 or len(a) < 2 or len(b) < 2:
        return 0.0
    chi2 = 0.0
    for x, ax in a.items():
        for y, by in b.items():
            exp = ax * by / n
            chi2 += (joint.get((x, y), 0) - exp) ** 2 / exp
    return math.sqrt(chi2 / (n * (min(len(a), len(b)) - 1)))


def age_band(age):
    return "0-15" if age < 16 else "16-29" if age < 30 else "30-44" if age < 45 else "45-64" if age < 65 else "65-79" if age < 80 else "80+"


def fivegram_overlap(texts, pairs=20000, seed=7):
    rng = random.Random(seed)
    grams = []
    for t in texts:
        w = t.lower().split()
        grams.append({tuple(w[i:i + 5]) for i in range(len(w) - 4)})
    total = 0.0
    used = 0
    for _ in range(pairs):
        a, b = rng.sample(range(len(grams)), 2)
        if grams[a] and grams[b]:
            total += len(grams[a] & grams[b]) / len(grams[a] | grams[b])
            used += 1
    return total / max(1, used)


def compute(path):
    rows = pq.read_table(path).to_pylist()
    n = len(rows)
    seeds_path = Path(path).with_name(Path(path).stem + "_seeds.parquet")
    if seeds_path.exists():  # v2 ships names in a companion table
        seeds = {s["uuid"]: s for s in pq.read_table(seeds_path).to_pylist()}
        names = [(seeds[r["uuid"]]["first_name"], seeds[r["uuid"]]["last_name"]) for r in rows]
    else:
        names = [person_name(r) for r in rows]
    out = {"rows": n, "fields": {}}

    for field in TEXT_FIELDS:
        masked = [mask_name(r[field], *nm) for r, nm in zip(rows, names)]
        open2 = Counter(" ".join(m.split()[:2]) for m in masked)
        open4 = Counter(" ".join(m.split()[:4]) for m in masked)
        top = open4.most_common(3)
        out["fields"][field] = {
            "openings_2": len(open2),
            "openings_4": len(open4),
            "commonest_opening_share": top[0][1] / n,
            "top3_opening_share": sum(c for _, c in top) / n,
            "distinct_texts": len(set(r[field] for r in rows)),
            "distinct_frames": len(set(frame(m) for m in masked)),
            "fivegram_overlap": fivegram_overlap(masked),
        }

    given = Counter(f for f, _ in names)
    sur = Counter(l for _, l in names)
    full = Counter(names)
    out["names"] = {
        "distinct_given": len(given),
        "distinct_surnames": len(sur),
        "distinct_full": len(full),
        "top10_surname_share": sum(c for _, c in sur.most_common(10)) / n,
        "most_frequent_full_name": full.most_common(1)[0][1],
    }

    workers = [r for r in rows if r["occupation"] != "not_in_workforce"]
    adults = [r for r in rows if r["age"] >= 25]
    assoc = {
        "occupation_x_education (workers)": cramers_v((r["occupation"], r["education_level"]) for r in workers),
        "county_x_education (25+)": cramers_v((r["lan"], r["education_level"]) for r in adults),
        "county_x_occupation (workers)": cramers_v((r["lan"], r["occupation"]) for r in workers),
        "county_x_household (25+)": cramers_v((r["lan"], r["household_type"]) for r in adults),
    }
    if "country_of_birth" in rows[0]:
        assoc["county_x_country_of_birth"] = cramers_v((r["lan"], r["country_of_birth"]) for r in rows)
    trad = [(r, next((t for t in V1_TRADITIONS if t in r["cultural_background"]), None)) for r in rows]
    trad = [(r, t) for r, t in trad if t]
    if len(trad) > n / 2:  # only meaningful for the rule-based v1 text
        assoc["v1_tradition_x_county"] = cramers_v((t, r["lan"]) for r, t in trad)
        assoc["v1_tradition_x_age_band"] = cramers_v((t, age_band(r["age"])) for r, t in trad)
        assoc["v1_tradition_x_occupation"] = cramers_v((t, r["occupation"]) for r, t in trad)
        assoc["v1_tradition_x_education"] = cramers_v((t, r["education_level"]) for r, t in trad)
        assoc["v1_tradition_x_sex"] = cramers_v((t, r["sex"]) for r, t in trad)
    out["association_cramers_v"] = assoc

    if "occupation_code" in rows[0]:  # SSYK 222 and 223 are nurses; levels below upper secondary
        nurses = [r for r in workers if r["occupation_code"][:3] in ("222", "223")]
        low = lambda r: r["education_level"].startswith("förgymnasial")
    else:
        nurses = [r for r in workers if r["occupation"] == "sjuksköterska"]
        low = lambda r: r["education_level"] == "grundskola"
    if nurses:
        out["nurses_compulsory_only_share"] = sum(low(r) for r in nurses) / len(nurses)
    out["distinct_occupations"] = len({r["occupation"] for r in workers})

    cond_path = Path(path).with_name(Path(path).stem + "_conditions.parquet")
    if cond_path.exists():
        has = {}
        for c in pq.read_table(cond_path).to_pylist():
            if c["source"] == "folkhalsomyndigheten":
                has.setdefault(c["condition"], set()).add(c["uuid"])
        # Expected co-occurrence is computed within age band and sex, so that a ratio above one
        # means clustering beyond what shared age and sex already explain.
        strata = Counter()
        for r in rows:
            strata[(min(85, r["age"] // 5 * 5), r["sex"])] += 1
        key = {r["uuid"]: (min(85, r["age"] // 5 * 5), r["sex"]) for r in rows}
        out["comorbidity_lift"] = {}
        for a, b in PAIRS:
            sa, sb = has.get(a, set()), has.get(b, set())
            ca, cb = Counter(key[u] for u in sa), Counter(key[u] for u in sb)
            expected = sum(ca[k] * cb[k] / size for k, size in strata.items()) / n
            observed = len(sa & sb) / n
            out["comorbidity_lift"][f"{a} + {b}"] = {
                "observed": observed, "expected_given_age_sex": expected,
                "ratio": observed / expected if expected else None,
            }
    return out


def show(m):
    print(f"rows: {m['rows']:,}")
    print(f"\n{'field':30}{'open2':>6}{'open4':>7}{'top1':>7}{'top3':>7}{'texts':>8}{'frames':>8}{'5-gram':>8}")
    for f, v in m["fields"].items():
        print(f"{f:30}{v['openings_2']:>6}{v['openings_4']:>7}{v['commonest_opening_share']:>7.1%}{v['top3_opening_share']:>7.1%}"
              f"{v['distinct_texts']:>8}{v['distinct_frames']:>8}{v['fivegram_overlap']:>8.2%}")
    print("\nnames:", json.dumps(m["names"], ensure_ascii=False))
    print("\nCramer's V")
    for k, v in m["association_cramers_v"].items():
        print(f"  {k:36}{v:.4f}")
    print(f"\ndistinct occupations: {m['distinct_occupations']}")
    if "nurses_compulsory_only_share" in m:
        print(f"nurses with compulsory school only: {m['nurses_compulsory_only_share']:.1%}")
    for k, v in m.get("comorbidity_lift", {}).items():
        print(f"lift {k:36} observed {v['observed']:.3%}  expected {v['expected_given_age_sex']:.3%}  ratio {v['ratio']:.2f}x")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=str(ROOT / "data/swedish_personas_100k.parquet"))
    ap.add_argument("--json")
    args = ap.parse_args()
    result = compute(args.path)
    show(result)
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
