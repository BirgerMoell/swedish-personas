"""Fetch the exact Statistics Sweden aggregates used by the generator.

Usage: python3 src/fetch_scb.py
The 2025 cells are disclosure controlled by SCB and may not sum exactly.
"""

import csv
import json
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

BASE = "https://api.scb.se/OV0104/v1/doris/en/ssd/BE/BE0101/BE0101A/BefolkningCKM"
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def request_json(payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(BASE, data=body, headers={"Content-Type": "application/json", "User-Agent": "swedish-personas/1.0"})
    with urlopen(req, timeout=120) as response:
        return json.load(response)


def selection(code, values):
    return {"code": code, "selection": {"filter": "item", "values": values}}


def write_csv(path, headings, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headings)
        writer.writerows(rows)


def count_value(value):
    return max(0, int(value)) if value not in (None, "", ".", "..", "-") else 0


def main():
    DATA.mkdir(exist_ok=True)
    meta = request_json()
    variables = {v["code"]: v for v in meta["variables"]}
    regions = variables["Region"]
    county_codes = [v for v in regions["values"] if len(v) == 2 and v != "00"]
    municipality_codes = [v for v in regions["values"] if len(v) == 4]
    names = dict(zip(regions["values"], regions["valueTexts"]))
    ages = [str(age) for age in range(100)] + ["100+1"]
    query = {"query": [
        selection("Region", county_codes),
        selection("Civilstand", ["OG", "G", "ÄNKL", "SK"]),
        selection("Alder", ages),
        selection("Kon", ["1", "2"]),
        selection("ContentsCode", ["000007ME"]),
        selection("Tid", ["2025"]),
    ], "response": {"format": "json"}}
    result = request_json(query)
    county_rows = []
    for item in result["data"]:
        region, civil, age, sex, year = item["key"]
        count = count_value(item["values"][0])
        county_rows.append((region, names[region].removesuffix(" county"), civil, age, sex, year, count))
    write_csv(DATA / "scb_county_age_sex_marital_2025.csv",
              ["county_code", "county", "marital_code", "age", "sex_code", "year", "population"], county_rows)

    query["query"] = [
        selection("Region", municipality_codes),
        selection("Civilstand", ["SC"]),
        selection("Alder", ["TotSA"]),
        selection("Kon", ["TotSa"]),
        selection("ContentsCode", ["000007ME"]),
        selection("Tid", ["2025"]),
    ]
    result = request_json(query)
    municipality_rows = []
    for item in result["data"]:
        code = item["key"][0]
        municipality_rows.append((code, names[code], code[:2], count_value(item["values"][0])))
    write_csv(DATA / "scb_municipality_2025.csv",
              ["municipality_code", "municipality", "county_code", "population"], municipality_rows)
    (DATA / "source.json").write_text(json.dumps({
        "source": BASE, "table": meta["title"], "year": 2025,
        "county_cells": len(county_rows), "municipalities": len(municipality_rows),
        "county_population_sum": sum(row[-1] for row in county_rows),
        "municipality_population_sum": sum(row[-1] for row in municipality_rows),
        "accessed": date.today().isoformat(),
        "note": "SCB applies Cell Key Method disclosure control to 2025 cells; margins may differ slightly."
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(county_rows)} county cells and {len(municipality_rows)} municipalities")


if __name__ == "__main__":
    main()
