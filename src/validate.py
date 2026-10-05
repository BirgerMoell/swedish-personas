"""Release checks for generated data and its SCB source margins."""

import csv
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def normalized_counts(items, key, weight):
    counts = Counter()
    for item in items:
        counts[key(item)] += weight(item)
    total = sum(counts.values())
    return {key: count / total for key, count in counts.items()}


def total_variation(a, b):
    return sum(abs(a.get(key, 0) - b.get(key, 0)) for key in a.keys() | b.keys()) / 2


def validate(path=ROOT / "data/swedish_personas_100k.parquet"):
    rows = pq.read_table(path).to_pylist()
    with (ROOT / "data/scb_county_age_sex_marital_2025.csv").open(encoding="utf-8") as handle:
        source = list(csv.DictReader(handle))
    assert len(rows) == 100_000, "release must contain 100,000 rows"
    assert len({row["id"] for row in rows}) == len(rows), "duplicate IDs"
    assert len({row["persona_sv"] for row in rows}) == len(rows), "duplicate descriptions"
    assert len({row["county_code"] for row in rows}) == 21, "missing counties"
    assert len({row["municipality_code"] for row in rows}) == 290, "missing municipalities"
    assert all(row["age"] >= 6 or row["employment_status"] == "barn" for row in rows)
    assert all(row["age"] >= 16 or row["employment_status"] in ("barn", "elev") for row in rows)
    assert all(row["age"] >= 65 or row["employment_status"] != "pensionär" for row in rows)
    assert all(row["employment_status"] in ("anställd", "egenföretagare") or not row["occupation"] for row in rows)
    dimensions = {
        "county": (lambda r: r["county_code"], lambda r: r["county_code"], .02),
        "age": (lambda r: 100 if r["age"].startswith("100+") else int(r["age"]), lambda r: r["age"], .03),
        "sex": (lambda r: r["sex_code"], lambda r: "1" if r["scb_sex"] == "man" else "2", .01),
        "marital": (lambda r: r["marital_code"], lambda r: {"ogift": "OG", "gift": "G", "skild": "SK", "änka eller änkling": "ÄNKL"}[r["marital_status"]], .01),
    }
    for name, (source_key, generated_key, ceiling) in dimensions.items():
        target = normalized_counts(source, source_key, lambda r: int(r["population"]))
        observed = normalized_counts(rows, generated_key, lambda r: 1)
        distance = total_variation(target, observed)
        assert distance < ceiling, f"{name} distribution differs from SCB: TV={distance:.3f}"
        print(f"{name}: total variation {distance:.4f}")
    print("Release validation passed")


if __name__ == "__main__":
    validate()
