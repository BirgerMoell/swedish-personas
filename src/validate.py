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


def validate_health(rows, conditions_path):
    """Observed condition counts must match the source rates implied by each persona's age and sex."""
    from generate import FOHM_BANDS, SOS_ADULT_EXCLUDED, SOS_NAMES, load_health
    sos, fohm = load_health()
    observed = Counter((r["source"], r["code"]) for r in pq.read_table(conditions_path).to_pylist())
    expected = Counter()
    for row in rows:
        age, sex = row["age"], row["sex"]
        for code, table in sos.items():
            if code in SOS_NAMES and not (age >= 16 and code in SOS_ADULT_EXCLUDED):
                expected[("socialstyrelsen", code)] += table.get((min(85, age // 5 * 5), sex), 0.0)
        if age >= 16:
            band = next(name for name, lo, hi in FOHM_BANDS if lo <= age <= hi)
            for condition, table in fohm.items():
                expected[("folkhalsomyndigheten", condition)] += table.get((band, sex), 0.0)
    checked = 0
    for key, exp in expected.items():
        if exp >= 200:
            assert abs(observed[key] - exp) / exp < 0.12, f"{key}: observed {observed[key]} vs expected {exp:.0f}"
            checked += 1
    assert not any(r["sex"] == "Kvinna" and "prostat" in r["healthcare_persona"] for r in rows), "prostate condition assigned to women"
    assert all(r["age"] >= 16 or "depression" not in r["healthcare_persona"] for r in rows), "adult-only condition for a child"
    print(f"health: {checked} conditions match source rates")


def validate(path=ROOT / "data/swedish_personas_100k.parquet"):
    rows = pq.read_table(path).to_pylist()
    with (ROOT / "data/scb_county_age_sex_marital_2025.csv").open(encoding="utf-8") as handle:
        source = list(csv.DictReader(handle))
    assert len(rows) == 100_000, "release must contain 100,000 rows"
    assert len({row["uuid"] for row in rows}) == len(rows), "duplicate uuids"
    dup = 1 - len({row["persona"] for row in rows}) / len(rows)
    assert dup < 0.02, f"too many duplicate personas: {dup:.3f}"
    assert len({row["lan"] for row in rows}) == 21, "missing counties"
    assert len({row["kommun"] for row in rows}) >= 285, "missing municipalities"
    assert all(row["age"] >= 16 or row["occupation"] == "not_in_workforce" for row in rows)
    assert all(row["age"] >= 65 or "äldreboende" not in row["household_type"] for row in rows)
    assert all(row["age"] >= 18 or row["marital_status"] == "ogift" for row in rows)
    assert all(row["country"] == "Sverige" for row in rows)
    assert all(row["professional_persona"] and row["persona"] and row["cultural_background"] for row in rows)
    dimensions = {
        "county": (lambda r: r["county"], lambda r: r["lan"], .02),
        "age": (lambda r: 100 if r["age"].startswith("100+") else int(r["age"]), lambda r: r["age"], .03),
        "sex": (lambda r: "Man" if r["sex_code"] == "1" else "Kvinna", lambda r: r["sex"], .01),
        "marital": (lambda r: r["marital_code"], lambda r: {"ogift": "OG", "gift": "G", "skild": "SK", "änka eller änkling": "ÄNKL"}[r["marital_status"]], .01),
    }
    for name, (source_key, generated_key, ceiling) in dimensions.items():
        target = normalized_counts(source, source_key, lambda r: int(r["population"]))
        observed = normalized_counts(rows, generated_key, lambda r: 1)
        distance = total_variation(target, observed)
        assert distance < ceiling, f"{name} distribution differs from SCB: TV={distance:.3f}"
        print(f"{name}: total variation {distance:.4f}")
    validate_health(rows, path.with_name(path.stem + "_conditions.parquet"))
    print("Release validation passed")


if __name__ == "__main__":
    validate()
